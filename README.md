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

## Web dashboard

Local control panel for triggering runs, editing prompts, previewing publish metadata.

```powershell
cd E:\dev\newsAi
.\.venv\Scripts\python.exe -m uvicorn web.main:app --port 8765
# Open http://localhost:8765
```

For development with auto-reload:

```powershell
.\.venv\Scripts\python.exe -m uvicorn web.main:app --port 8765 --reload
```

### Panels

- **Dashboard** — today's episode card (video player, file size, B站 link) + past 30 days grid
- **Run** — date picker, run all / re-run single stage buttons, live log via SSE
- **Prompts** — edit `curate.system.md` / `script.system.md` inline, save or save + re-run
- **Publish** — preview auto-generated B站 metadata (editable), cover image, one-click publish

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

## B站自动发布

The pipeline can auto-upload each day's `video.mp4` to Bilibili using [biliup-rs](https://github.com/biliup/biliup-rs) (binary already placed at `.venv/Scripts/biliup.exe`).

### One-time setup (login)

Activate the venv, then scan the QR code that biliup prints in your terminal with the Bilibili app:

```powershell
.venv\Scripts\activate
biliup login
```

Credentials are saved to `cookies.json` in the current directory. Keep this file out of git (it's already in `.gitignore`).

### Enable auto-publish

In your `.env`:

```
AUTO_PUBLISH=1
```

The publish stage runs after video rendering. If it fails, the run still counts as successful (the video exists locally); a separate toast notification is shown for the upload failure.

### Dry-run a single day

Builds metadata and writes `dist/YYYY-MM-DD/publish.json` without uploading:

```powershell
python -m pipelines.publish --date 2026-05-14 --dry-run
```

### Publish a single day manually

```powershell
python -m pipelines.publish --date 2026-05-14
```

### Metadata generated per episode

| Field | Value |
|-------|-------|
| `tid` | 188 (科技 → 数码) |
| `copyright` | 1 (自制) |
| `title` | `AI 投资晨读 · M月D日 · 公司1/公司2/公司3 等 N 条` (≤ 80 chars) |
| `desc` | 本期精选 N 条… + numbered titles + closing line (≤ 250 chars) |
| `tag` | AI,投资,科技,日更,AI晨读,财经 + top company names (≤ 12 tags) |
