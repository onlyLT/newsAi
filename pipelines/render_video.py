import argparse
import asyncio
import json
import re
import subprocess
from pathlib import Path
import structlog
from playwright.async_api import async_playwright
from core.tts import MiniMaxTTS
from pipelines.render_html import render_frame

_log = structlog.get_logger(__name__)


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


async def assemble_video(
    *,
    segments: list[dict],
    srt_path: Path,
    out_path: Path,
    bgm_path: Path | None = None,
    sfx_path: Path | None = None,
) -> Path:
    """
    segments: [{frame: Path png, audio: Path mp3, duration_s: float}]
    Builds:
      - concat each (frame held for duration_s + audio) into a single stream
      - mux SRT as soft subtitle (mov_text) AND burn-in for hardcoded display
      - mix optional BGM at -20dB
    Output: H.264 1080p mp4
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.parent / "_ffmpeg_work"
    work.mkdir(exist_ok=True)

    # Step A: build a per-segment intermediate (image looped for duration + that segment's audio)
    seg_files: list[Path] = []
    use_sfx = sfx_path is not None and sfx_path.exists()
    for i, seg in enumerate(segments):
        frame = seg["frame"]
        audio = seg["audio"]
        dur = float(seg["duration_s"])
        seg_out = work / f"seg_{i:03d}.mp4"
        sid = seg.get("id", "")
        if use_sfx and sid.startswith("item-"):
            # SFX overlaid (amix) on first ~0.3s of TTS so subtitle stays aligned.
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", f"{dur:.3f}", "-i", str(frame),
                "-i", str(audio),
                "-i", str(sfx_path),
                "-filter_complex",
                "[2:a]volume=0.6[sfx];"
                "[1:a][sfx]amix=inputs=2:duration=first:normalize=0[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(seg_out),
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", f"{dur:.3f}", "-i", str(frame),
                "-i", str(audio),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(seg_out),
            ]
        subprocess.run(cmd, check=True, capture_output=True)
        seg_files.append(seg_out)

    # Step B: concat list
    concat_list = work / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in seg_files),
        encoding="utf-8",
    )

    # Step C: concat + burn subtitles + mix bgm (optional)
    burned = work / "burned.mp4"
    subs_arg = str(srt_path).replace("\\", "/").replace(":", r"\:")  # ffmpeg filter escapes
    vf = f"subtitles='{subs_arg}':force_style='FontName=PingFang SC,FontSize=22,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2,Alignment=2,MarginV=50'"
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        str(burned),
    ]
    subprocess.run(cmd_concat, check=True, capture_output=True)

    if bgm_path and bgm_path.exists():
        cmd_bgm = [
            "ffmpeg", "-y",
            "-i", str(burned), "-stream_loop", "-1", "-i", str(bgm_path),
            "-filter_complex",
            "[1:a]volume=0.1,apad[a1];[0:a][a1]amerge=inputs=2,pan=stereo|c0<c0+c2|c1<c1+c3[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]
        subprocess.run(cmd_bgm, check=True, capture_output=True)
    else:
        # just rename burned to out
        burned.replace(out_path)

    return out_path


async def run(
    *,
    day_dir: Path,
    templates_dir: Path,
    tts_api_key: str,
    tts_group_id: str,
    tts_voice_id: str,
    bgm_path: Path | None,
    sfx_path: Path | None = None,
    date: str,
    episode: int,
    brand_title: str = "AI 投资晨读",
) -> Path:
    curated_path = day_dir / "curated.json"
    segments_path = day_dir / "segments.json"
    frames_dir = day_dir / "frames"
    audio_dir = day_dir / "audio"
    frames_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    segments = json.loads(segments_path.read_text(encoding="utf-8"))

    # 1. Render frames
    frame_paths: dict[str, Path] = {}
    outro_html = render_frame(
        curated_path=curated_path, out_dir=frames_dir, templates_dir=templates_dir,
        date=date, episode=episode, mode="outro", brand_title=brand_title,
    )
    frame_paths["outro"] = frames_dir / "outro.png"
    await screenshot_html(outro_html, frame_paths["outro"])

    # Map toc and item-N segments to rendered frames
    for seg in segments:
        sid = seg["id"]
        if sid == "toc":
            toc_html = render_frame(
                curated_path=curated_path, out_dir=frames_dir,
                templates_dir=templates_dir,
                date=date, episode=episode, mode="toc", brand_title=brand_title,
            )
            png = frames_dir / "toc.png"
            await screenshot_html(toc_html, png)
            frame_paths[sid] = png
        elif sid.startswith("item-"):
            n = int(sid.split("-")[1])
            card_html = render_frame(
                curated_path=curated_path, out_dir=frames_dir,
                templates_dir=templates_dir,
                date=date, episode=episode, mode="card", card_index=n - 1,
                brand_title=brand_title,
            )
            png = frames_dir / f"card_{n:02d}.png"
            await screenshot_html(card_html, png)
            frame_paths[sid] = png

    # 2. TTS each segment (skip failures per spec §7)
    tts = MiniMaxTTS(api_key=tts_api_key, group_id=tts_group_id, voice_id=tts_voice_id)
    enriched: list[dict] = []
    for seg in segments:
        sid = seg["id"]
        mp3 = audio_dir / f"{sid}.mp3"
        try:
            dur = tts.synthesize(seg["text"], mp3)
        except Exception as exc:
            _log.warning("tts.segment_failed", segment_id=sid, error=repr(exc))
            continue
        enriched.append({
            "id": sid,
            "text": seg["text"],
            "duration_s": dur,
            "frame": frame_paths[sid],
            "audio": mp3,
        })
    if not enriched:
        raise RuntimeError("no segments produced audio; cannot assemble video")

    # 3. Build SRT
    srt_path = day_dir / "subs.srt"
    srt_path.write_text(build_srt(enriched), encoding="utf-8")

    # 4. Assemble video
    out_mp4 = day_dir / "video.mp4"
    await assemble_video(
        segments=enriched,
        srt_path=srt_path,
        out_path=out_mp4,
        bgm_path=bgm_path,
        sfx_path=sfx_path,
    )
    return out_mp4


def main():
    from core.config import Settings, day_dir as get_day_dir, today_str
    from core.channel import load_channel
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--episode", type=int, default=1)
    parser.add_argument("--channel", default=None)
    args = parser.parse_args()
    settings = Settings()
    date = args.date or today_str(settings.timezone)
    channel_id = args.channel or settings.default_channel_id
    channel = load_channel(settings.channels_dir, channel_id)
    d = get_day_dir(settings, date, channel_id)
    bgm_file = channel.bgm or "bgm.mp3"
    sfx_file = channel.sfx or "page_turn.mp3"
    bgm = settings.assets_dir / bgm_file
    sfx = settings.assets_dir / sfx_file
    templates_dir = channel.templates_dir_override or settings.templates_dir
    asyncio.run(run(
        day_dir=d,
        templates_dir=templates_dir,
        tts_api_key=settings.minimax_api_key,
        tts_group_id=settings.minimax_group_id,
        tts_voice_id=channel.voice_id,
        bgm_path=bgm if bgm.exists() else None,
        sfx_path=sfx if sfx.exists() else None,
        date=date, episode=args.episode,
        brand_title=channel.brand_title,
    ))
    print(f"wrote {d / 'video.mp4'}")


if __name__ == "__main__":
    main()
