import argparse
import json
from pathlib import Path
import structlog
from pydantic import ValidationError
from core.models import CuratedItem
from core.llm import LLMClient, LLMJsonError

_log = structlog.get_logger(__name__)


def _load_prompt(prompts_dir: Path, name: str) -> str:
    return (prompts_dir / name).read_text(encoding="utf-8")


def _validate_curated(payload) -> list[CuratedItem]:
    if not isinstance(payload, list):
        raise ValueError("curated payload must be a JSON array")
    return [CuratedItem.model_validate(it) for it in payload]


def run(
    *,
    raw_path: Path,
    out_path: Path,
    recent_curated_paths: list[Path],
    api_key: str,
    prompts_dir: Path,
    llm_model: str = "deepseek-v4-flash",
) -> Path:
    system = _load_prompt(prompts_dir, "curate.system.md")
    raw_text = raw_path.read_text(encoding="utf-8")
    cached_blocks: list[str] = []
    if recent_curated_paths:
        joined = "\n\n".join(
            f"=== {p.name} ===\n{p.read_text(encoding='utf-8')}"
            for p in recent_curated_paths if p.exists()
        )
        if joined.strip():
            cached_blocks.append(f"# 过去 3 天已发布 curated（避免重复选题）\n{joined}")

    user_prompt = f"# 当日候选新闻全量\n```json\n{raw_text}\n```"

    llm = LLMClient(api_key=api_key, model=llm_model)

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            payload = llm.complete_json(
                system=system,
                user=user_prompt,
                cached_blocks=cached_blocks,
                max_tokens=8000,
                temperature=0.3,
            )
            items = _validate_curated(payload)
            break
        except (ValidationError, ValueError, LLMJsonError) as e:
            last_err = e
            _log.warning("curate.attempt_failed", attempt=attempt + 1, error=repr(e))
            continue
    else:
        raise RuntimeError(f"curate failed after 2 attempts: {last_err}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([it.model_dump(mode="json") for it in items],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def main():
    from core.config import Settings, day_dir, today_str
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    settings = Settings()
    date = args.date or today_str(settings.timezone)
    d = day_dir(settings, date)

    # find past 3 days' curated.json if they exist
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    base = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(settings.timezone))
    recent = []
    for i in range(1, 4):
        prev = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        p = settings.dist_dir / prev / "curated.json"
        if p.exists():
            recent.append(p)

    out = run(
        raw_path=d / "raw.json",
        out_path=d / "curated.json",
        recent_curated_paths=recent,
        api_key=settings.anthropic_api_key,
        prompts_dir=settings.prompts_dir,
        llm_model=settings.llm_model,
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
