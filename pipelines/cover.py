"""
Compose a per-day B站 cover by overlaying daily title text on the channel's
brand frame image. Output: dist/<channel>/<date>/cover.png (1920x1080).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
import numpy as np
from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from core.channel import Channel


TARGET_W, TARGET_H = 1920, 1080
STROKE_PX = 5
STROKE_COLOR = (0, 0, 0)
FILL_COLOR = (255, 255, 255)

WIN_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 Bold
    r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",   # 黑体
]

# Fallback hardcoded boxes for ai-invest frame (at 1920x1080).
# Used when auto-detection fails.  Derived from actual pixel analysis.
_FALLBACK_PURPLE = (208, 378, 1054, 550)   # (left, top, right, bottom)
_FALLBACK_GOLD   = (94,  665, 1093, 826)


def _pick_font(size: int) -> ImageFont.FreeTypeFont:
    for p in WIN_FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise RuntimeError("No Chinese-supporting font found at expected Windows paths.")


def _resize_to_canvas(im: Image.Image) -> Image.Image:
    """Resize while preserving aspect; letterbox to 1920x1080 if needed."""
    target_ratio = TARGET_W / TARGET_H
    cur_ratio = im.width / im.height
    if abs(cur_ratio - target_ratio) < 0.01:
        return im.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    # Letterbox black bars
    if cur_ratio > target_ratio:
        new_w = TARGET_W
        new_h = int(TARGET_W / cur_ratio)
    else:
        new_h = TARGET_H
        new_w = int(TARGET_H * cur_ratio)
    resized = im.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (TARGET_W, TARGET_H), (0, 0, 0))
    canvas.paste(resized, ((TARGET_W - new_w) // 2, (TARGET_H - new_h) // 2))
    return canvas


def _detect_block(
    rgb: np.ndarray,
    hue_lo: float,
    hue_hi: float,
    s_min: float = 0.5,
    v_min: float = 0.5,
    percentile_trim: float = 12.0,
) -> tuple[int, int, int, int] | None:
    """
    Find bbox of the largest contiguous region matching the HSV criteria.
    Returns (left, top, right, bottom) or None if not found / too small.
    Hues in degrees (0-360).

    Uses vectorised numpy HSV conversion; no scipy required.
    Clips outliers via percentile to handle tilted parallelogram edges.
    """
    rgb_f = rgb.astype(np.float32) / 255.0
    r, g, b = rgb_f[..., 0], rgb_f[..., 1], rgb_f[..., 2]
    maxc = np.max(rgb_f, axis=-1)
    minc = np.min(rgb_f, axis=-1)
    v = maxc
    delta = maxc - minc
    safe = delta > 1e-6
    denom = np.where(safe, delta, 1.0)
    s = np.where(maxc > 0, delta / np.where(maxc > 0, maxc, 1.0), 0.0)
    rc = np.where(safe, (maxc - r) / denom, 0.0)
    gc = np.where(safe, (maxc - g) / denom, 0.0)
    bc = np.where(safe, (maxc - b) / denom, 0.0)
    hue = np.where(
        maxc == r,
        bc - gc,
        np.where(maxc == g, 2.0 + rc - bc, 4.0 + gc - rc),
    )
    hue = (hue * 60.0) % 360.0

    mask = (hue >= hue_lo) & (hue <= hue_hi) & (s >= s_min) & (v >= v_min)
    if not mask.any():
        return None

    ys, xs = np.where(mask)
    # Require a minimum area to avoid matching tiny specks
    if len(xs) < 500:
        return None

    # Clip outliers (handles tilted edges and stray off-color pixels)
    p = percentile_trim
    x_lo = int(np.percentile(xs, p))
    x_hi = int(np.percentile(xs, 100 - p))
    y_lo = int(np.percentile(ys, p))
    y_hi = int(np.percentile(ys, 100 - p))

    if x_hi <= x_lo or y_hi <= y_lo:
        return None
    return (x_lo, y_lo, x_hi, y_hi)


def _fit_font_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    target_fill_w: float = 0.82,
    target_fill_h: float = 0.75,
) -> int:
    """Return the largest font size that fits text within target_fill_w × box_w
    and target_fill_h × box_h. Used to compute a unified size across blocks."""
    left, top, right, bottom = box
    bw, bh = right - left, bottom - top
    lo, hi = 20, min(bh - 8, 200)
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        f = _pick_font(mid)
        tb = draw.textbbox((0, 0), text, font=f, stroke_width=STROKE_PX)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        if tw <= bw * target_fill_w and th <= bh * target_fill_h:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font_size: int | None = None,
    target_fill_w: float = 0.82,
    target_fill_h: float = 0.75,
) -> None:
    """
    Draw text centred in box with a stroke outline. If font_size is None,
    auto-pick the largest size that fits target_fill_w/h fractions.
    """
    left, top, right, bottom = box
    bw, bh = right - left, bottom - top
    if font_size is None:
        font_size = _fit_font_size(draw, text, box, target_fill_w, target_fill_h)
    best = font_size
    f = _pick_font(best)
    tb = draw.textbbox((0, 0), text, font=f, stroke_width=STROKE_PX)
    tw = tb[2] - tb[0]
    th = tb[3] - tb[1]
    x = left + (bw - tw) // 2 - tb[0]
    y = top + (bh - th) // 2 - tb[1]
    draw.text(
        (x, y), text, font=f,
        fill=FILL_COLOR,
        stroke_width=STROKE_PX,
        stroke_fill=STROKE_COLOR,
    )


def _hook(title: str, max_chars: int = 14) -> str:
    """Extract a short hook: first comma-clause, or truncated with ellipsis."""
    title = (title or "").strip()
    for sep in "，,、":
        if sep in title:
            clause = title.split(sep)[0].strip()
            if len(clause) <= max_chars:
                return clause
            return clause[:max_chars].rstrip() + "…"
    if len(title) <= max_chars:
        return title
    return title[:max_chars].rstrip() + "…"


def compose_cover(
    frame_path: Path,
    out_path: Path,
    text_top: str,
    text_bottom: str,
) -> Path:
    """
    Compose daily cover by overlaying text on the channel frame.

    1. Open frame, resize to 1920x1080 (letterbox if needed).
    2. Auto-detect purple and gold colour blocks via HSV masking.
    3. Render Chinese text centred on each block with white+black stroke.
    4. Save to out_path.
    """
    im = Image.open(frame_path).convert("RGB")
    im = _resize_to_canvas(im)
    rgb = np.array(im)

    # Detect purple (top/upper block) — H ~276°, high S+V
    purple_box = _detect_block(rgb, hue_lo=260, hue_hi=295, s_min=0.40, v_min=0.40)
    if purple_box is None:
        print(
            f"WARN: purple block not detected in {frame_path}; "
            "using fallback coordinates.",
            file=sys.stderr,
        )
        purple_box = _FALLBACK_PURPLE

    # Detect gold/yellow (bottom block) — H ~43°, high S+V
    gold_box = _detect_block(rgb, hue_lo=35, hue_hi=58, s_min=0.50, v_min=0.60)
    if gold_box is None:
        print(
            f"WARN: gold block not detected in {frame_path}; "
            "using fallback coordinates.",
            file=sys.stderr,
        )
        gold_box = _FALLBACK_GOLD

    draw = ImageDraw.Draw(im)
    # Compute unified font size: take min of what each block can fit, so both
    # headlines render at the same visual size (looks balanced, not lopsided).
    size_top = _fit_font_size(draw, text_top, purple_box) if text_top else 200
    size_bot = _fit_font_size(draw, text_bottom, gold_box) if text_bottom else 200
    unified = min(size_top, size_bot)
    if text_top:
        _draw_centered(draw, text_top, purple_box, font_size=unified)
    if text_bottom:
        _draw_centered(draw, text_bottom, gold_box, font_size=unified)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path, "PNG")
    return out_path


def build_for_episode(
    channel: "Channel",
    curated: list[dict],
    date: str,
    out_path: Path,
) -> Path | None:
    """
    Build today's cover for a channel.

    Returns None if no cover_frame.png exists for this channel.
    text_top:    rank-1 item's short hook (top headline, max 10 chars for punch)
    text_bottom: rank-2 item's short hook (second headline)
    Falls back to channel.brand_title if curated is empty.
    """
    frame_path = channel.root / "cover_frame.png"
    if not frame_path.exists():
        return None
    if curated:
        text_top = _hook(curated[0]["title"], max_chars=10)
        text_bottom = _hook(curated[1]["title"], max_chars=10) if len(curated) >= 2 else ""
    else:
        text_top = channel.brand_title
        text_bottom = ""
    return compose_cover(frame_path, out_path, text_top, text_bottom)


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Compose a daily channel cover.")
    parser.add_argument("--channel", required=True, help="Channel ID (e.g. ai-invest)")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    from core.channel import load_channel
    from core.config import Settings

    s = Settings()
    try:
        ch = load_channel(s.channels_dir, args.channel)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    day = s.dist_dir / args.channel / args.date
    curated_path = day / "curated.json"
    if not curated_path.exists():
        print(f"ERROR: {curated_path} not found", file=sys.stderr)
        return 1

    curated = json.loads(curated_path.read_text(encoding="utf-8"))
    out = day / "cover.png"
    result = build_for_episode(ch, curated, args.date, out)
    if result is None:
        print(
            f"No cover_frame.png at {ch.root / 'cover_frame.png'}",
            file=sys.stderr,
        )
        return 1
    print(f"wrote {result}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
