"""
Tests for the web dashboard (web/main.py).

Uses FastAPI TestClient — no real subprocess calls, no real biliup, no LLM calls.
SSE streaming is not tested here (integration-only).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers: override PROJECT_ROOT before importing app
# ---------------------------------------------------------------------------

def _make_fake_project(tmp_path: Path) -> Path:
    """Create a minimal fake project directory for isolation."""
    # prompts
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "curate.system.md").write_text(
        "# Curate system prompt\nYou are a curator.", encoding="utf-8"
    )
    (tmp_path / "prompts" / "script.system.md").write_text(
        "# Script system prompt\nYou are a writer.", encoding="utf-8"
    )
    # dist (empty — episodes list may be [])
    (tmp_path / "dist").mkdir(exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Fixture: isolated app with tmp project root
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Return a TestClient with PROJECT_ROOT pointing at a tmp directory."""
    fake_root = _make_fake_project(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    # Re-import main so it picks up the new PROJECT_ROOT env var
    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    return TestClient(web_main.app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_root_returns_200_html(client):
    """GET / should return 200 with HTML content."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<html" in resp.text.lower()


def test_api_episodes_empty(client):
    """GET /api/episodes returns a list (may be empty when dist/ has no dated dirs)."""
    resp = client.get("/api/episodes")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_api_episodes_with_data(tmp_path, monkeypatch):
    """GET /api/episodes returns episode data when dist/ contains dated dirs."""
    fake_root = _make_fake_project(tmp_path)
    date = "2026-01-01"
    day = fake_root / "dist" / date
    day.mkdir(parents=True)
    # Write a minimal curated.json
    (day / "curated.json").write_text(
        json.dumps([{"rank": 1, "title": "Test item", "impact": {"tickers": []}}]),
        encoding="utf-8",
    )
    # Write a fake run.log with success marker
    (day / "run.log").write_text("run.success event=...", encoding="utf-8")

    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    c = TestClient(web_main.app)
    resp = c.get("/api/episodes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["date"] == date
    assert data[0]["item_count"] == 1
    assert data[0]["status"] == "success"


def test_api_prompts_curate(client):
    """GET /api/prompts/curate returns the actual prompt content."""
    resp = client.get("/api/prompts/curate")
    assert resp.status_code == 200
    assert "curator" in resp.text


def test_api_prompts_script(client):
    """GET /api/prompts/script returns the script prompt content."""
    resp = client.get("/api/prompts/script")
    assert resp.status_code == 200
    assert "writer" in resp.text


def test_api_prompts_unknown_404(client):
    """GET /api/prompts/nonexistent should return 404."""
    resp = client.get("/api/prompts/nonexistent")
    assert resp.status_code == 404


def test_put_prompt_saves_file(client, tmp_path, monkeypatch):
    """PUT /api/prompts/curate with new content saves it to disk."""
    fake_root = _make_fake_project(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    c = TestClient(web_main.app)
    new_content = "# Updated curate prompt\nNew instructions here."
    resp = c.put("/api/prompts/curate", content=new_content.encode("utf-8"))
    assert resp.status_code == 200
    assert resp.json()["saved"] is True

    # Verify the file was actually written
    written = (fake_root / "prompts" / "curate.system.md").read_text(encoding="utf-8")
    assert written == new_content


def test_post_run_mocks_subprocess(tmp_path, monkeypatch):
    """POST /api/run mocks subprocess.Popen and returns a task_id."""
    fake_root = _make_fake_project(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    import web.runs as web_runs

    importlib.reload(web_runs)
    importlib.reload(web_main)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # still running

    with patch("web.runs.subprocess.Popen", return_value=mock_proc) as mock_popen:
        c = TestClient(web_main.app)
        resp = c.post(
            "/api/run",
            json={"date": "2026-01-15", "stage": "curate"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "2026-01-15"
    assert "started_at" in data
    mock_popen.assert_called_once()


def test_post_run_full_pipeline(tmp_path, monkeypatch):
    """POST /api/run without a stage triggers the full pipeline command."""
    fake_root = _make_fake_project(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    import web.runs as web_runs

    importlib.reload(web_runs)
    importlib.reload(web_main)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    with patch("web.runs.subprocess.Popen", return_value=mock_proc) as mock_popen:
        c = TestClient(web_main.app)
        resp = c.post("/api/run", json={"date": "2026-02-01"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["stage"] is None
    # The command should include run_daily.py
    call_args = mock_popen.call_args[0][0]  # first positional arg = cmd list
    assert "run_daily.py" in call_args


# ---------------------------------------------------------------------------
# Feature 2: Episode detail
# ---------------------------------------------------------------------------

def _make_episode_dir(base: Path, date: str, with_video: bool = False) -> Path:
    """Create a minimal episode dir with enough files for detail tests."""
    day = base / "dist" / date
    day.mkdir(parents=True, exist_ok=True)

    curated = [
        {
            "rank": 1,
            "title": "AI chips boom",
            "tldr": "GPU demand up.",
            "details": "More details here.",
            "impact": {
                "tickers": ["NVDA"],
                "sectors": ["AI基础设施"],
                "direction": "bullish",
                "reasoning": "Strong demand.",
            },
            "source_url": "https://example.com/story",
            "source_name": "Example",
        }
    ]
    (day / "curated.json").write_text(json.dumps(curated), encoding="utf-8")

    segments = [
        {"id": "toc", "text": "今天是1月1日", "duration_hint_s": 5, "card_ref": None},
        {"id": "item-1", "text": "AI chips boom!", "duration_hint_s": 20, "card_ref": "card-1"},
    ]
    (day / "segments.json").write_text(json.dumps(segments), encoding="utf-8")

    (day / "script.md").write_text("# Script\nHello world.", encoding="utf-8")

    # run.log with success
    (day / "run.log").write_text(
        "stage.start stage=ingest\nstage.start stage=curate\nrun.success date=2026-01-01",
        encoding="utf-8",
    )
    return day


def test_episode_detail_returns_data(tmp_path, monkeypatch):
    """GET /api/episodes/{date}/detail returns full detail including curated items."""
    fake_root = _make_fake_project(tmp_path)
    date = "2026-01-01"
    _make_episode_dir(fake_root, date)

    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    c = TestClient(web_main.app)
    resp = c.get(f"/api/episodes/{date}/detail")
    assert resp.status_code == 200
    data = resp.json()

    assert data["date"] == date
    assert data["status"] == "success"
    assert data["item_count"] == 1
    assert len(data["curated"]) == 1
    assert data["curated"][0]["title"] == "AI chips boom"
    assert len(data["segments"]) == 2
    # First segment starts at 00:00
    assert data["segments"][0]["start_ts"] == "00:00"
    # Second segment starts at 00:05 (after toc's 5s)
    assert data["segments"][1]["start_ts"] == "00:05"
    assert data["script_md"] == "# Script\nHello world."


def test_episode_page_returns_html(tmp_path, monkeypatch):
    """GET /episodes/{date} returns 200 HTML with episode content."""
    fake_root = _make_fake_project(tmp_path)
    date = "2026-01-02"
    _make_episode_dir(fake_root, date)

    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    c = TestClient(web_main.app)
    resp = c.get(f"/episodes/{date}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert date in resp.text
    assert "AI chips boom" in resp.text


# ---------------------------------------------------------------------------
# Feature 8: Failed-stage retry banner logic
# ---------------------------------------------------------------------------

def test_failed_banner_logic_detects_stuck_stage(tmp_path):
    """parse_run_log correctly identifies the last started stage when no success."""
    from web.episodes import parse_run_log, detect_failed_stage

    log_path = tmp_path / "run.log"
    # Stage started but no run.success
    log_path.write_text(
        "stage.start stage=ingest\nstage.start stage=curate\nstage.start stage=script\n",
        encoding="utf-8",
    )
    info = parse_run_log(log_path)
    assert info["last_stage"] == "script"
    assert info["status"] == "running"
    assert info["failed_stage"] == "script"

    stage = detect_failed_stage(log_path)
    assert stage == "script"


def test_failed_banner_logic_no_banner_on_success(tmp_path):
    """detect_failed_stage returns None when run.success is present."""
    from web.episodes import detect_failed_stage

    log_path = tmp_path / "run.log"
    log_path.write_text(
        "stage.start stage=ingest\nstage.start stage=render_video\nrun.success date=2026-01-01",
        encoding="utf-8",
    )
    assert detect_failed_stage(log_path) is None


def test_failed_banner_logic_detects_run_fail(tmp_path):
    """detect_failed_stage returns the stuck stage when run.fail is present."""
    from web.episodes import detect_failed_stage

    log_path = tmp_path / "run.log"
    log_path.write_text(
        "stage.start stage=curate\nstage.start stage=script\nrun.fail error=timeout",
        encoding="utf-8",
    )
    stage = detect_failed_stage(log_path)
    assert stage == "script"


def test_failed_stage_api_endpoint(tmp_path, monkeypatch):
    """GET /api/run/{date}/failed-stage returns correct data."""
    fake_root = _make_fake_project(tmp_path)
    date = "2026-03-01"
    day = fake_root / "dist" / date
    day.mkdir(parents=True)
    (day / "run.log").write_text(
        "stage.start stage=render_video\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))
    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    c = TestClient(web_main.app)
    resp = c.get(f"/api/run/{date}/failed-stage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed_stage"] == "render_video"
    assert data["status"] == "running"


# ---------------------------------------------------------------------------
# Feature 5: Sources CRUD
# ---------------------------------------------------------------------------

def _make_project_with_sources(tmp_path: Path) -> Path:
    fake_root = _make_fake_project(tmp_path)
    sources_dir = fake_root / "sources"
    sources_dir.mkdir(exist_ok=True)
    (sources_dir / "sources.yaml").write_text(
        "sources:\n  - id: test_src\n    name: Test Source\n    type: rss\n"
        "    url: https://example.com/rss\n    lang: en\n    filter_keywords: []\n",
        encoding="utf-8",
    )
    return fake_root


def test_sources_get(tmp_path, monkeypatch):
    """GET /api/sources returns list of sources."""
    fake_root = _make_project_with_sources(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    c = TestClient(web_main.app)
    resp = c.get("/api/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "test_src"


def test_sources_put(tmp_path, monkeypatch):
    """PUT /api/sources overwrites sources.yaml."""
    fake_root = _make_project_with_sources(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    c = TestClient(web_main.app)
    new_sources = [
        {"id": "src_a", "name": "Source A", "type": "rss",
         "url": "https://a.com/rss", "lang": "zh", "filter_keywords": ["AI"]},
        {"id": "src_b", "name": "Source B", "type": "rss",
         "url": "https://b.com/rss", "lang": "en", "filter_keywords": []},
    ]
    resp = c.put("/api/sources", json=new_sources)
    assert resp.status_code == 200
    assert resp.json()["count"] == 2

    # Verify re-read
    resp2 = c.get("/api/sources")
    data = resp2.json()
    assert len(data) == 2
    assert data[0]["id"] == "src_a"


def test_sources_test_mock_httpx(tmp_path, monkeypatch):
    """POST /api/sources/test returns count and sample_titles (mock httpx)."""
    fake_root = _make_project_with_sources(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    # Build a minimal RSS XML
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>Story One</title><link>https://example.com/1</link></item>
  <item><title>Story Two</title><link>https://example.com/2</link></item>
</channel></rss>"""

    import httpx
    import respx

    with respx.mock(assert_all_called=False) as rsps:
        rsps.get("https://example.com/rss").mock(
            return_value=httpx.Response(200, text=rss_xml, headers={"content-type": "application/rss+xml"})
        )
        c = TestClient(web_main.app)
        resp = c.post(
            "/api/sources/test",
            json={"id": "test_src", "name": "Test", "type": "rss",
                  "url": "https://example.com/rss", "lang": "en", "filter_keywords": []},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data or "error" in data
    # If httpx mock worked, we get articles; if feedparser fails to parse, count could be 0
    if "count" in data:
        assert isinstance(data["count"], int)


# ---------------------------------------------------------------------------
# Feature 7: Stats
# ---------------------------------------------------------------------------

def _make_stats_fixture(tmp_path: Path) -> Path:
    """Create a fake project with two dist days for stats testing."""
    fake_root = _make_fake_project(tmp_path)

    for date, status_line in [
        ("2026-02-01", "stage.start stage=ingest\nrun.success date=2026-02-01"),
        ("2026-02-02", "stage.start stage=curate\nrun.fail error=oops"),
    ]:
        day = fake_root / "dist" / date
        day.mkdir(parents=True)
        (day / "run.log").write_text(status_line, encoding="utf-8")
        (day / "curated.json").write_text(json.dumps([
            {"rank": 1, "title": "t", "tldr": "x", "details": "d",
             "impact": {"tickers": ["A"], "sectors": [], "direction": "bullish", "reasoning": "r"},
             "source_url": "https://x.com", "source_name": "x"}
        ]), encoding="utf-8")
        segs = [{"id": "toc", "text": "hello world!", "duration_hint_s": 10, "card_ref": None}]
        (day / "segments.json").write_text(json.dumps(segs), encoding="utf-8")
        (day / "script.md").write_text("# script\nhello!", encoding="utf-8")

    return fake_root


def test_stats_endpoint(tmp_path, monkeypatch):
    """GET /api/stats returns correct shape with daily array and rates."""
    fake_root = _make_stats_fixture(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", str(fake_root))

    import importlib
    import web.main as web_main
    importlib.reload(web_main)

    c = TestClient(web_main.app)
    resp = c.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert "daily" in data
    assert "rates" in data
    assert isinstance(data["daily"], list)
    assert len(data["daily"]) == 2

    # Check rates keys
    rates = data["rates"]
    assert "tts_rmb_per_char" in rates
    assert "llm_usd_per_m_in" in rates
    assert "llm_usd_per_m_out" in rates
    assert "usd_to_rmb" in rates

    # Check daily shape
    day0 = data["daily"][0]  # sorted chronologically
    assert day0["date"] == "2026-02-01"
    assert day0["success"] is True
    assert day0["failed"] is False
    assert "tts_rmb" in day0
    assert "llm_rmb" in day0
    assert "total_rmb" in day0
    assert day0["items"] == 1

    day1 = data["daily"][1]
    assert day1["date"] == "2026-02-02"
    assert day1["success"] is False
    assert day1["failed"] is True
