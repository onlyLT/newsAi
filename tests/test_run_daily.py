import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from run_daily import main as run_main


def _setup_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    monkeypatch.setenv("MINIMAX_GROUP_ID", "x")
    monkeypatch.setenv("MINIMAX_VOICE_ID", "x")
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    # Copy channels/ and templates/ from real repo into the fake project root
    repo = Path(__file__).parent.parent
    for sub in ["templates", "channels", "assets"]:
        if (repo / sub).exists():
            shutil.copytree(repo / sub, tmp_path / sub, dirs_exist_ok=True)


def test_run_daily_invokes_each_stage_in_order(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)

    calls: list[str] = []

    async def fake_ingest(*a, **kw):
        calls.append("ingest")
        out = kw.get("out_path") or a[1]
        out.write_text("[]", encoding="utf-8")
        return out

    def fake_curate(**kw):
        calls.append("curate")
        kw["out_path"].write_text("[]", encoding="utf-8")
        return kw["out_path"]

    def fake_script(**kw):
        calls.append("script")
        kw["script_md_path"].write_text("# x", encoding="utf-8")
        kw["segments_path"].write_text("[]", encoding="utf-8")
        return kw["script_md_path"], kw["segments_path"]

    def fake_render_html(**kw):
        calls.append("render_html")
        kw["out_path"].write_text("<html></html>", encoding="utf-8")
        return kw["out_path"]

    async def fake_render_video(**kw):
        calls.append("render_video")
        out = kw["day_dir"] / "video.mp4"
        out.write_bytes(b"\x00" * 100)
        return out

    with patch("run_daily.ingest_run", new=fake_ingest), \
         patch("run_daily.curate_run", new=fake_curate), \
         patch("run_daily.script_run", new=fake_script), \
         patch("run_daily.html_render", new=fake_render_html), \
         patch("run_daily.video_run", new=fake_render_video), \
         patch("run_daily.notify"):
        rc = run_main(["--date", "2026-05-12", "--channel", "ai-invest"])
    assert rc == 0
    assert calls == ["ingest", "curate", "script", "render_html", "render_video"]


def test_run_daily_returns_nonzero_on_failure(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)

    async def boom_ingest(*a, **kw):
        raise RuntimeError("network down")

    with patch("run_daily.ingest_run", new=boom_ingest), \
         patch("run_daily.notify") as note:
        rc = run_main(["--date", "2026-05-12", "--channel", "ai-invest"])
    assert rc != 0
    note.assert_called()
    # Should notify with success=False
    assert note.call_args.kwargs.get("success") is False


def test_run_daily_multi_channel_continues_on_failure(monkeypatch, tmp_path):
    """When running all channels and one fails, the other still runs."""
    _setup_env(monkeypatch, tmp_path)

    calls: list[str] = []
    call_channels: list[str] = []

    async def fake_ingest(*a, **kw):
        # Determine which channel from the path: dist/{channel_id}/{date}/raw.json
        out_path = kw.get("out_path") or (a[1] if len(a) > 1 else None)
        if out_path:
            channel_from_path = out_path.parts[-3]  # dist/{ch}/{date}/raw.json
            call_channels.append(channel_from_path)
            if channel_from_path == "ai-invest":
                raise RuntimeError("ai-invest failed")
        calls.append("ingest")
        if out_path:
            out_path.write_text("[]", encoding="utf-8")
        return out_path

    def fake_curate(**kw):
        calls.append("curate")
        kw["out_path"].write_text("[]", encoding="utf-8")
        return kw["out_path"]

    def fake_script(**kw):
        calls.append("script")
        kw["script_md_path"].write_text("# x", encoding="utf-8")
        kw["segments_path"].write_text("[]", encoding="utf-8")

    def fake_render_html(**kw):
        calls.append("render_html")
        kw["out_path"].write_text("<html></html>", encoding="utf-8")

    async def fake_render_video(**kw):
        calls.append("render_video")
        out = kw["day_dir"] / "video.mp4"
        out.write_bytes(b"\x00" * 100)
        return out

    with patch("run_daily.ingest_run", new=fake_ingest), \
         patch("run_daily.curate_run", new=fake_curate), \
         patch("run_daily.script_run", new=fake_script), \
         patch("run_daily.html_render", new=fake_render_html), \
         patch("run_daily.video_run", new=fake_render_video), \
         patch("run_daily.notify"):
        # No --channel flag → runs all channels
        rc = run_main(["--date", "2026-05-12"])

    # Overall return code is non-zero because at least one channel failed
    assert rc != 0
    # Both channels were attempted (ai-invest fails, cn-finance proceeds)
    assert "ai-invest" in call_channels
    assert "cn-finance" in call_channels


@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="live smoke; set RUN_LIVE=1")
def test_smoke_full_pipeline_live(monkeypatch, tmp_path):
    """
    End-to-end against real Claude + MiniMax + local ffmpeg + Playwright.
    Costs ~¥2-3 per channel.
    Requires .env in repo root with real keys.
    """
    repo = Path(__file__).parent.parent
    for sub in ["templates", "channels", "assets"]:
        if (repo / sub).exists():
            shutil.copytree(repo / sub, tmp_path / sub, dirs_exist_ok=True)
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    # Real keys must come from .env
    rc = run_main(["--date", "2026-05-12", "--channel", "ai-invest"])
    assert rc == 0
    day = tmp_path / "dist" / "ai-invest" / "2026-05-12"
    assert (day / "raw.json").exists()
    assert (day / "curated.json").exists()
    assert (day / "script.md").exists()
    assert (day / "segments.json").exists()
    assert (day / "index.html").exists()
    assert (day / "video.mp4").exists()
    assert (day / "video.mp4").stat().st_size > 100_000
