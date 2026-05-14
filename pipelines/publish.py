"""
Stage 6: Auto-publish today's video.mp4 to Bilibili via biliup-rs.

CLI:
    python -m pipelines.publish --date 2026-05-14 [--dry-run]

Requires:
    biliup.exe on PATH (placed at .venv/Scripts/biliup.exe).
    User must have run `biliup login` once (QR-code scan — interactive).

Never invoked by the pipeline on a cold machine; gated by AUTO_PUBLISH=1 in .env.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Ticker → common short company name mapping (extend as needed)
# ---------------------------------------------------------------------------
_TICKER_NAMES: dict[str, str] = {
    "NVDA": "英伟达",
    "MSFT": "微软",
    "AAPL": "苹果",
    "GOOG": "谷歌",
    "GOOGL": "谷歌",
    "META": "Meta",
    "AMZN": "亚马逊",
    "TSLA": "特斯拉",
    "BIDU": "百度",
    "BABA": "阿里",
    "9988": "阿里",
    "TSM": "台积电",
    "INTC": "英特尔",
    "AMD": "AMD",
    "ARM": "ARM",
    "CSCO": "思科",
    "IBM": "IBM",
    "ORCL": "甲骨文",
    "NFLX": "奈飞",
    "SPOT": "Spotify",
    "U": "Unity",
    "PLTR": "Palantir",
    "SNOW": "Snowflake",
    "CRM": "Salesforce",
    "ADBE": "Adobe",
    "NOW": "ServiceNow",
    "PANW": "Palo Alto",
    "NET": "Cloudflare",
    "DDOG": "Datadog",
    "MDB": "MongoDB",
    "ESTC": "Elastic",
    "ZS": "Zscaler",
    "CRWD": "CrowdStrike",
    "S": "SentinelOne",
}


def _extract_company_names(curated: list[dict]) -> list[str]:
    """Return distinct company names from top tickers across all items."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for item in curated:
        tickers = item.get("impact", {}).get("tickers", [])
        for t in tickers:
            name = _TICKER_NAMES.get(t.upper())
            if name and name not in seen_set:
                seen_set.add(name)
                seen.append(name)
        if len(seen) >= 6:
            break  # no need to scan further — we'll pick top 3 later
    return seen


def _build_title(companies: list[str], month: str, day: str, n: int) -> str:
    """
    Build a title ≤ 80 chars.
    Format: AI 投资晨读 · {M}月{D}日 · {C1}/{C2}/{C3} 等 {N} 条
    Drops companies until it fits.
    """
    base = f"AI 投资晨读 · {month}月{day}日"
    suffix = f" 等 {n} 条"
    top = companies[:3]
    while top:
        candidate = base + " · " + "/".join(top) + suffix
        if len(candidate) <= 80:
            return candidate
        top.pop()
    # No companies fit — return minimal title
    return (base + suffix)[:80]


def _build_desc(curated: list[dict], date: str) -> str:
    """
    Build a desc ≤ 250 chars.
    Opening + numbered title list + closing.
    """
    n = len(curated)
    opening = f"本期精选 {n} 条 AI 投资风向新闻，覆盖："
    closing = f"完整 HTML 报告与口播稿见 dist/{date}/. 由 AI 自动生成。"
    titles = [f"{i+1}.{item['title']}" for i, item in enumerate(curated)]

    full = opening + " ".join(titles) + " " + closing
    if len(full) <= 250:
        return full

    # Need to truncate — keep as many titles as possible
    budget = 250 - len(opening) - len(closing) - 1  # -1 for space before closing
    kept: list[str] = []
    used = 0
    for t in titles:
        # +1 for the space separator
        need = len(t) + (1 if kept else 0)
        if used + need > budget:
            break
        kept.append(t)
        used += need

    if kept:
        return (opening + " ".join(kept) + " " + closing)[:250]
    # Edge case: even the opening + closing doesn't fit (shouldn't happen)
    return (opening + closing)[:250]


def _build_tags(curated: list[dict]) -> str:
    """
    Build a comma-separated tag string.
    Base tags + dynamic tags from tickers (mapped names).
    B站 rules: each tag ≤ 20 chars, no special chars, total ≤ 12 tags.
    """
    base_tags = ["AI", "投资", "科技", "日更", "AI晨读", "财经"]
    dynamic: list[str] = []
    seen: set[str] = set(base_tags)

    for item in curated:
        tickers = item.get("impact", {}).get("tickers", [])
        for t in tickers:
            name = _TICKER_NAMES.get(t.upper())
            if name and name not in seen:
                # Sanitize: remove special chars
                clean = "".join(c for c in name if c.isalnum() or "一" <= c <= "鿿")
                if clean and len(clean) <= 20:
                    seen.add(name)
                    dynamic.append(clean)
        if len(base_tags) + len(dynamic) >= 12:
            break

    all_tags = base_tags + dynamic
    # Enforce totals
    all_tags = all_tags[:12]
    return ",".join(all_tags)


def _build_metadata(curated: list[dict], date: str, episode: int) -> dict:
    """
    Build Bilibili upload metadata from curated news items.

    Returns a dict with keys: title, desc, tag, tid, copyright, cover.
    """
    # Parse date parts for Chinese format
    parts = date.split("-")  # YYYY-MM-DD
    month = parts[1].lstrip("0")  # remove leading zero
    day = parts[2].lstrip("0")
    n = len(curated)

    companies = _extract_company_names(curated)
    title = _build_title(companies, month, day, n)
    desc = _build_desc(curated, date)
    tag = _build_tags(curated)

    return {
        "title": title,
        "desc": desc,
        "tag": tag,
        "tid": 188,       # 科技 > 数码
        "copyright": 1,   # 自制
        "cover": None,    # auto from video frame
    }


def run(
    *,
    video_path: Path,
    curated_path: Path,
    date: str,
    episode: int,
    dry_run: bool = False,
) -> dict:
    """
    Build metadata and (unless dry_run) invoke biliup.exe to upload the video.

    Returns the metadata dict.
    Writes dist/{date}/publish.json in all cases (useful for inspection).
    Raises RuntimeError if biliup not on PATH.
    Raises subprocess.CalledProcessError if biliup exits non-zero.
    """
    curated: list[dict] = json.loads(curated_path.read_text(encoding="utf-8"))
    meta = _build_metadata(curated, date, episode)

    # Write publish.json alongside the video for inspection
    publish_json = video_path.parent / "publish.json"
    publish_json.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if dry_run:
        return meta

    # Locate biliup.exe — first try venv's Scripts dir (where install puts it),
    # then fall back to system PATH.
    import sys as _sys
    venv_biliup = Path(_sys.executable).parent / ("biliup.exe" if _sys.platform == "win32" else "biliup")
    if venv_biliup.exists():
        biliup_exe = str(venv_biliup)
    else:
        biliup_exe = shutil.which("biliup") or shutil.which("biliup.exe")
    if not biliup_exe:
        raise RuntimeError(
            "biliup not found. Place biliup.exe in .venv/Scripts/ or on PATH."
        )

    # Build the biliup upload command.
    # biliup-rs CLI: biliup upload [OPTIONS] <video_file>
    # --title, --desc, --tag, --tid, --copyright
    cmd = [
        biliup_exe,
        "upload",
        str(video_path),
        "--title", meta["title"],
        "--desc", meta["desc"],
        "--tag", meta["tag"],
        "--tid", str(meta["tid"]),
        "--copyright", str(meta["copyright"]),
    ]

    result = subprocess.run(cmd, check=True, capture_output=False)
    return meta


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Publish today's video to Bilibili via biliup-rs."
    )
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build metadata and write publish.json without uploading.",
    )
    args = parser.parse_args()

    # Resolve paths relative to project root (two levels up from this file)
    project_root = Path(__file__).resolve().parent.parent
    day_dir = project_root / "dist" / args.date
    video_path = day_dir / "video.mp4"
    curated_path = day_dir / "curated.json"

    if not video_path.exists():
        print(f"ERROR: video not found at {video_path}", file=sys.stderr)
        return 1
    if not curated_path.exists():
        print(f"ERROR: curated.json not found at {curated_path}", file=sys.stderr)
        return 1

    # Episode: count prior dirs that have video.mp4
    episode = 1
    dist_dir = project_root / "dist"
    if dist_dir.exists():
        for d in dist_dir.iterdir():
            if d.is_dir() and d.name < args.date and (d / "video.mp4").exists():
                episode += 1

    meta = run(
        video_path=video_path,
        curated_path=curated_path,
        date=args.date,
        episode=episode,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("DRY RUN — metadata written to", video_path.parent / "publish.json")
    else:
        print("Published successfully.")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
