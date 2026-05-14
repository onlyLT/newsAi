"""Tests for pipelines/publish.py — metadata building and dry-run behavior."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pipelines.publish import _build_metadata, run as publish_run


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_item(rank: int, title: str, tickers: list[str]) -> dict:
    return {
        "rank": rank,
        "title": title,
        "tldr": "tldr",
        "details": "details",
        "impact": {
            "tickers": tickers,
            "sectors": [],
            "direction": "bullish",
            "reasoning": "r",
        },
        "source_url": "https://example.com",
        "source_name": "Test",
    }


THREE_ITEMS = [
    _make_item(1, "英伟达发布新GPU", ["NVDA"]),
    _make_item(2, "苹果进军AI硬件", ["AAPL"]),
    _make_item(3, "微软发布Copilot更新", ["MSFT"]),
]

EIGHT_ITEMS_LONG = [
    _make_item(1, "超长公司名称测试一号新闻，包含非常详细的描述", ["NVDA"]),
    _make_item(2, "超长公司名称测试二号新闻，更长的标题内容测试", ["AAPL"]),
    _make_item(3, "超长公司名称测试三号新闻，再长一些来测试截断", ["MSFT"]),
    _make_item(4, "超长公司名称测试四号新闻，加上更多内容", ["GOOG"]),
    _make_item(5, "超长公司名称测试五号新闻，继续填充", ["META"]),
    _make_item(6, "超长公司名称测试六号新闻，数量已够", ["AMZN"]),
    _make_item(7, "超长公司名称测试七号新闻，再添一条", ["TSLA"]),
    _make_item(8, "超长公司名称测试八号新闻，最后一条", ["BABA"]),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildMetadataBasic:
    """_build_metadata with a simple 3-item curated list."""

    def setup_method(self):
        self.meta = _build_metadata(THREE_ITEMS, "2026-05-14", episode=3)

    def test_title_length_within_limit(self):
        assert len(self.meta["title"]) <= 80, (
            f"Title too long ({len(self.meta['title'])}): {self.meta['title']}"
        )

    def test_title_contains_date(self):
        # Title format is "{M}/{D} 早报｜..."
        assert "5/14" in self.meta["title"]
        assert "早报" in self.meta["title"]

    def test_title_has_at_least_one_company(self):
        # At least one known company name should appear
        known = ["英伟达", "苹果", "微软", "谷歌", "Meta", "亚马逊"]
        found = any(c in self.meta["title"] for c in known)
        assert found, f"No company found in title: {self.meta['title']}"

    def test_desc_length_within_limit(self):
        assert len(self.meta["desc"]) <= 250, (
            f"Desc too long ({len(self.meta['desc'])}): {self.meta['desc']}"
        )

    def test_desc_includes_all_three_titles(self):
        for item in THREE_ITEMS:
            assert item["title"] in self.meta["desc"], (
                f"Title '{item['title']}' not found in desc"
            )

    def test_tag_count_within_limit(self):
        tags = self.meta["tag"].split(",")
        assert len(tags) <= 12, f"Too many tags ({len(tags)}): {self.meta['tag']}"

    def test_tag_each_within_20_chars(self):
        for t in self.meta["tag"].split(","):
            assert len(t) <= 20, f"Tag too long: {t!r}"

    def test_tid_is_188(self):
        assert self.meta["tid"] == 188

    def test_copyright_is_1(self):
        assert self.meta["copyright"] == 1


class TestBuildMetadataTruncatesLongTitle:
    """With 8 items having long titles/many companies, title must still be ≤ 80."""

    def test_title_still_within_limit(self):
        meta = _build_metadata(EIGHT_ITEMS_LONG, "2026-05-14", episode=8)
        assert len(meta["title"]) <= 80, (
            f"Title too long ({len(meta['title'])}): {meta['title']}"
        )

    def test_title_still_contains_date(self):
        meta = _build_metadata(EIGHT_ITEMS_LONG, "2026-05-14", episode=8)
        assert "5/14" in meta["title"]

    def test_tag_count_within_limit_with_many_items(self):
        meta = _build_metadata(EIGHT_ITEMS_LONG, "2026-05-14", episode=8)
        tags = meta["tag"].split(",")
        assert len(tags) <= 12


class TestPublishRunDryRun:
    """publish.run with dry_run=True must not invoke biliup and must write publish.json."""

    def test_dry_run_does_not_invoke_biliup(self, tmp_path):
        curated_path = tmp_path / "curated.json"
        curated_path.write_text(
            json.dumps(THREE_ITEMS, ensure_ascii=False), encoding="utf-8"
        )
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"\x00" * 16)  # fake mp4

        with patch("pipelines.publish.subprocess.run") as mock_sub:
            meta = publish_run(
                video_path=video_path,
                curated_path=curated_path,
                date="2026-05-14",
                episode=3,
                dry_run=True,
            )
            mock_sub.assert_not_called()

        # publish.json must be written
        publish_json = tmp_path / "publish.json"
        assert publish_json.exists(), "publish.json not written in dry-run mode"
        written = json.loads(publish_json.read_text(encoding="utf-8"))
        assert written["title"] == meta["title"]

    def test_dry_run_returns_valid_metadata(self, tmp_path):
        curated_path = tmp_path / "curated.json"
        curated_path.write_text(
            json.dumps(THREE_ITEMS, ensure_ascii=False), encoding="utf-8"
        )
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"\x00" * 16)

        meta = publish_run(
            video_path=video_path,
            curated_path=curated_path,
            date="2026-05-14",
            episode=3,
            dry_run=True,
        )
        assert "title" in meta
        assert "desc" in meta
        assert "tag" in meta
        assert len(meta["title"]) <= 80
        assert len(meta["desc"]) <= 250
