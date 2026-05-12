from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from core.models import (
    Lang, SourceType, SourceConfig,
    RawArticle, Direction, Impact, CuratedItem,
    Segment, RunArtifacts,
)


def test_source_config_round_trip():
    s = SourceConfig(
        id="techcrunch_ai",
        name="TechCrunch AI",
        type=SourceType.RSS,
        url="https://example.com/rss",
        lang=Lang.EN,
    )
    assert s.id == "techcrunch_ai"
    assert s.filter_keywords == []


def test_raw_article_requires_iso_datetime():
    art = RawArticle(
        id="a" * 64,
        source_id="x",
        source_name="X",
        title="t",
        url="https://x.com/1",
        published_at=datetime(2026, 5, 12, 3, 0, tzinfo=timezone.utc),
        lang=Lang.EN,
    )
    assert art.summary == ""
    assert art.content == ""


def test_curated_item_requires_at_least_one_target():
    # Either tickers or sectors must be non-empty
    with pytest.raises(ValidationError):
        CuratedItem(
            rank=1,
            title="t",
            tldr="x",
            details="y",
            impact=Impact(
                tickers=[],
                sectors=[],
                direction=Direction.BULLISH,
                reasoning="r",
            ),
            source_url="https://x",
            source_name="X",
        )


def test_curated_item_accepts_tickers_only():
    item = CuratedItem(
        rank=1,
        title="t",
        tldr="x",
        details="y",
        impact=Impact(
            tickers=["NVDA"],
            sectors=[],
            direction=Direction.BULLISH,
            reasoning="r",
        ),
        source_url="https://x",
        source_name="X",
    )
    assert item.impact.tickers == ["NVDA"]


def test_segment_id_format():
    seg = Segment(id="item-3", text="hello", duration_hint_s=20, card_ref="card-3")
    assert seg.id == "item-3"
