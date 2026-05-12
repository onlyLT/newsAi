import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import structlog
import yaml
from dateutil import parser as dtparser
from rapidfuzz import fuzz

_log = structlog.get_logger(__name__)

from core.models import RawArticle, SourceConfig


def load_sources(yaml_path: Path) -> list[SourceConfig]:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return [SourceConfig.model_validate(s) for s in data["sources"]]


def _hash_url(url: str) -> str:
    norm = url.strip().rstrip("/").lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


def _parse_pubdate(entry) -> datetime:
    raw = entry.get("published") or entry.get("updated") or ""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        d = dtparser.parse(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


async def fetch_source(client: httpx.AsyncClient, src: SourceConfig) -> list[RawArticle]:
    try:
        resp = await client.get(src.url, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        _log.warning("ingest.fetch_failed", source_id=src.id, url=src.url, error=repr(exc))
        return []
    feed = feedparser.parse(resp.text)
    articles: list[RawArticle] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = (entry.get("summary") or "").strip()
        haystack = f"{title}\n{summary}"
        if not _matches_keywords(haystack, src.filter_keywords):
            continue
        articles.append(RawArticle(
            id=_hash_url(link),
            source_id=src.id,
            source_name=src.name,
            title=title,
            url=link,
            published_at=_parse_pubdate(entry),
            summary=summary,
            content="",
            lang=src.lang,
        ))
    return articles


def dedupe(articles: list[RawArticle], title_threshold: int = 85) -> list[RawArticle]:
    seen_ids: set[str] = set()
    kept: list[RawArticle] = []
    for art in articles:
        if art.id in seen_ids:
            continue
        # title fuzzy check
        is_dup = False
        for k in kept:
            if k.lang == art.lang and fuzz.ratio(k.title, art.title) >= title_threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(art)
            seen_ids.add(art.id)
    return kept


def recent_only(articles: list[RawArticle], max_age_hours: int = 24) -> list[RawArticle]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return [a for a in articles if a.published_at >= cutoff]


async def run(sources_yaml: Path, out_path: Path, max_age_hours: int = 24) -> Path:
    sources = load_sources(sources_yaml)
    async with httpx.AsyncClient(http2=True) as client:
        results = await asyncio.gather(*[fetch_source(client, s) for s in sources])
    all_articles = [a for r in results for a in r]
    all_articles = recent_only(all_articles, max_age_hours=max_age_hours)
    all_articles = dedupe(all_articles)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([a.model_dump(mode="json") for a in all_articles],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def main():
    from core.config import Settings, day_dir, today_str
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYY-MM-DD; default=today")
    parser.add_argument("--max-age-hours", type=int, default=24)
    args = parser.parse_args()
    settings = Settings()
    date = args.date or today_str(settings.timezone)
    d = day_dir(settings, date)
    out = d / "raw.json"
    path = asyncio.run(run(settings.sources_yaml, out, args.max_age_hours))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
