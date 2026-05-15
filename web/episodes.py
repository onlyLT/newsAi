"""
Episode detail helpers: parse run.log, probe video with ffprobe, etc.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# run.log parsing
# ---------------------------------------------------------------------------

def parse_run_log(log_path: Path) -> dict:
    """
    Parse a run.log and return a dict with:
      - status: 'success' | 'failed' | 'running' | 'unknown'
      - last_stage: name of last stage.start seen (or None)
      - failed_stage: name of stage that failed/stuck (or None)
      - generated_at: ISO timestamp of run.success event (or None)
      - lines: all lines (list)
    """
    if not log_path.exists():
        return {
            "status": "unknown",
            "last_stage": None,
            "failed_stage": None,
            "generated_at": None,
            "lines": [],
        }

    text = log_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    last_stage: Optional[str] = None
    generated_at: Optional[str] = None
    has_success = False
    has_fail = False

    for line in lines:
        # Extract stage.start events — structlog emits JSON or key=value lines
        # Match patterns like:  stage.start ... stage=ingest  or  "stage": "ingest"
        if "stage.start" in line:
            m = re.search(r'stage=["\']?(\w+)["\']?', line)
            if m:
                last_stage = m.group(1)
        if "run.success" in line:
            has_success = True
            # Try to extract timestamp if structlog includes it
            m = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', line)
            if m:
                generated_at = m.group(0)
        if "run.fail" in line:
            has_fail = True

    if has_success:
        status = "success"
        failed_stage = None
    elif has_fail:
        status = "failed"
        failed_stage = last_stage
    elif last_stage is not None:
        # A stage started but no completion → running or stuck
        status = "running"
        failed_stage = last_stage
    else:
        status = "unknown"
        failed_stage = None

    return {
        "status": status,
        "last_stage": last_stage,
        "failed_stage": failed_stage,
        "generated_at": generated_at,
        "lines": lines,
    }


def detect_failed_stage(log_path: Path) -> Optional[str]:
    """
    Return the name of the failed/stuck stage, or None if run succeeded or
    no log exists or is not yet started.
    """
    info = parse_run_log(log_path)
    # Only report banner for 'failed' or 'running' (stuck) — not 'success' or 'unknown'
    if info["status"] in ("failed", "running") and info["failed_stage"]:
        return info["failed_stage"]
    return None


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def probe_video(video_path: Path) -> dict:
    """
    Return {'duration_s': float, 'size_kb': int} for the video file,
    or empty dict if ffprobe is not available or file doesn't exist.
    """
    if not video_path.exists():
        return {}
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration,size",
                "-of", "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))
        size = int(fmt.get("size", 0))
        return {"duration_s": round(duration, 1), "size_kb": size // 1024}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# segments.json helpers
# ---------------------------------------------------------------------------

def load_segments(day: Path) -> list[dict]:
    """Load segments and annotate with cumulative start times."""
    seg_path = day / "segments.json"
    if not seg_path.exists():
        return []
    try:
        raw = json.loads(seg_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    result = []
    cumulative = 0
    for seg in raw:
        duration = seg.get("duration_hint_s", 0)
        minutes = cumulative // 60
        seconds = cumulative % 60
        result.append({
            "id": seg.get("id", ""),
            "text": seg.get("text", ""),
            "duration_s": duration,
            "start_ts": f"{minutes:02d}:{seconds:02d}",
            "card_ref": seg.get("card_ref"),
        })
        cumulative += duration
    return result


# ---------------------------------------------------------------------------
# curated items helper
# ---------------------------------------------------------------------------

def load_curated(day: Path) -> list[dict]:
    c = day / "curated.json"
    if not c.exists():
        return []
    try:
        return json.loads(c.read_text(encoding="utf-8"))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# script.md helper
# ---------------------------------------------------------------------------

def load_script_md(day: Path) -> Optional[str]:
    s = day / "script.md"
    if not s.exists():
        return None
    return s.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# publish status
# ---------------------------------------------------------------------------

def load_publish_status(day: Path) -> dict:
    p = day / "publish.json"
    if not p.exists():
        return {"published": False, "bvid": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        bvid = data.get("bvid") or data.get("BV")
        return {"published": bool(bvid), "bvid": bvid}
    except Exception:
        return {"published": False, "bvid": None}


# ---------------------------------------------------------------------------
# Full detail builder
# ---------------------------------------------------------------------------

def build_episode_detail(day: Path) -> dict:
    """Build the full detail dict for an episode directory."""
    date = day.name

    log_info = parse_run_log(day / "run.log")
    video_info = probe_video(day / "video.mp4")
    segments = load_segments(day)
    curated = load_curated(day)
    script_md = load_script_md(day)
    pub = load_publish_status(day)

    return {
        "date": date,
        "status": log_info["status"],
        "generated_at": log_info["generated_at"],
        "failed_stage": log_info["failed_stage"],
        # Video
        "has_video": (day / "video.mp4").exists(),
        "has_html": (day / "index.html").exists(),
        "has_cover": (day / "cover.png").exists() or (day / "frames" / "toc.png").exists(),
        "video_duration_s": video_info.get("duration_s"),
        "video_size_kb": video_info.get("size_kb"),
        # Curated items
        "item_count": len(curated),
        "curated": curated,
        # Script
        "script_md": script_md,
        # Segments
        "segments": segments,
        # Publish
        "published": pub["published"],
        "bvid": pub["bvid"],
        # Log tail (last 50 lines)
        "log_tail": log_info["lines"][-50:],
    }
