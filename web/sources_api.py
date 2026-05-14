"""
Sources CRUD helpers for the web dashboard.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_sources(yaml_path: Path) -> list[dict]:
    """Return list of source dicts from sources.yaml."""
    if not yaml_path.exists():
        return []
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not data or "sources" not in data:
        return []
    return data["sources"] or []


def save_sources(yaml_path: Path, sources: list[dict]) -> None:
    """Overwrite sources.yaml with the given list of source dicts."""
    content = yaml.dump(
        {"sources": sources},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    yaml_path.write_text(content, encoding="utf-8")


async def test_fetch_source(src: dict) -> dict:
    """
    Attempt to fetch the source URL and return
    {'count': N, 'sample_titles': [...]} or {'error': '...'}.

    Imports ingest helpers at call time so they're easy to mock in tests.
    """
    import feedparser
    import httpx

    url = src.get("url", "")
    filter_keywords: list[str] = src.get("filter_keywords") or []

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=20.0, follow_redirects=True)
            resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        titles: list[str] = []
        for entry in feed.entries:
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            if filter_keywords:
                lower = title.lower()
                if not any(k.lower() in lower for k in filter_keywords):
                    continue
            titles.append(title)
        return {"count": len(titles), "sample_titles": titles[:5]}
    except Exception as exc:
        return {"error": str(exc)}
