"""Tests for pipelines/cover.py — colour block detection + text overlay."""
from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path
from PIL import Image

from pipelines.cover import (
    _detect_block,
    _hook,
    _resize_to_canvas,
    compose_cover,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_frame(tmp_path: Path) -> Path:
    """Synthesize a 1672x941 frame with known purple + gold blocks for testing."""
    im = Image.new("RGB", (1672, 941), (20, 30, 50))
    # Purple block at x=[60,660), y=[290,460)  — colour ~#a855f7
    purple = (168, 85, 247)
    for y in range(290, 460):
        for x in range(60, 660):
            im.putpixel((x, y), purple)
    # Gold block at x=[130,810), y=[500,680)  — colour ~#fbbf24
    gold = (251, 191, 36)
    for y in range(500, 680):
        for x in range(130, 810):
            im.putpixel((x, y), gold)
    p = tmp_path / "frame.png"
    im.save(p)
    return p


# ---------------------------------------------------------------------------
# _detect_block
# ---------------------------------------------------------------------------

def test_detect_purple_block(tmp_path: Path):
    frame = _make_test_frame(tmp_path)
    rgb = np.array(Image.open(frame).convert("RGB"))
    box = _detect_block(rgb, hue_lo=260, hue_hi=295, s_min=0.4, v_min=0.4)
    assert box is not None, "purple block should be detected"
    l, t, r, b = box
    # Should roughly match (60, 290, 660, 460) with 2/98 pct trim
    assert 50 <= l <= 100,  f"left={l}"
    assert 280 <= t <= 310, f"top={t}"
    assert 600 <= r <= 680, f"right={r}"
    assert 440 <= b <= 480, f"bottom={b}"


def test_detect_gold_block(tmp_path: Path):
    frame = _make_test_frame(tmp_path)
    rgb = np.array(Image.open(frame).convert("RGB"))
    box = _detect_block(rgb, hue_lo=35, hue_hi=58, s_min=0.5, v_min=0.6)
    assert box is not None, "gold block should be detected"
    l, t, r, b = box
    # Should roughly match (130, 500, 810, 680) with 2/98 pct trim
    assert 100 <= l <= 180, f"left={l}"
    assert 490 <= t <= 530, f"top={t}"
    assert 750 <= r <= 850, f"right={r}"
    assert 660 <= b <= 700, f"bottom={b}"


def test_detect_block_returns_none_when_absent(tmp_path: Path):
    """Blank image has no saturated colours — should return None."""
    im = Image.new("RGB", (400, 300), (128, 128, 128))
    rgb = np.array(im)
    box = _detect_block(rgb, hue_lo=260, hue_hi=295, s_min=0.4, v_min=0.4)
    assert box is None


# ---------------------------------------------------------------------------
# compose_cover
# ---------------------------------------------------------------------------

def test_compose_cover_produces_1920x1080(tmp_path: Path):
    frame = _make_test_frame(tmp_path)
    out = tmp_path / "cover.png"
    compose_cover(frame, out, text_top="测试", text_bottom="测试标题")
    assert out.exists(), "cover.png should be created"
    im = Image.open(out)
    assert im.size == (1920, 1080), f"expected 1920x1080, got {im.size}"


# ---------------------------------------------------------------------------
# _hook
# ---------------------------------------------------------------------------

def test_hook_first_clause():
    assert _hook("英伟达发布新GPU，性能提升30%") == "英伟达发布新GPU"


def test_hook_no_comma_short():
    assert _hook("没有逗号的短标题") == "没有逗号的短标题"


def test_hook_no_comma_long_truncates():
    result = _hook("非常非常非常非常非常长的没有逗号的标题")
    assert result.endswith("…")
    # Max 14 chars before ellipsis
    assert len(result) <= 15


# ---------------------------------------------------------------------------
# _resize_to_canvas
# ---------------------------------------------------------------------------

def test_resize_to_canvas_exact_16_9():
    """A 1920x1080 image should pass through unchanged in size."""
    im = Image.new("RGB", (1920, 1080), (0, 0, 0))
    out = _resize_to_canvas(im)
    assert out.size == (1920, 1080)


def test_resize_to_canvas_letterbox():
    """The ai-invest frame (1672x941) has nearly the same ratio — direct resize."""
    im = Image.new("RGB", (1672, 941), (0, 0, 0))
    out = _resize_to_canvas(im)
    assert out.size == (1920, 1080)
