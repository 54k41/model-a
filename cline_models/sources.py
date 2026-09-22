"""Coleta posts/menções recentes de várias fontes, sempre com janela de datas.

Fontes (todas filtradas para os últimos N dias):
- Reddit r/CLine (busca "free", RSS de busca, duas ordenações)
- Hacker News (API pública do Algolia)
- Blog oficial da Cline (cline.bot/blog)

Usa apenas a biblioteca padrão.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .reddit import BROWSER_UA

REDDIT_SUBREDDIT = "CLine"
REDDIT_QUERY = "free"
HN_QUERY = "cline free"
BLOG_URL = "https://cline.bot/blog"
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


@dataclass
class Post:
    """Uma menção coletada em qualquer fonte."""

    title: str
    url: str
    date: datetime | None
    text: str
    source: str
    matched_models: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "date": self.date.isoformat() if self.date else None,
            "source": self.source,
        }


def _get(url: str, retries: int = 3) -> bytes:
    """Baixa a URL; Reddit responde 429 em rajadas, então esperamos e tentamos de novo."""
    last_error: Exception | None = None
    for attempt in range(retries):
        request = Request(url, headers={"User-Agent": BROWSER_UA})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            time.sleep(5 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _is_recent(date: datetime | None, cutoff: datetime) -> bool:
    # Post sem data legível entra; a busca já veio com janela (ex.: t=month).
    return date is None or date >= cutoff


def fetch_reddit_posts(subreddit: str = REDDIT_SUBREDDIT,
                       query: str = REDDIT_QUERY,
                       t: str = "month") -> list[Post]:
    """Posts da busca do Reddit, mesclando as ordenações new e relevance."""
    url_base = f"https://www.reddit.com/r/{subreddit}/search.rss"
    posts: dict[str, Post] = {}
    for sort in ("new", "relevance"):
        url = f"{url_base}?q={quote(query)}&restrict_sr=on&sort={sort}&t={t}"
        try:
            root = ElementTree.fromstring(_get(url))
        except Exception:
            continue
        for entry in root.findall("a:entry", ATOM_NS):
            link = entry.find("a:link", ATOM_NS)
            post_url = link.get("href") if link is not None else ""
            title = unescape(entry.findtext("a:title", "", ATOM_NS))
            if not post_url or post_url in posts:
                continue
            content = entry.findtext("a:content", "", ATOM_NS)
            posts[post_url] = Post(
                title=title,
                url=post_url,
                date=_parse_date(entry.findtext("a:updated", "", ATOM_NS)),
                text=f"{title} {_strip_html(content)}",
                source=f"reddit:r/{subreddit}",
            )
    return list(posts.values())


def fetch_hn_posts(query: str = HN_QUERY, days: int = 30) -> list[Post]:
    """Histórias do Hacker News via API pública do Algolia, filtradas por data."""
    since = int(time.time()) - days * 86400
    url = (
        "https://hn.algolia.com/api/v1/search_by_date"
        f"?query={quote(query)}&tags=story&hitsPerPage=50"
        f"&numericFilters={quote(f'created_at_i>{since}')}"
    )
    import json

    data = json.loads(_get(url).decode("utf-8"))
    posts: list[Post] = []
    for hit in data.get("hits", []):
        title = hit.get("title") or hit.get("story_title") or ""
        if not title:
            continue
        body = hit.get("story_text") or ""
        posts.append(
            Post(
                title=title,
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                date=_parse_date(hit.get("created_at")),
                text=f"{title} {_strip_html(body)}",
                source="hackernews",
            )
        )
    return posts


def fetch_blog_posts(days: int = 30) -> list[Post]:
    """Posts recentes do blog oficial da Cline (título + resumo)."""
    html = _get(BLOG_URL).decode("utf-8", errors="ignore")
    links = []
    for link in re.findall(r'href="(/blog/[^"]+)"', html):
        if link not in links and link != "/blog/archive":
            links.append(link)
    posts: list[Post] = []
    for link in links:
        try:
            page = _get("https://cline.bot" + link).decode("utf-8", errors="ignore")
        except Exception:
            continue
        title = re.search(r'<meta property="og:title" content="([^"]+)"', page)
        desc = re.search(r'<meta property="og:description" content="([^"]+)"', page)
        published = re.search(
            r'"datePublished"\s*:\s*"([^"]+)"|'
            r'<meta property="article:published_time" content="([^"]+)"',
            page,
        )
        date = _parse_date((published.group(1) or published.group(2)) if published else None)
        if not _is_recent(date, datetime.now(timezone.utc) - timedelta(days=days)):
            continue
        posts.append(
            Post(
                title=unescape(title.group(1)) if title else link,
                url="https://cline.bot" + link,
                date=date,
                text=unescape(
                    f"{title.group(1) if title else ''} {desc.group(1) if desc else ''}"
                ),
                source="cline-blog",
            )
        )
    return posts


def fetch_all_posts(days: int = 30) -> list[Post]:
    """Todas as fontes, deduplicadas por URL e filtradas pela janela de dias."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    collected: list[Post] = []
    for fetch in (fetch_reddit_posts, lambda: fetch_hn_posts(days=days),
                  lambda: fetch_blog_posts(days=days)):
        try:
            collected.extend(fetch())
        except Exception as exc:  # uma fonte fora do ar não derruba o app
            print(f"aviso: fonte indisponível ({fetch.__name__}): {exc}")
    seen: set[str] = set()
    unique: list[Post] = []
    for post in collected:
        if post.url in seen:
            continue
        seen.add(post.url)
        if _is_recent(post.date, cutoff):
            unique.append(post)
    return unique
