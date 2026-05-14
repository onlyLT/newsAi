import argparse
import json
from pathlib import Path
import structlog
from pydantic import ValidationError
from core.models import Segment
from core.llm import LLMClient, LLMJsonError


_log = structlog.get_logger(__name__)


def _load_prompt(prompts_dir: Path, name: str) -> str:
    return (prompts_dir / name).read_text(encoding="utf-8")


def _validate_script_payload(payload) -> tuple[str, list[Segment]]:
    if not isinstance(payload, dict):
        raise ValueError("script payload must be a JSON object")
    script_md = payload.get("script_md", "")
    raw_segs = payload.get("segments")
    if not isinstance(script_md, str) or not script_md.strip():
        raise ValueError("script_md missing")
    if not isinstance(raw_segs, list) or len(raw_segs) < 3:
        raise ValueError("segments must be a list with toc + items + outro")
    segs = [Segment.model_validate(s) for s in raw_segs]
    if segs[0].id != "toc" or segs[-1].id != "outro":
        raise ValueError("segments must start with toc and end with outro")
    return script_md, segs


def run(
    *,
    curated_path: Path,
    script_md_path: Path,
    segments_path: Path,
    api_key: str,
    prompts_dir: Path,
    date: str,
    llm_model: str = "deepseek-v4-flash",
    llm_base_url: str | None = None,
) -> tuple[Path, Path]:
    system = _load_prompt(prompts_dir, "script.system.md")
    curated_text = curated_path.read_text(encoding="utf-8")
    user_prompt = (
        f"# 今天日期\n{date}（开场报这个日期，按中文口语化念，例如 5 月 14 日）\n\n"
        f"# 当日 curated\n```json\n{curated_text}\n```"
    )

    llm = LLMClient(api_key=api_key, model=llm_model, base_url=llm_base_url)
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            payload = llm.complete_json(
                system=system,
                user=user_prompt,
                max_tokens=6000,
                temperature=0.5,
            )
            script_md, segments = _validate_script_payload(payload)
            break
        except (ValidationError, ValueError, LLMJsonError) as e:
            last_err = e
            _log.warning("script.attempt_failed", attempt=attempt + 1, error=repr(e))
            continue
    else:
        raise RuntimeError(f"script generation failed: {last_err}")

    script_md_path.parent.mkdir(parents=True, exist_ok=True)
    script_md_path.write_text(script_md, encoding="utf-8")
    segments_path.write_text(
        json.dumps([s.model_dump(mode="json") for s in segments],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return script_md_path, segments_path


def main():
    from core.config import Settings, day_dir, today_str
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    settings = Settings()
    date = args.date or today_str(settings.timezone)
    d = day_dir(settings, date)
    sm, sp = run(
        curated_path=d / "curated.json",
        script_md_path=d / "script.md",
        segments_path=d / "segments.json",
        api_key=settings.anthropic_api_key,
        prompts_dir=settings.prompts_dir,
        date=date,
        llm_model=settings.llm_model,
        llm_base_url=settings.anthropic_base_url,
    )
    print(f"wrote {sm} and {sp}")


if __name__ == "__main__":
    main()
