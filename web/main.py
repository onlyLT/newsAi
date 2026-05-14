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

from fastapi import FastAPI, HTTPException, Query, Request, Body
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
CHANNELS_DIR = PROJECT_ROOT / "channels"
# Fallback prompt dir (used when channel dir doesn't have prompts; legacy)
PROMPTS_DIR = PROJECT_ROOT / "prompts"
SOURCES_YAML = PROJECT_ROOT / "sources" / "sources.yaml"
PYTHON_EXE = str(Path(sys.executable))

# ---------------------------------------------------------------------------
# Channel helpers
# ---------------------------------------------------------------------------


def _get_channel_ids() -> list[str]:
    """Return sorted channel IDs available on disk."""
    from core.channel import list_channels
    return list_channels(CHANNELS_DIR)


def _resolve_channel(channel: Optional[str]) -> str:
    """Resolve channel id, defaulting to the first alphabetical channel."""
    if channel:
        return channel
    ids = _get_channel_ids()
    return ids[0] if ids else "ai-invest"


def _channel_prompts_dir(channel_id: str) -> Path:
    ch_dir = CHANNELS_DIR / channel_id / "prompts"
    if ch_dir.exists():
        return ch_dir
    return PROMPTS_DIR  # fallback


def _channel_sources_yaml(channel_id: str) -> Path:
    ch_yaml = CHANNELS_DIR / channel_id / "sources.yaml"
    if ch_yaml.exists():
        return ch_yaml
    return SOURCES_YAML  # fallback


def _channel_dist_dir(channel_id: str) -> Path:
    return DIST_DIR / channel_id


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


def _list_episodes(channel_id: str, limit: int = 30) -> list[dict]:
    ch_dist = _channel_dist_dir(channel_id)
    if not ch_dist.exists():
        return []
    days = sorted(
        [d for d in ch_dist.iterdir() if d.is_dir() and d.name[0].isdigit()],
        key=lambda d: d.name,
        reverse=True,
    )[:limit]
    return [_episode_summary(d) for d in days]


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, channel: Optional[str] = Query(default=None)):
    from core.config import today_str
    today = today_str()
    channel_id = _resolve_channel(channel)
    channel_ids = _get_channel_ids()
    episodes = _list_episodes(channel_id, 30)
    today_ep = next((e for e in episodes if e["date"] == today), None)

    # Detect failed stage for today's banner
    from web.episodes import detect_failed_stage, parse_run_log
    today_failed_stage = None
    retry_log_tail: list[str] = []
    if not is_running(today):
        log_path = _channel_dist_dir(channel_id) / today / "run.log"
        today_failed_stage = detect_failed_stage(log_path)
        if today_failed_stage:
            info = parse_run_log(log_path)
            retry_log_tail = info["lines"][-50:]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "today": today,
            "today_ep": today_ep,
            "episodes": episodes,
            "today_failed_stage": today_failed_stage,
            "retry_log_tail": retry_log_tail,
            "channel_id": channel_id,
            "channel_ids": channel_ids,
        },
    )


# ---------------------------------------------------------------------------
# Episode detail page (server-rendered)
# ---------------------------------------------------------------------------

@app.get("/episodes/{date}", response_class=HTMLResponse)
async def episode_page(date: str, request: Request,
                       channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    day = _channel_dist_dir(channel_id) / date
    if not day.exists():
        raise HTTPException(status_code=404, detail=f"No episode for {date}")

    from web.episodes import build_episode_detail
    ep = build_episode_detail(day)

    # Render script.md as HTML
    script_html = None
    if ep.get("script_md"):
        try:
            import markdown as _md
            script_html = _md.markdown(ep["script_md"])
        except Exception:
            script_html = f"<pre>{ep['script_md']}</pre>"
    ep["script_html"] = script_html

    return templates.TemplateResponse(
        request=request,
        name="episode.html",
        context={"date": date, "ep": ep, "channel_id": channel_id},
    )


# ---------------------------------------------------------------------------
# API: Episodes
# ---------------------------------------------------------------------------

@app.get("/api/episodes")
async def list_episodes(channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    return _list_episodes(channel_id, 30)


@app.get("/api/episodes/{date}")
async def episode_detail(date: str, channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    day = _channel_dist_dir(channel_id) / date
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


@app.get("/api/episodes/{date}/detail")
async def episode_detail_full(date: str, channel: Optional[str] = Query(default=None)):
    """Extended detail endpoint for the episode detail page / API consumers."""
    channel_id = _resolve_channel(channel)
    day = _channel_dist_dir(channel_id) / date
    if not day.exists():
        raise HTTPException(status_code=404, detail="Episode not found")

    from web.episodes import build_episode_detail
    return build_episode_detail(day)


# ---------------------------------------------------------------------------
# API: Run trigger
# ---------------------------------------------------------------------------

VALID_STAGES = {"ingest", "curate", "script", "render_html", "render_video", "publish"}

# Ordered stage list for "retry from stage" logic
STAGE_ORDER = ["ingest", "curate", "script", "render_html", "render_video", "publish"]


@app.post("/api/run")
async def trigger_run(body: dict = Body(...)):
    date: str = body.get("date", "")
    stage: Optional[str] = body.get("stage")
    start_stage: Optional[str] = body.get("start_stage")  # for retry-from
    channel_id: Optional[str] = body.get("channel")

    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    if stage and stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")
    if start_stage and start_stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid start_stage: {start_stage}")
    if is_running(date):
        raise HTTPException(status_code=409, detail=f"Run for {date} already in progress")

    channel_args = ["--channel", channel_id] if channel_id else []

    if start_stage:
        cmd = [PYTHON_EXE, "run_daily.py", "--date", date, "--start-stage", start_stage] + channel_args
    elif stage:
        cmd = [PYTHON_EXE, "-m", f"pipelines.{stage}", "--date", date] + channel_args
    else:
        cmd = [PYTHON_EXE, "run_daily.py", "--date", date] + channel_args

    start_run(date, cmd, PROJECT_ROOT)
    return {
        "task_id": date,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "start_stage": start_stage,
        "channel": channel_id,
    }


@app.get("/api/run/status")
async def get_run_status():
    return run_status()


@app.get("/api/run/{date}/log/stream")
async def stream_log(date: str, request: Request,
                     channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    log_path = _channel_dist_dir(channel_id) / date / "run.log"

    async def event_generator():
        async for line in tail_log(log_path):
            if await request.is_disconnected():
                break
            yield {"data": line}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# API: Failed-stage detection
# ---------------------------------------------------------------------------

@app.get("/api/run/{date}/failed-stage")
async def get_failed_stage(date: str, channel: Optional[str] = Query(default=None)):
    """Return the failed/stuck stage for a date, or null if none."""
    channel_id = _resolve_channel(channel)
    log_path = _channel_dist_dir(channel_id) / date / "run.log"
    from web.episodes import detect_failed_stage, parse_run_log
    stage = detect_failed_stage(log_path)
    info = parse_run_log(log_path)
    return {
        "date": date,
        "failed_stage": stage,
        "status": info["status"],
        "log_tail": info["lines"][-50:],
        "channel": channel_id,
    }


# ---------------------------------------------------------------------------
# API: Channels
# ---------------------------------------------------------------------------

@app.get("/api/channels")
async def list_all_channels():
    """Return list of available channels with id, name, and brand_title."""
    from core.channel import list_channels, load_channel
    out = []
    for cid in list_channels(CHANNELS_DIR):
        try:
            ch = load_channel(CHANNELS_DIR, cid)
            out.append({"id": ch.id, "name": ch.name, "brand_title": ch.brand_title})
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# API: Prompts
# ---------------------------------------------------------------------------

PROMPT_FILES = {
    "curate": "curate.system.md",
    "script": "script.system.md",
}


@app.get("/api/prompts/{name}")
async def get_prompt(name: str, channel: Optional[str] = Query(default=None)):
    if name not in PROMPT_FILES:
        raise HTTPException(status_code=404, detail="Unknown prompt name")
    channel_id = _resolve_channel(channel)
    path = _channel_prompts_dir(channel_id) / PROMPT_FILES[name]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Prompt file not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.put("/api/prompts/{name}")
async def save_prompt(name: str, request: Request,
                      channel: Optional[str] = Query(default=None)):
    if name not in PROMPT_FILES:
        raise HTTPException(status_code=404, detail="Unknown prompt name")
    channel_id = _resolve_channel(channel)
    content = await request.body()
    path = _channel_prompts_dir(channel_id) / PROMPT_FILES[name]
    path.write_text(content.decode("utf-8"), encoding="utf-8")
    return {"saved": True, "path": str(path)}


# ---------------------------------------------------------------------------
# API: Publish
# ---------------------------------------------------------------------------

@app.get("/api/publish/{date}/preview")
async def publish_preview(date: str, channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    day = _channel_dist_dir(channel_id) / date
    curated_path = day / "curated.json"
    video_path = day / "video.mp4"

    if not curated_path.exists():
        raise HTTPException(status_code=404, detail="curated.json not found for this date")

    from pipelines.publish import _build_metadata

    curated = json.loads(curated_path.read_text(encoding="utf-8"))
    # Count prior episodes for episode number
    episode = 1
    ch_dist = _channel_dist_dir(channel_id)
    if ch_dist.exists():
        for d in ch_dist.iterdir():
            if d.is_dir() and d.name < date and (d / "video.mp4").exists():
                episode += 1

    # Load channel publish config if available
    try:
        from core.channel import load_channel
        ch = load_channel(CHANNELS_DIR, channel_id)
        meta = _build_metadata(
            curated, date, episode,
            tid=ch.publish.tid,
            title_prefix=ch.publish.title_prefix,
            base_tags=ch.publish.base_tags,
            channel_name=ch.name,
        )
    except Exception:
        meta = _build_metadata(curated, date, episode)

    # Fill cover if available
    toc_cover = day / "frames" / "toc.png"
    if toc_cover.exists():
        meta["cover"] = f"/dist/{channel_id}/{date}/frames/toc.png"

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
async def do_publish(date: str, body: dict = Body(...),
                     channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    day = _channel_dist_dir(channel_id) / date
    video_path = day / "video.mp4"

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="video.mp4 not found")

    # Write the (possibly edited) metadata to publish.json
    publish_json = day / "publish.json"
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
        cmd += ["--cover", cover]
    elif cover and cover.startswith("/dist/"):
        rel = cover.lstrip("/dist/")
        abs_cover = DIST_DIR / rel
        if abs_cover.exists():
            cmd += ["--cover", str(abs_cover)]

    try:
        # capture as bytes so we can force UTF-8 decode regardless of Windows code page
        result = subprocess.run(cmd, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="biliup timed out")

    stderr_text = (result.stderr or b"").decode("utf-8", errors="replace")
    stdout_text = (result.stdout or b"").decode("utf-8", errors="replace")

    if result.returncode != 0:
        # Surface biliup's actual log to the UI so user can see WHY it failed
        # (e.g. 21566 "投稿过于频繁" rate-limit, expired cookie, etc.)
        combined = (stderr_text + "\n" + stdout_text).strip()
        # Detect known B站 error codes and add friendly message
        if "21566" in combined:
            friendly = "❌ B站 风控触发 (21566 投稿过于频繁)。距上次投稿太近，请等 3-6 小时或到明天再试。"
        elif "code: 60024" in combined or "60024" in combined:
            friendly = "❌ 标题已存在 (60024)。换个标题再发。"
        elif "cookie" in combined.lower() and ("过期" in combined or "expir" in combined.lower()):
            friendly = "❌ B站 登录过期。在 PowerShell 跑: .venv\\Scripts\\biliup.exe login 重新扫码。"
        else:
            friendly = "❌ biliup 失败 (exit " + str(result.returncode) + "):"
        return JSONResponse(
            status_code=500,
            content={"error": f"{friendly}\n\n{combined[-1500:]}"},  # last 1500 chars to fit UI
        )

    # use decoded stdout below
    result_stdout_for_parse = stdout_text

    # Try to parse BV from stdout
    bvid = None
    for line in (stdout_text + "\n" + stderr_text).splitlines():
        if "BV" in line:
            import re
            m = re.search(r"BV[A-Za-z0-9]+", line)
            if m:
                bvid = m.group()
                break

    if bvid:
        meta["bvid"] = bvid
        publish_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"bvid": bvid, "stdout": stdout_text}


# ---------------------------------------------------------------------------
# API: Sources
# ---------------------------------------------------------------------------

@app.get("/api/sources")
async def get_sources(channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    sources_yaml = _channel_sources_yaml(channel_id)
    from web.sources_api import load_sources
    return load_sources(sources_yaml)


@app.put("/api/sources")
async def put_sources(body: list = Body(...),
                      channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    sources_yaml = _channel_sources_yaml(channel_id)
    from web.sources_api import save_sources
    save_sources(sources_yaml, body)
    return {"saved": True, "count": len(body)}


@app.post("/api/sources/test")
async def test_source(body: dict = Body(...)):
    from web.sources_api import test_fetch_source
    result = await test_fetch_source(body)
    return result


# ---------------------------------------------------------------------------
# API: Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats(channel: Optional[str] = Query(default=None)):
    channel_id = _resolve_channel(channel)
    from web.stats import build_stats
    return build_stats(_channel_dist_dir(channel_id))
