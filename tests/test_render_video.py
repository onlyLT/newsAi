import asyncio
import shutil
import subprocess
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
from pipelines.render_video import screenshot_html, build_srt, assemble_video


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


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not on PATH")
def test_assemble_video_produces_mp4(tmp_path):
    import asyncio
    # 2 simple frames + 2 tiny silent mp3s (generated with ffmpeg directly)
    frame1 = tmp_path / "f1.png"
    frame2 = tmp_path / "f2.png"
    a1 = tmp_path / "a1.mp3"
    a2 = tmp_path / "a2.mp3"
    srt = tmp_path / "subs.srt"
    out = tmp_path / "video.mp4"

    # Create solid color PNGs via ffmpeg
    for f, color in [(frame1, "red"), (frame2, "blue")]:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1920x1080:d=0.1",
             "-frames:v", "1", str(f)], check=True, capture_output=True,
        )
    # Create 1s silent mp3
    for a in [a1, a2]:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=cl=mono:r=32000",
             "-t", "1", str(a)], check=True, capture_output=True,
        )
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nhello\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nworld\n",
        encoding="utf-8",
    )

    segments = [
        {"frame": frame1, "audio": a1, "duration_s": 1.0},
        {"frame": frame2, "audio": a2, "duration_s": 1.0},
    ]
    asyncio.run(assemble_video(segments=segments, srt_path=srt, out_path=out, bgm_path=None))
    assert out.exists()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not on PATH")
def test_render_video_run_end_to_end(tmp_path, monkeypatch):
    """Run with mocked TTS + real Playwright + real ffmpeg."""
    import json, asyncio, shutil
    # Layout: copy templates to tmp
    repo = Path(__file__).parent.parent
    (tmp_path / "templates").mkdir()
    for f in ["index.html.j2", "_card.html.j2", "styles.css"]:
        shutil.copyfile(repo / "templates" / f, tmp_path / "templates" / f)
    # curated.json fixture (2 items for speed)
    curated = [
        {"rank": 1, "title": "A", "tldr": "测试一", "details": "细节",
         "impact": {"tickers": ["NVDA"], "sectors": [], "direction": "bullish", "reasoning": "r"},
         "source_url": "u", "source_name": "n"},
        {"rank": 2, "title": "B", "tldr": "测试二", "details": "细节",
         "impact": {"tickers": ["TSM"], "sectors": [], "direction": "bearish", "reasoning": "r"},
         "source_url": "u", "source_name": "n"},
    ]
    day = tmp_path / "dist" / "2026-05-12"
    day.mkdir(parents=True)
    (day / "curated.json").write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")
    segs = [
        {"id": "intro", "text": "开场", "duration_hint_s": 2},
        {"id": "item-1", "text": "第一条", "duration_hint_s": 2, "card_ref": "card-1"},
        {"id": "item-2", "text": "第二条", "duration_hint_s": 2, "card_ref": "card-2"},
        {"id": "outro", "text": "拜拜", "duration_hint_s": 2},
    ]
    (day / "segments.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")

    # Mock TTS: each call writes a 1s silent mp3 and returns 1.0
    def fake_synth(text, out_path, **kw):
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=cl=mono:r=32000",
             "-t", "1", str(out_path)], check=True, capture_output=True,
        )
        return 1.0

    fake_tts = MagicMock()
    fake_tts.synthesize.side_effect = fake_synth

    from pipelines.render_video import run as run_video
    with patch("pipelines.render_video.MiniMaxTTS", return_value=fake_tts):
        asyncio.run(run_video(
            day_dir=day,
            templates_dir=tmp_path / "templates",
            tts_api_key="k", tts_group_id="g", tts_voice_id="v",
            bgm_path=None,
            date="2026-05-12", episode=1,
        ))
    assert (day / "video.mp4").exists()
    assert (day / "video.mp4").stat().st_size > 5000
