from datetime import datetime, timezone, timedelta
from pathlib import Path
from pipelines.ingest import load_sources

import respx
import httpx
from core.models import Lang, RawArticle, SourceType, SourceConfig
from pipelines.ingest import fetch_source


FIX = Path(__file__).parent / "fixtures"


def test_load_sources_from_yaml():
    sources = load_sources(FIX / "sample_sources.yaml")
    assert len(sources) == 2
    assert sources[0].id == "test_zh"
    assert sources[1].filter_keywords == ["AI", "LLM"]


@respx.mock
async def test_fetch_source_parses_rss():
    rss_body = (FIX / "sample_rss.xml").read_text(encoding="utf-8")
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=rss_body)
    )
    src = SourceConfig(
        id="t", name="T", type=SourceType.RSS,
        url="https://example.com/feed", lang=Lang.EN,
    )
    async with httpx.AsyncClient() as client:
        arts = await fetch_source(client, src)
    assert len(arts) == 2
    assert arts[0].title == "OpenAI releases GPT-7"
    assert arts[0].source_id == "t"
    assert arts[0].lang == Lang.EN
    assert len(arts[0].id) == 64  # sha256 hex


@respx.mock
async def test_fetch_source_applies_keyword_filter():
    rss_body = (FIX / "sample_rss.xml").read_text(encoding="utf-8")
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=rss_body)
    )
    src = SourceConfig(
        id="t", name="T", type=SourceType.RSS,
        url="https://example.com/feed", lang=Lang.EN,
        filter_keywords=["GPT", "OpenAI"],
    )
    async with httpx.AsyncClient() as client:
        arts = await fetch_source(client, src)
    assert len(arts) == 1
    assert "GPT" in arts[0].title


@respx.mock
async def test_fetch_source_returns_empty_on_http_error():
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(500))
    src = SourceConfig(
        id="t", name="T", type=SourceType.RSS,
        url="https://example.com/feed", lang=Lang.EN,
    )
    async with httpx.AsyncClient() as client:
        arts = await fetch_source(client, src)
    assert arts == []


from pipelines.ingest import dedupe, recent_only


def _make_article(idx: int, title: str, hours_ago: float = 1.0) -> RawArticle:
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return RawArticle(
        id=f"{idx:0>64x}",
        source_id="s",
        source_name="S",
        title=title,
        url=f"https://x/{idx}",
        published_at=ts,
        lang=Lang.EN,
    )


def test_dedupe_keeps_first_by_url():
    a = _make_article(1, "OpenAI releases GPT-7")
    b = _make_article(1, "OpenAI releases GPT-7 (duplicate)")  # same id
    out = dedupe([a, b])
    assert len(out) == 1
    assert out[0].title == "OpenAI releases GPT-7"


def test_dedupe_collapses_near_identical_titles():
    a = _make_article(1, "OpenAI releases GPT-7 today")
    b = _make_article(2, "OpenAI releases GPT 7 today")
    out = dedupe([a, b])
    assert len(out) == 1


def test_dedupe_keeps_unrelated():
    a = _make_article(1, "OpenAI releases GPT-7")
    b = _make_article(2, "Apple announces new chip")
    out = dedupe([a, b])
    assert len(out) == 2


def test_recent_only_filters_old():
    a = _make_article(1, "fresh", hours_ago=2)
    b = _make_article(2, "stale", hours_ago=30)
    out = recent_only([a, b], max_age_hours=24)
    assert len(out) == 1
    assert out[0].title == "fresh"
