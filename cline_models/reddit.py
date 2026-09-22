"""Busca posts "free" de r/CLine (último mês) e casa com os modelos da Cline.

O .json do Reddit bloqueia clientes sem sessão (403), mas o feed RSS de busca
continua aberto — por isso usamos search.rss com User-Agent de navegador.
Usa apenas a biblioteca padrão.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from html import unescape
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .scraper import Model

REDDIT_SEARCH_URL = (
    "https://www.reddit.com/r/CLine/search.rss"
    "?q=free&restrict_sr=on&sort=new&t=month"
)
# O Reddit devolve 403 para UAs genéricos de script.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


@dataclass
class Post:
    """Um post de r/CLine retornado pela busca."""

    title: str
    url: str
    updated: str
    text: str  # título + corpo, sem tags HTML

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "updated": self.updated}


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _fetch(url: str, retries: int = 3) -> bytes:
    """Baixa a URL; o Reddit costuma responder 429 em rajadas, então esperamos e tentamos de novo."""
    last_error: Exception | None = None
    for attempt in range(retries):
        request = Request(url, headers={"User-Agent": BROWSER_UA})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code != 429:
                raise
            last_error = exc
            time.sleep(10 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def fetch_free_posts(url: str = REDDIT_SEARCH_URL) -> list[Post]:
    """Retorna os posts da busca 'free' em r/CLine do último mês."""
    root = ElementTree.fromstring(_fetch(url))
    posts: list[Post] = []
    for entry in root.findall("a:entry", ATOM_NS):
        title = entry.findtext("a:title", "", ATOM_NS)
        link = entry.find("a:link", ATOM_NS)
        content = entry.findtext("a:content", "", ATOM_NS)
        posts.append(
            Post(
                title=unescape(title),
                url=(link.get("href") if link is not None else ""),
                updated=entry.findtext("a:updated", "", ATOM_NS),
                text=f"{title} {_strip_html(content)}",
            )
        )
    if not posts:
        raise ValueError(f"Nenhum post retornado por {url}.")
    return posts


def normalize(text: str) -> str:
    """Normaliza nomes para comparação: 'GLM-5.2' e 'GLM 5.2' ficam iguais."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def find_free_models(models: list[Model], posts: list[Post]) -> list[Model]:
    """Modelos da lista da Cline citados em algum post da busca 'free'."""
    found: list[Model] = []
    for model in models:
        key = normalize(model.name)
        if any(key in normalize(post.text) for post in posts):
            found.append(model)
    return found
