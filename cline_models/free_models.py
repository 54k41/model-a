"""Detecta modelos gratuitos citando as fontes coletadas e o catálogo do modelgrep.

Regras:
1. Uma frase só conta se contiver a palavra "free" E o nome de um modelo
   reconhecido no catálogo do modelgrep (sitemap, ~1.5 mil modelos).
2. Frases que só mencionam um modelo sem falar de free são ignoradas — evita
   falsos positivos do tipo post de benchmark citando um modelo pago.
3. "Muse Spark 1.3 Contributor" == "Muse Spark 1.3": o sufixo Contributor é
   só a variante de compartilhamento com a Meta, então é descartado na
   normalização.
4. Se duas versões da mesma família aparecem como free (ex.: DeepSeek V4
   Flash e DeepSeek V4.1 Flash), vale a mais nova — quando o provedor lança
   a versão seguinte como free, ele desativa a anterior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .modelgrep import fetch_model_info
from .sources import Post


@dataclass
class FreeModel:
    """Um modelo detectado como gratuito."""

    name: str                # nome de exibição (do ranking ou da página de detalhe)
    slug: str | None         # slug no modelgrep, ex.: 'deepseek/deepseek-v4.1-flash'
    url: str | None          # página do modelo no modelgrep
    score: float | None      # inteligência (ordenação final)
    sources: set[str] = field(default_factory=set)  # títulos das menções

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "url": self.url,
            "score": self.score,
            "sources": sorted(self.sources),
        }


def _tokens(text: str) -> list[str]:
    """Tokeniza para casar nomes: minúsculas, separa letras de números
    ('solar-pro4' == 'Solar Pro 4'), descarta 'v' solto e o sufixo Contributor."""
    text = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", text.lower())
    tokens = re.split(r"[^a-z0-9.]+", text)
    return [t for t in tokens if t and t != "v" and t != "contributor"]


def _build_index(catalog: dict[str, str]) -> dict[tuple[str, ...], tuple[str, str]]:
    """Tokens normalizados do slug -> (slug, url). Na colisão (ex.: variante
    Contributor), fica o slug base, mais curto."""
    index: dict[tuple[str, ...], tuple[str, str]] = {}
    for slug, url in catalog.items():
        model_slug = slug.split("/", 1)[-1]  # ignora o vendor no casamento
        key = tuple(_tokens(model_slug))
        if not key:
            continue
        current = index.get(key)
        if current is None or len(slug) < len(current[0]):
            index[key] = (slug, url)
    return index


def _find_model_spans(sentence_tokens: list[str],
                      index: dict[tuple[str, ...], tuple[str, str]]) -> list[tuple[int, int, str, str]]:
    """Encontra modelos citados: subsequências contíguas de tokens que formam
    um slug conhecido. Mantém só os matches maximais ('glm 5.3 flash' vence
    'glm 5.3' no mesmo trecho)."""
    matches: list[tuple[int, int, str, str]] = []
    for key, (slug, url) in index.items():
        size = len(key)
        for start in range(len(sentence_tokens) - size + 1):
            if tuple(sentence_tokens[start:start + size]) == key:
                matches.append((start, start + size, slug, url))
                break
    maximal: list[tuple[int, int, str, str]] = []
    for span in matches:
        start, end, _, _ = span
        if any(other[0] <= start and end <= other[1] and (other[0], other[1]) != (start, end)
               for other in matches):
            continue
        maximal.append(span)
    return maximal


def _fallback_name(sentence: str) -> str | None:
    """Modelo free anunciado mas fora do catálogo (ex.: stealth 'Union Alpha').
    Tenta extrair o nome dos padrões de anúncio: 'added X (…)', 'Free → X',
    'X is FREE'. Case-sensitive: nomes de modelo começam com maiúscula."""
    patterns = [
        r"\b(?:added|introducing|launched|welcoming)\s+([A-Z][\w.-]*(?:\s+[A-Z0-9][\w.-]*)*)\s+\(",
        r"\bFree\s*(?:→|->|:)\s*([A-Z][\w.-]*(?:\s+[A-Z0-9][\w.-]*)*)",
        r"^([A-Z][\w.-]*(?:\s+[A-Z0-9][\w.-]*)*)\s+(?:\([^)]*\)\s*)?(?:is|was)\s+(?:now\s+)?FREE\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, sentence)
        if match:
            tokens = match.group(1).split()
            while tokens and tokens[-1].lower() in _STOP_WORDS:
                tokens.pop()
            if tokens and tokens[0].lower() not in _STOP_WORDS:
                return " ".join(tokens)
    return None


# Palavras comuns que o fallback pode arrastar junto do nome do modelo.
_STOP_WORDS = {
    "it", "if", "you", "the", "is", "was", "in", "on", "for", "to", "and",
    "or", "our", "we", "try", "now", "use", "with", "by", "at", "as", "this",
    "that", "select", "open", "run", "then", "look", "under", "from", "free",
    "cline", "model", "models", "provider", "settings", "options", "any",
}


def _family(model: FreeModel) -> str:
    """Família do modelo: tokens sem números. 'DeepSeek V4 Flash' e
    'DeepSeek V4.1 Flash' são da mesma família."""
    tokens = _tokens(model.slug or model.name)
    return " ".join(t for t in tokens if not re.search(r"\d", t))


def _version(model: FreeModel) -> float:
    tokens = _tokens(model.slug or model.name)
    for token in tokens:
        if re.search(r"\d", token):
            match = re.search(r"\d+(?:\.\d+)?", token)
            if match:
                return float(match.group())
    return 0.0


# Modelos stealth que o catálogo ainda não conhece, com a revelação oficial
# já publicada. 'ox alpha' foi revelado como GLM-5.3-Flash pela Z.ai.
_STEALTH_ALIASES = {
    "ox alpha": "z-ai/glm-5.3-flash",
}


def _drop_superseded(models: list[FreeModel]) -> list[FreeModel]:
    """Dentro de uma família, mantém só a versão mais nova."""
    by_family: dict[str, FreeModel] = {}
    for model in models:
        current = by_family.get(_family(model))
        if current is None or _version(model) > _version(current):
            by_family[_family(model)] = model
    return list(by_family.values())


def detect_free_models(posts: list[Post],
                       catalog: dict[str, str],
                       known_scores: dict[str, tuple[str, float]] | None = None,
                       resolve_details: bool = True) -> list[FreeModel]:
    """Varre os posts, reconhece modelos em frases com 'free' e resolve
    nome/score de cada um via modelgrep."""
    known_scores = known_scores or {}
    index = _build_index(catalog)
    found: dict[str, FreeModel] = {}

    for post in posts:
        for sentence in re.split(r"(?<=[.!?])\s+|\s*\n\s*|\s*[·|]\s*", post.text):
            tokens = _tokens(sentence)
            if "free" not in tokens:
                continue
            spans = _find_model_spans(tokens, index)
            if spans:
                for _start, _end, slug, url in spans:
                    model = found.get(slug)
                    if model is None:
                        name, score = known_scores.get(url, (None, None))
                        if name is None and resolve_details:
                            try:
                                name, score = fetch_model_info(url)
                            except Exception:
                                name = slug.split("/", 1)[-1]
                        model = FreeModel(name=name or slug, slug=slug, url=url,
                                          score=score)
                        found[slug] = model
                    model.sources.add(post.title)
                continue
            # sem casamento no catálogo: tenta extrair o nome do anúncio
            fallback = _fallback_name(sentence)
            if not fallback:
                continue
            key_tokens = tuple(_tokens(fallback))
            if any(key_tokens == _tokens(m.slug or m.name) for m in found.values()):
                continue  # já reconhecido pelo catálogo
            alias_slug = _STEALTH_ALIASES.get(" ".join(key_tokens))
            if alias_slug:
                fallback = None  # já revelado como um modelo do catálogo
                model = found.get(alias_slug)
                if model is not None:
                    model.sources.add(post.title)
                continue
            if fallback:
                found[f"__fallback__:{' '.join(key_tokens)}"] = FreeModel(
                    name=fallback, slug=None, url=None, score=None,
                    sources={post.title},
                )

    models = _drop_superseded(list(found.values()))
    # com score primeiro, ordenado por inteligência; sem score vai para o fim
    models.sort(key=lambda m: (m.score is None, -(m.score or 0), m.name.lower()))
    return models
