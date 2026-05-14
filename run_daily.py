import argparse
import asyncio
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from core.config import Settings, day_dir, today_str
from core.logging import configure_logging, log
from pipelines.ingest import run as ingest_run
from pipelines.curate import run as curate_run
from pipelines.script import run as script_run
from pipelines.render_html import render as html_render
from pipelines.render_video import run as video_run
from pipelines.notify import notify


def _episode_number(settings: Settings, date: str) -> int:
    """Count how many prior day dirs have a video.mp4."""
    n = 1
    if not settings.dist_dir.exists():
        return n
    for d in settings.dist_dir.iterdir():
        if d.is_dir() and d.name < date and (d / "video.mp4").exists():
            n += 1
    return n


def _recent_curated_paths(settings: Settings, date: str) -> list[Path]:
    base = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(settings.timezone))
    out: list[Path] = []
    for i in range(1, 4):
        prev = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        p = settings.dist_dir / prev / "curated.json"
        if p.exists():
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args(argv)

    settings = Settings()
    date = args.date or today_str(settings.timezone)
    d = day_dir(settings, date)
    log_file = d / "run.log"
    configure_logging(settings.log_level, log_file=log_file)
    logger = log("run_daily")

    episode = _episode_number(settings, date)
    bgm = settings.assets_dir / "bgm.mp3"
    sfx = settings.assets_dir / "page_turn.mp3"

    try:
        logger.info("stage.start", stage="ingest")
        asyncio.run(ingest_run(
            settings.sources_yaml, d / "raw.json", max_age_hours=24,
        ))
        logger.info("stage.start", stage="curate")
        curate_run(
            raw_path=d / "raw.json",
            out_path=d / "curated.json",
            recent_curated_paths=_recent_curated_paths(settings, date),
            api_key=settings.anthropic_api_key,
            prompts_dir=settings.prompts_dir,
            llm_model=settings.llm_model,
            llm_base_url=settings.anthropic_base_url,
        )
        logger.info("stage.start", stage="script")
        script_run(
            curated_path=d / "curated.json",
            script_md_path=d / "script.md",
            segments_path=d / "segments.json",
            api_key=settings.anthropic_api_key,
            prompts_dir=settings.prompts_dir,
            date=date,
            llm_model=settings.llm_model,
            llm_base_url=settings.anthropic_base_url,
        )
        logger.info("stage.start", stage="render_html")
        html_render(
            curated_path=d / "curated.json",
            out_path=d / "index.html",
            templates_dir=settings.templates_dir,
            date=date, episode=episode,
        )
        logger.info("stage.start", stage="render_video")
        asyncio.run(video_run(
            day_dir=d,
            templates_dir=settings.templates_dir,
            tts_api_key=settings.minimax_api_key,
            tts_group_id=settings.minimax_group_id,
            tts_voice_id=settings.minimax_voice_id,
            bgm_path=bgm if bgm.exists() else None,
            sfx_path=sfx if sfx.exists() else None,
            date=date, episode=episode,
        ))
        logger.info("run.success", date=date, episode=episode)
        notify(
            title="AI 投资晨读 · 完成",
            message=f"{date} 第 {episode} 期已生成",
            success=True,
        )
        return 0
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("run.fail", error=str(e), traceback=tb)
        notify(
            title="AI 投资晨读 · 失败",
            message=f"{date}: {e}",
            success=False,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
