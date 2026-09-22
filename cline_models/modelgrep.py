"""Rankings do modelgrep.com: modelos mais inteligentes e APIs gratuitas.

As páginas são Next.js com HTML server-rendered. Cada linha tem um link
/models/<vendor>/<slug>, o nome e o score de inteligência; o card nº 1
("Top pick") usa um markup próprio. O JSON-LD da página fornece o nome de
exibição amigável (ex.: "Z.ai: GLM 5.2 (free)"). Usa apenas a biblioteca padrão.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from urllib.request import Request, urlopen

from .reddit import BROWSER_UA

SMARTEST_URL = "https://modelgrep.com/best/smartest"
FREE_API_URL = "https://modelgrep.com/free-llm-api"
SITEMAP_URL = "https://modelgrep.com/sitemap.xml"
SITE_BASE = "https://modelgrep.com"

_NAME_PAT = re.compile(r"(?:tracking-\[-0\.025em\] |font-semibold )text-ink[^>]*>([^<]+)<")
_SCORE_PAT = re.compile(r"font-bold[^>]*text-ink[^>]*>([0-9]+\.[0-9]+)</div>")
_RANK_PAT = re.compile(r"text-on-brand\">(\d+)</span>|font-bold text-ink\">(\d+)</span>|text-ink-3\">(\d+)</span>")
_ANCHOR_PAT = re.compile(r'href="(/models/[^"]+)"')


@dataclass
class RankedModel:
    """Um modelo em um ranking do modelgrep."""

    name: str           # nome exibido pelo site, ex.: "Z.ai: GLM 5.2 (free)"
    short_name: str     # nome extraído da linha, ex.: "glm-5.2:free" ou "Kimi K3"
    score: float
    rank: int | None
    url: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "short_name": self.short_name,
            "score": self.score,
            "rank": self.rank,
            "url": self.url,
        }


def _fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": BROWSER_UA})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def _display_names_from_jsonld(html: str) -> dict[str, str]:
    """Mapa href -> nome de exibição, ex.: '/models/z-ai/glm-5.2:free' -> 'Z.ai: GLM 5.2 (free)'."""
    names: dict[str, str] = {}
    for match in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        blocks = data if isinstance(data, list) else [data]
        for block in blocks:
            if not isinstance(block, dict) or block.get("@type") != "ItemList":
                continue
            for element in block.get("itemListElement", []):
                url = element.get("url") or ""
                href = url.removeprefix(SITE_BASE)
                if href.startswith("/models/") and element.get("name"):
                    names[href] = unescape(element["name"])
    return names


def _parse_rows(html: str) -> list[RankedModel]:
    display_names = _display_names_from_jsonld(html)
    rows: list[RankedModel] = []
    seen: set[str] = set()
    anchors = list(_ANCHOR_PAT.finditer(html))
    for i, anchor in enumerate(anchors):
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(html)
        chunk = html[anchor.start():end]
        if len(chunk) > 6000:
            continue  # bloco muito grande para ser uma linha do ranking
        name = _NAME_PAT.search(chunk)
        score = _SCORE_PAT.search(chunk)
        if not (name and score):
            continue
        href = anchor.group(1)
        if href in seen:
            continue
        seen.add(href)
        rank_match = _RANK_PAT.search(chunk)
        rank = next((g for g in rank_match.groups() if g), None) if rank_match else None
        rows.append(
            RankedModel(
                name=display_names.get(href, unescape(name.group(1).strip())),
                short_name=unescape(name.group(1).strip()),
                score=float(score.group(1)),
                rank=int(rank) if rank else None,
                url=SITE_BASE + href,
            )
        )
    if not rows:
        raise ValueError("Nenhum modelo encontrado (o layout do modelgrep pode ter mudado).")
    return rows


def fetch_smartest_models(url: str = SMARTEST_URL) -> list[RankedModel]:
    """Ranking dos modelos mais inteligentes (Artificial Analysis Intelligence Index)."""
    return _parse_rows(_fetch(url))


def fetch_free_api_models(url: str = FREE_API_URL) -> list[RankedModel]:
    """Ranking de LLMs com API gratuita, ordenado por inteligência."""
    return _parse_rows(_fetch(url))


def fetch_catalog() -> dict[str, str]:
    """Catálogo de todos os modelos conhecidos: slug ('vendor/model') -> URL.

    Vem do sitemap do modelgrep (~1.5 mil modelos), usado para reconhecer
    nomes de modelos citados em textos de qualquer fonte.
    """
    xml = _fetch(SITEMAP_URL)
    catalog: dict[str, str] = {}
    for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
        marker = "/models/"
        if marker not in loc:
            continue
        slug = loc.split(marker, 1)[1].strip("/")
        if slug:
            catalog[slug] = loc
    if not catalog:
        raise ValueError("Nenhum modelo encontrado no sitemap do modelgrep.")
    return catalog


def fetch_model_info(url: str) -> tuple[str, float | None]:
    """Nome de exibição e score de inteligência da página de detalhe do modelo."""
    html = _fetch(url)
    title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    desc = re.search(r'<meta property="og:description" content="([^"]+)"', html)
    name = unescape(title.group(1)).split(" — ")[0].strip() if title else url.rsplit("/", 1)[-1]
    score = None
    if desc:
        match = re.search(r"Intelligence (\d+(?:\.\d+)?) ·", unescape(desc.group(1)))
        if match:
            score = float(match.group(1))
    return name, score


def matches_model(ranked: RankedModel, model_name: str) -> bool:
    """Verifica se um modelo do ranking corresponde a um nome de modelo da Cline.

    Compara nomes normalizados (só letras/números): 'GLM-5.2' == 'GLM 5.2'.
    """
    from .reddit import normalize

    key = normalize(model_name)
    return key in normalize(ranked.name) or key in normalize(ranked.short_name)
