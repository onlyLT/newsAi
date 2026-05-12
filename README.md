# AI 投资晨读 (newsAi)

Daily auto-generated AI investment news podcast (video + HTML digest).

## Setup
1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -e ".[dev]"`
3. `playwright install chromium`
4. Install **ffmpeg** and ensure `ffmpeg` is on PATH (Windows: `winget install Gyan.FFmpeg` or `choco install ffmpeg`)
5. Copy `.env.example` to `.env` and fill in keys
6. `python run_daily.py` to generate today's episode

## LLM provider

The pipeline uses DeepSeek V4 Flash by default (cheaper, ~10x less per run than Claude Opus). To switch to Anthropic Claude:

1. Comment out `ANTHROPIC_BASE_URL` in `.env`
2. Set `LLM_MODEL=claude-opus-4-7` (or any current Claude model)
3. Put your Anthropic API key in `ANTHROPIC_API_KEY`

The `anthropic` Python SDK is provider-agnostic when given the right base URL; no code changes needed.

## Architecture
See `docs/specs/2026-05-12-ai-news-podcast-design.md`.

## Running

- Once per day: `python run_daily.py`
- Specific date: `python run_daily.py --date 2026-05-12`
- Re-run single stage: `python -m pipelines.curate --date 2026-05-12`
- Live smoke (costs ~¥3): `$env:RUN_LIVE="1"; pytest tests/test_run_daily.py::test_smoke_full_pipeline_live -v -s`

## Outputs (per day)

`dist/YYYY-MM-DD/`:
- `raw.json` — all fetched articles
- `curated.json` — top 10 with investment analysis
- `script.md` — readable script
- `segments.json` — TTS-ready segments
- `index.html` + `styles.css` — daily digest page
- `audio/*.mp3` — per-segment TTS
- `frames/*.png` — per-segment video frames
- `subs.srt` — burned-in subtitles
- `video.mp4` — final 1080p video
- `run.log` — structured log

## Schedule (Windows)

To run automatically every day at 07:00 local:

```powershell
# In an elevated PowerShell from the project root:
.\scripts\install_schedule.ps1
```

To verify:
```powershell
Get-ScheduledTask -TaskName "newsAi-daily" | Get-ScheduledTaskInfo
```

To remove:
```powershell
Unregister-ScheduledTask -TaskName "newsAi-daily" -Confirm:$false
```

If a run fails, a Windows toast notification appears, and details are in `dist/YYYY-MM-DD/run.log`.
