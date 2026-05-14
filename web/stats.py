"""
Stats aggregation for the web dashboard.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from web.episodes import probe_video, parse_run_log


# ---------------------------------------------------------------------------
# Rates (constants, exposed in API response)
# ---------------------------------------------------------------------------

RATES = {
    "tts_rmb_per_char": 0.002,          # MiniMax speech-2.8-hd
    "llm_usd_per_m_in": 0.14,           # DeepSeek V4 Flash cache-miss
    "llm_usd_per_m_out": 0.28,          # DeepSeek V4 Flash output
    "usd_to_rmb": 7.2,
}

# Rough tokens-per-char estimate for Chinese+English mixed text
CHARS_PER_TOKEN = 1.5


def _count_chars(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return len(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return 0


def _segment_chars(day: Path) -> int:
    seg_path = day / "segments.json"
    if not seg_path.exists():
        return 0
    try:
        segs = json.loads(seg_path.read_text(encoding="utf-8"))
        return sum(len(s.get("text", "")) for s in segs)
    except Exception:
        return 0


def _estimate_costs(day: Path) -> dict:
    """Return estimated TTS and LLM costs in RMB for one day dir."""
    # TTS cost: segment chars × rate
    seg_chars = _segment_chars(day)
    tts_rmb = seg_chars * RATES["tts_rmb_per_char"]

    # LLM cost: treat raw.json as input, curated+segments as output
    raw_chars = _count_chars(day / "raw.json")
    out_chars = _count_chars(day / "curated.json") + _count_chars(day / "segments.json")

    in_tokens = raw_chars / CHARS_PER_TOKEN / 1_000_000
    out_tokens = out_chars / CHARS_PER_TOKEN / 1_000_000

    llm_usd = (in_tokens * RATES["llm_usd_per_m_in"]
                + out_tokens * RATES["llm_usd_per_m_out"])
    llm_rmb = llm_usd * RATES["usd_to_rmb"]

    script_chars = _count_chars(day / "script.md")

    return {
        "script_chars": script_chars,
        "seg_chars": seg_chars,
        "tts_rmb": round(tts_rmb, 4),
        "llm_rmb": round(llm_rmb, 4),
        "total_rmb": round(tts_rmb + llm_rmb, 4),
    }


def _bvid(day: Path) -> Optional[str]:
    p = day / "publish.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("bvid") or data.get("BV") or None
    except Exception:
        return None


def build_stats(dist_dir: Path, limit: int = 30) -> dict:
    """Build the full stats payload."""
    if not dist_dir.exists():
        return {"daily": [], "rates": RATES}

    days = sorted(
        [d for d in dist_dir.iterdir() if d.is_dir() and d.name[0].isdigit()],
        key=lambda d: d.name,
        reverse=True,
    )[:limit]

    daily = []
    for day in days:
        log_info = parse_run_log(day / "run.log")
        video_info = probe_video(day / "video.mp4")
        costs = _estimate_costs(day)

        # item count
        item_count = 0
        c = day / "curated.json"
        if c.exists():
            try:
                item_count = len(json.loads(c.read_text(encoding="utf-8")))
            except Exception:
                pass

        daily.append({
            "date": day.name,
            "items": item_count,
            "duration_s": video_info.get("duration_s"),
            "size_kb": video_info.get("size_kb"),
            "success": log_info["status"] == "success",
            "failed": log_info["status"] == "failed",
            "published": bool(_bvid(day)),
            **costs,
        })

    # Sort chronologically for charts
    daily.sort(key=lambda x: x["date"])

    return {"daily": daily, "rates": RATES}
