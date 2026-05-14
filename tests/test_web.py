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
