"""
Subprocess tracker and SSE log tailer for the web dashboard.

Tracks in-memory running PIDs keyed by date.
Provides an async generator that tails a log file for SSE.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import AsyncGenerator

# date -> {"proc": Popen, "status": "running"|"done"|"failed"}
_RUNS: dict[str, dict] = {}


def start_run(date: str, cmd: list[str], cwd: Path) -> None:
    """Start a subprocess for the given date.  Raises if already running."""
    if _RUNS.get(date, {}).get("status") == "running":
        raise ValueError(f"A run for {date} is already in progress")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _RUNS[date] = {"proc": proc, "status": "running"}


def poll_runs() -> None:
    """Update status for all tracked runs (call before returning status)."""
    for date, info in _RUNS.items():
        proc: subprocess.Popen = info["proc"]
        if info["status"] == "running":
            ret = proc.poll()
            if ret is not None:
                info["status"] = "done" if ret == 0 else "failed"


def run_status() -> dict[str, str]:
    """Return mapping of date → status string."""
    poll_runs()
    return {date: info["status"] for date, info in _RUNS.items()}


def is_running(date: str) -> bool:
    poll_runs()
    return _RUNS.get(date, {}).get("status") == "running"


async def tail_log(log_path: Path) -> AsyncGenerator[str, None]:
    """
    Async generator that yields lines from log_path as they are written.
    Yields existing content first, then polls for new lines every 0.5 s.
    Stops when the file has not grown for 60 seconds after the last run for
    that date completes (or after 10 min hard limit).
    """
    position = 0
    deadline = asyncio.get_event_loop().time() + 600  # 10 min hard limit

    # derive date from log path (parent dir name is the date)
    date = log_path.parent.name

    while asyncio.get_event_loop().time() < deadline:
        if log_path.exists():
            with log_path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(position)
                chunk = fh.read()
                if chunk:
                    for line in chunk.splitlines():
                        yield line
                    position = fh.tell()

        # Stop tailing if run is done/failed and we've read all content
        status = _RUNS.get(date, {}).get("status", "idle")
        if status in ("done", "failed") and log_path.exists():
            # one more pass to drain any final lines
            with log_path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(position)
                chunk = fh.read()
                if chunk:
                    for line in chunk.splitlines():
                        yield line
            return

        await asyncio.sleep(0.5)
