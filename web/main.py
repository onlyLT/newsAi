"""
FastAPI web dashboard for the AI News pipeline.

Run:
    uvicorn web.main:app --port 8765 --reload
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from web.runs import start_run, run_status, is_running, tail_log

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
DIST_DIR = PROJECT_ROOT / "dist"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
PYTHON_EXE = str(Path(sys.executable))

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="NewsAI Dashboard")

# Mount dist/ so video.mp4, index.html, frames/*.png are served directly
if DIST_DIR.exists():
    app.mount("/dist", StaticFiles(directory=str(DIST_DIR)), name="dist")

_web_dir = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(_web_dir / "static")), name="static")

templates = Jinja2Templates(directory=str(_web_dir / "templates"))


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _parse_log_status(log_path: Path) -> str:
    """Read run.log and return 'success', 'failed', or 'unknown'."""
    if not log_path.exists():
        return "unknown"
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if "run.success" in text:
        return "success"
    if "run.fail" in text:
        return "failed"
    return "unknown"


def _video_size_kb(day: Path) -> Optional[int]:
    v = day / "video.mp4"
    if v.exists():
        return v.stat().st_size // 1024
    return None


def _item_count(day: Path) -> Optional[int]:
    c = day / "curated.json"
    if c.exists():
        try:
            return len(json.loads(c.read_text(encoding="utf-8")))
        except Exception:
            pass
    return None


def _bvid(day: Path) -> Optional[str]:
    p = day / "publish.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("bvid") or data.get("BV") or None
        except Exception:
            pass
    return None


def _episode_summary(day: Path) -> dict:
    date = day.name
    return {
        "date": date,
        "video_size_kb": _video_size_kb(day),
        "item_count": _item_count(day),
        "status": _parse_log_status(day / "run.log"),
        "bvid": _bvid(day),
        "has_video": (day / "video.mp4").exists(),
        "has_html": (day / "index.html").exists(),
        "has_cover": (day / "frames" / "toc.png").exists(),
    }


def _list_episodes(limit: int = 30) -> list[dict]:
    if not DIST_DIR.exists():
        return []
    days = sorted(
        [d for d in DIST_DIR.iterdir() if d.is_dir() and d.name[0].isdigit()],
        key=lambda d: d.name,
        reverse=True,
    )[:limit]
    return [_episode_summary(d) for d in days]


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    from core.config import today_str
    today = today_str()
    episodes = _list_episodes(30)
    today_ep = next((e for e in episodes if e["date"] == today), None)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "today": today,
            "today_ep": today_ep,
            "episodes": episodes,
        },
    )


# ---------------------------------------------------------------------------
# API: Episodes
# ---------------------------------------------------------------------------

@app.get("/api/episodes")
async def list_episodes():
    return _list_episodes(30)


@app.get("/api/episodes/{date}")
async def episode_detail(date: str):
    day = DIST_DIR / date
    if not day.exists():
        raise HTTPException(status_code=404, detail="Episode not found")
    summary = _episode_summary(day)
    # Add ranked items list
    items: list[dict] = []
    c = day / "curated.json"
    if c.exists():
        try:
            raw = json.loads(c.read_text(encoding="utf-8"))
            items = [{"rank": i.get("rank", idx + 1), "title": i.get("title", "")}
                     for idx, i in enumerate(raw)]
        except Exception:
            pass
    summary["items"] = items
    return summary


# ---------------------------------------------------------------------------
# API: Run trigger
# ---------------------------------------------------------------------------

VALID_STAGES = {"ingest", "curate", "script", "render_html", "render_video", "publish"}


@app.post("/api/run")
async def trigger_run(body: dict = Body(...)):
    date: str = body.get("date", "")
    stage: Optional[str] = body.get("stage")

    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    if stage and stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")
    if is_running(date):
        raise HTTPException(status_code=409, detail=f"Run for {date} already in progress")

    if stage:
        cmd = [PYTHON_EXE, "-m", f"pipelines.{stage}", "--date", date]
    else:
        cmd = [PYTHON_EXE, "run_daily.py", "--date", date]

    start_run(date, cmd, PROJECT_ROOT)
    return {"task_id": date, "started_at": datetime.now(timezone.utc).isoformat(), "stage": stage}


@app.get("/api/run/status")
async def get_run_status():
    return run_status()


@app.get("/api/run/{date}/log/stream")
async def stream_log(date: str, request: Request):
    log_path = DIST_DIR / date / "run.log"

    async def event_generator():
        async for line in tail_log(log_path):
            if await request.is_disconnected():
                break
            yield {"data": line}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# API: Prompts
# ---------------------------------------------------------------------------

PROMPT_FILES = {
    "curate": "curate.system.md",
    "script": "script.system.md",
}


@app.get("/api/prompts/{name}")
async def get_prompt(name: str):
    if name not in PROMPT_FILES:
        raise HTTPException(status_code=404, detail="Unknown prompt name")
    path = PROMPTS_DIR / PROMPT_FILES[name]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Prompt file not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.put("/api/prompts/{name}")
async def save_prompt(name: str, request: Request):
    if name not in PROMPT_FILES:
        raise HTTPException(status_code=404, detail="Unknown prompt name")
    content = await request.body()
    path = PROMPTS_DIR / PROMPT_FILES[name]
    path.write_text(content.decode("utf-8"), encoding="utf-8")
    return {"saved": True, "path": str(path)}


# ---------------------------------------------------------------------------
# API: Publish
# ---------------------------------------------------------------------------

@app.get("/api/publish/{date}/preview")
async def publish_preview(date: str):
    day = DIST_DIR / date
    curated_path = day / "curated.json"
    video_path = day / "video.mp4"

    if not curated_path.exists():
        raise HTTPException(status_code=404, detail="curated.json not found for this date")

    from pipelines.publish import _build_metadata

    curated = json.loads(curated_path.read_text(encoding="utf-8"))
    # Count prior episodes for episode number
    episode = 1
    if DIST_DIR.exists():
        for d in DIST_DIR.iterdir():
            if d.is_dir() and d.name < date and (d / "video.mp4").exists():
                episode += 1

    meta = _build_metadata(curated, date, episode)

    # Fill cover if available
    toc_cover = day / "frames" / "toc.png"
    if toc_cover.exists():
        meta["cover"] = f"/dist/{date}/frames/toc.png"

    # Check existing publish.json for bvid
    publish_json = day / "publish.json"
    if publish_json.exists():
        try:
            existing = json.loads(publish_json.read_text(encoding="utf-8"))
            meta["bvid"] = existing.get("bvid") or existing.get("BV")
        except Exception:
            pass

    return meta


@app.post("/api/publish/{date}")
async def do_publish(date: str, body: dict = Body(...)):
    day = DIST_DIR / date
    video_path = day / "video.mp4"

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="video.mp4 not found")

    # Write the (possibly edited) metadata to publish.json
    publish_json = day / "publish.json"
    # Merge body over existing
    meta = dict(body)
    publish_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Locate biliup
    venv_biliup = Path(PYTHON_EXE).parent / ("biliup.exe" if sys.platform == "win32" else "biliup")
    if venv_biliup.exists():
        biliup_exe = str(venv_biliup)
    else:
        biliup_exe = shutil.which("biliup") or shutil.which("biliup.exe")

    if not biliup_exe:
        raise HTTPException(
            status_code=503,
            detail="biliup not found. Place biliup.exe in .venv/Scripts/ or on PATH.",
        )

    cmd = [
        biliup_exe,
        "upload",
        str(video_path),
        "--title", meta.get("title", ""),
        "--desc", meta.get("desc", ""),
        "--tag", meta.get("tag", ""),
        "--tid", str(meta.get("tid", 188)),
        "--copyright", str(meta.get("copyright", 1)),
    ]
    cover = meta.get("cover")
    if cover and not cover.startswith("/dist/"):
        # Absolute path from publish.json
        cmd += ["--cover", cover]
    elif cover and cover.startswith("/dist/"):
        # Serve path → resolve to filesystem
        rel = cover.lstrip("/dist/")
        abs_cover = DIST_DIR / rel
        if abs_cover.exists():
            cmd += ["--cover", str(abs_cover)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="biliup timed out")

    if result.returncode != 0:
        return JSONResponse(
            status_code=500,
            content={"error": result.stderr or result.stdout or "biliup exited non-zero"},
        )

    # Try to parse BV from stdout
    bvid = None
    for line in (result.stdout or "").splitlines():
        if "BV" in line:
            import re
            m = re.search(r"BV\w+", line)
            if m:
                bvid = m.group()
                break

    if bvid:
        meta["bvid"] = bvid
        publish_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"bvid": bvid, "stdout": result.stdout}
