"""Baixa e interpreta o diretório de modelos de https://cline.bot/models.

A página é HTML estático: cada seção tem um <h2> com o nome do grupo e,
dentro dela, links <a class="model-row"> com provedor, nome e descrição.
Usa apenas a biblioteca padrão do Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.request import Request, urlopen

MODELS_URL = "https://cline.bot/models"
SITE_BASE = "https://cline.bot"  # links dos cards são relativos, ex.: /models/glm-5-2
USER_AGENT = "Mozilla/5.0 (compatible; cline-models-list/1.0)"


@dataclass
class Model:
    """Um modelo listado no diretório da Cline."""

    name: str
    provider: str
    description: str
    url: str
    group: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "provider": self.provider,
            "description": self.description,
            "url": self.url,
            "group": self.group,
        }


class _ModelsPageParser(HTMLParser):
    """Extrai (grupo, provedor, nome, descrição, href) de cada card."""

    def __init__(self) -> None:
        super().__init__()
        self.models: list[Model] = []
        self._base_url = SITE_BASE
        self._section = ""
        self._card_href: str | None = None
        self._provider = ""
        self._name = ""
        self._description = ""
        self._capture: str | None = None  # provider | name | description

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "h2":
            self._capture = "section"
            self._section = ""
        elif tag == "a" and "model-row" in classes:
            self._card_href = a.get("href") or ""
            self._provider = ""
            self._name = ""
            self._description = ""
        elif tag == "span" and "model-provider" in classes:
            self._capture = "provider"
        elif tag == "h3":
            self._capture = "name"
        elif tag == "p" and self._card_href is not None:
            self._capture = "description"

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._capture == "section":
            self._capture = None
        elif tag == "span" and self._capture == "provider":
            self._capture = None
        elif tag == "h3" and self._capture == "name":
            self._capture = None
        elif tag == "p" and self._capture == "description":
            self._capture = None
        elif tag == "a" and self._card_href is not None:
            if self._name:
                self.models.append(
                    Model(
                        name=self._name.strip(),
                        provider=self._provider.strip(),
                        description=self._description.strip(),
                        url=self._base_url + self._card_href,
                        group=self._section.strip(),
                    )
                )
            self._card_href = None
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture == "section":
            self._section += data
        elif self._capture == "provider":
            self._provider += data
        elif self._capture == "name":
            self._name += data
        elif self._capture == "description":
            self._description += data


def _fetch_page(url: str = MODELS_URL) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def fetch_models(url: str = MODELS_URL) -> list[Model]:
    """Retorna todos os modelos listados na página, na ordem do site."""
    parser = _ModelsPageParser()
    parser.feed(_fetch_page(url))
    if not parser.models:
        raise ValueError(
            f"Nenhum modelo encontrado em {url}. O layout da página pode ter mudado."
        )
    return parser.models
