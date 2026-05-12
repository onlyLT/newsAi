import asyncio
from pathlib import Path
import pytest
from pipelines.render_video import screenshot_html, build_srt


def test_screenshot_html_produces_png(tmp_path):
    html = tmp_path / "page.html"
    html.write_text(
        "<html><body style='margin:0;background:#000;color:#fff;'>"
        "<div style='width:1920px;height:1080px;display:flex;align-items:center;justify-content:center;font-size:120px'>"
        "HELLO</div></body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "shot.png"
    asyncio.run(screenshot_html(html, out, width=1920, height=1080))
    assert out.exists()
    # PNG magic bytes
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_build_srt_formats_timestamps():
    segments = [
        {"id": "intro", "text": "各位早", "duration_s": 2.5},
        {"id": "item-1", "text": "第一条新闻：英伟达", "duration_s": 5.0},
    ]
    srt = build_srt(segments)
    lines = srt.splitlines()
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:02,500"
    assert lines[2] == "各位早"
    assert lines[5] == "00:00:02,500 --> 00:00:07,500"
    assert "第一条新闻：英伟达" in srt


def test_build_srt_splits_long_text_into_chunks():
    long_text = "第一句。" * 30  # very long, single segment
    segments = [{"id": "item-1", "text": long_text, "duration_s": 30.0}]
    srt = build_srt(segments, max_chars_per_cue=20)
    # should produce multiple cues
    cues = [b for b in srt.split("\n\n") if b.strip()]
    assert len(cues) > 1
