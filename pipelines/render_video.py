import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright


async def screenshot_html(html_path: Path, png_path: Path,
                          width: int = 1920, height: int = 1080) -> Path:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    url = html_path.resolve().as_uri()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        page = await ctx.new_page()
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=str(png_path), full_page=False, omit_background=False)
        await browser.close()
    return png_path


def _fmt_ts(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h = total_ms // 3_600_000
    rem = total_ms % 3_600_000
    m = rem // 60_000
    rem = rem % 60_000
    s = rem // 1000
    ms = rem % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split long text into roughly equal chunks, preferring sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    parts = re.split(r"([。！？，；])", text)
    # re-pair punctuation with preceding chunk
    merged: list[str] = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i + 1 < len(parts):
            chunk += parts[i + 1]
            i += 2
        else:
            i += 1
        if chunk:
            merged.append(chunk)
    # then greedily pack
    out: list[str] = []
    cur = ""
    for chunk in merged:
        if len(cur) + len(chunk) <= max_chars:
            cur += chunk
        else:
            if cur:
                out.append(cur)
            cur = chunk
    if cur:
        out.append(cur)
    return out or [text]


def build_srt(segments: list[dict], max_chars_per_cue: int = 28) -> str:
    """segments: [{id, text, duration_s}]; cumulative timing."""
    lines: list[str] = []
    cue_idx = 1
    cursor = 0.0
    for seg in segments:
        text = seg["text"]
        dur = float(seg["duration_s"])
        chunks = _split_text(text, max_chars_per_cue)
        per = dur / len(chunks)
        for chunk in chunks:
            start = cursor
            end = cursor + per
            lines.append(str(cue_idx))
            lines.append(f"{_fmt_ts(start)} --> {_fmt_ts(end)}")
            lines.append(chunk)
            lines.append("")
            cursor = end
            cue_idx += 1
    return "\n".join(lines)
