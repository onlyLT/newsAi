import argparse
import asyncio
import json
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from core.channel import Channel, list_channels, load_channel
from core.config import Settings, day_dir, today_str
from core.logging import configure_logging, log
from pipelines.ingest import run as ingest_run
from pipelines.curate import run as curate_run
from pipelines.script import run as script_run
from pipelines.render_html import render as html_render
from pipelines.render_video import run as video_run
from pipelines.publish import run as publish_run
from pipelines.notify import notify


def _episode_number(settings: Settings, channel_id: str, date: str) -> int:
    """Count how many prior day dirs (for this channel) have a video.mp4."""
    n = 1
    ch_dist = settings.dist_dir / channel_id
    if not ch_dist.exists():
        return n
    for d in ch_dist.iterdir():
        if d.is_dir() and d.name < date and (d / "video.mp4").exists():
            n += 1
    return n


def _recent_curated_paths(settings: Settings, channel_id: str, date: str) -> list[Path]:
    base = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(settings.timezone))
    out: list[Path] = []
    for i in range(1, 4):
        prev = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        p = settings.dist_dir / channel_id / prev / "curated.json"
        if p.exists():
            out.append(p)
    return out


_STAGE_ORDER = ["ingest", "curate", "script", "render_html", "render_video", "cover", "publish"]


def _run_channel(
    channel: Channel,
    date: str,
    settings: Settings,
    start_stage: str,
) -> int:
    """Run all pipeline stages for one channel. Returns 0 on success, 1 on failure."""

    def _skip(stage: str) -> bool:
        return _STAGE_ORDER.index(stage) < _STAGE_ORDER.index(start_stage)

    channel_id = channel.id
    d = day_dir(settings, date, channel_id)
    log_file = d / "run.log"
    configure_logging(settings.log_level, log_file=log_file)
    logger = log(f"run_daily.{channel_id}")

    episode = _episode_number(settings, channel_id, date)
    templates_dir = channel.templates_dir_override or settings.templates_dir

    # Resolve asset paths from channel config
    bgm_file = channel.bgm if channel.bgm else "bgm.mp3"
    sfx_file = channel.sfx if channel.sfx else "page_turn.mp3"
    bgm = settings.assets_dir / bgm_file
    sfx = settings.assets_dir / sfx_file

    try:
        if not _skip("ingest"):
            logger.info("stage.start", stage="ingest")
            asyncio.run(ingest_run(
                channel.sources_yaml, d / "raw.json", max_age_hours=24,
            ))
        if not _skip("curate"):
            logger.info("stage.start", stage="curate")
            curate_run(
                raw_path=d / "raw.json",
                out_path=d / "curated.json",
                recent_curated_paths=_recent_curated_paths(settings, channel_id, date),
                api_key=settings.anthropic_api_key,
                prompts_dir=channel.prompts_dir,
                llm_model=settings.llm_model,
                llm_base_url=settings.anthropic_base_url,
            )
        if not _skip("script"):
            logger.info("stage.start", stage="script")
            script_run(
                curated_path=d / "curated.json",
                script_md_path=d / "script.md",
                segments_path=d / "segments.json",
                api_key=settings.anthropic_api_key,
                prompts_dir=channel.prompts_dir,
                date=date,
                llm_model=settings.llm_model,
                llm_base_url=settings.anthropic_base_url,
            )
        if not _skip("render_html"):
            logger.info("stage.start", stage="render_html")
            html_render(
                curated_path=d / "curated.json",
                out_path=d / "index.html",
                templates_dir=templates_dir,
                date=date,
                episode=episode,
                brand_title=channel.brand_title,
            )
        if not _skip("render_video"):
            logger.info("stage.start", stage="render_video")
            asyncio.run(video_run(
                day_dir=d,
                templates_dir=templates_dir,
                tts_api_key=settings.minimax_api_key,
                tts_group_id=settings.minimax_group_id,
                tts_voice_id=channel.voice_id,
                bgm_path=bgm if bgm.exists() else None,
                sfx_path=sfx if sfx.exists() else None,
                date=date,
                episode=episode,
                brand_title=channel.brand_title,
            ))
        # Stage 6: compose channel-branded cover image
        if not _skip("cover"):
            logger.info("stage.start", stage="cover")
            try:
                from pipelines.cover import build_for_episode
                curated = json.loads((d / "curated.json").read_text(encoding="utf-8"))
                build_for_episode(channel, curated, date, d / "cover.png")
                logger.info("stage.done", stage="cover")
            except Exception as cover_err:
                # Cover failure isn't fatal — publish will fall back to toc.png
                logger.warning("stage.cover_failed", error=str(cover_err))

        # Stage 7: optional B站 publish
        published = False
        if settings.auto_publish and not _skip("publish"):
            logger.info("stage.start", stage="publish")
            try:
                publish_run(
                    video_path=d / "video.mp4",
                    curated_path=d / "curated.json",
                    date=date,
                    episode=episode,
                    channel=channel,
                )
                published = True
                logger.info("stage.done", stage="publish")
            except Exception as pub_err:
                logger.error(
                    "stage.fail",
                    stage="publish",
                    error=str(pub_err),
                )
                notify(
                    title=f"{channel.name} · 发布失败",
                    message=f"{date} B站上传失败: {pub_err}",
                    success=False,
                )

        logger.info("run.success", date=date, episode=episode, channel=channel_id)
        publish_note = "，已发布到 B站" if published else ""
        notify(
            title=f"{channel.name} · 完成",
            message=f"{date} 第 {episode} 期已生成{publish_note}",
            success=True,
        )
        return 0
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("run.fail", error=str(e), traceback=tb, channel=channel_id)
        notify(
            title=f"{channel.name} · 失败",
            message=f"{date}: {e}",
            success=False,
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument(
        "--start-stage",
        default="ingest",
        choices=_STAGE_ORDER,
        help="Resume from this stage onward (skips earlier stages). Default: ingest (full run).",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="Channel ID. If not given, runs all channels in channels/ sequentially.",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    date = args.date or today_str(settings.timezone)

    # Determine which channels to run
    if args.channel:
        channel_ids = [args.channel]
    else:
        channel_ids = list_channels(settings.channels_dir)
        if not channel_ids:
            # Fallback if channels/ dir is empty — shouldn't happen in production
            channel_ids = ["ai-invest"]

    overall_rc = 0
    for channel_id in channel_ids:
        try:
            channel = load_channel(settings.channels_dir, channel_id)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            overall_rc = 1
            continue

        rc = _run_channel(channel, date, settings, args.start_stage)
        if rc != 0:
            overall_rc = rc
        # Per-channel failure does NOT stop the next channel

    return overall_rc


if __name__ == "__main__":
    sys.exit(main())
