# AI 投资晨读 (newsAi)

Daily auto-generated AI investment news podcast (video + HTML digest).

## Setup
1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -e ".[dev]"`
3. `playwright install chromium`
4. Install **ffmpeg** and ensure `ffmpeg` is on PATH (Windows: `winget install Gyan.FFmpeg` or `choco install ffmpeg`)
5. Copy `.env.example` to `.env` and fill in keys
6. `python run_daily.py` to generate today's episode

## Architecture
See `docs/specs/2026-05-12-ai-news-podcast-design.md`.
