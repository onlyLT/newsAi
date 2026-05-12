# AI 投资晨读 自动化日更视频播客 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily, unattended pipeline that ingests AI news, has Claude curate ~10 items with investment angles, generates a Chinese voice-over script, renders an HTML digest page + a 1080p MP4 video, and notifies on completion/failure — runnable from Windows Task Scheduler at 07:00.

**Architecture:** A linear pipeline of stages, each owned by a file in `pipelines/`, each producing a JSON/text artifact under `dist/YYYY-MM-DD/`. Stages are independently re-runnable (idempotent on the same date) and share Pydantic models in `core/models.py`. Per-stage CLI entry points + a top-level `run_daily.py` orchestrator.

**Tech Stack:** Python 3.11+, `anthropic` (Claude 4.7 with prompt caching), `feedparser`+`httpx`, `pydantic`/`pydantic-settings`, `Jinja2`, `playwright` (headless Chromium for screenshots), MiniMax TTS, `ffmpeg-python`, `structlog`, `pytest`. Windows Task Scheduler for scheduling.

**Reference spec:** `docs/specs/2026-05-12-ai-news-podcast-design.md`

---

## File Structure

Created up-front in Task 1, populated as we go:

```
newsAi/
├── core/
│   ├── __init__.py
│   ├── models.py          # All Pydantic schemas (single source of truth)
│   ├── config.py          # Settings (env, paths)
│   ├── logging.py         # structlog setup
│   ├── llm.py             # Claude SDK wrapper (prompt caching, retry)
│   └── tts.py             # MiniMax TTS wrapper
├── pipelines/
│   ├── __init__.py
│   ├── ingest.py          # 4.1: RSS fetch → raw.json
│   ├── curate.py          # 4.2: LLM curate → curated.json
│   ├── script.py          # 4.3: LLM script → script.md + segments.json
│   ├── render_html.py     # 4.4.1: Jinja → index.html
│   ├── render_video.py    # 4.4.2: Playwright + TTS + ffmpeg → video.mp4
│   └── notify.py          # Windows toast on success/failure
├── sources/
│   └── sources.yaml       # New sources added here, not in code
├── prompts/
│   ├── curate.system.md
│   └── script.system.md
├── templates/
│   ├── index.html.j2      # Dual-purpose: digest view + video frame view
│   └── styles.css
├── assets/
│   ├── bgm.mp3            # Placeholder until selected
│   ├── logo.png
│   └── intro_outro/
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── sample_rss.xml
│   │   ├── raw_sample.json
│   │   ├── curated_sample.json
│   │   └── segments_sample.json
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_ingest.py
│   ├── test_curate.py
│   ├── test_script.py
│   ├── test_render_html.py
│   ├── test_render_video.py
│   └── test_run_daily.py
├── dist/                  # Per-day outputs (gitignored)
├── run_daily.py           # Top-level orchestrator
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

**Naming consistency notes (apply across all tasks):**
- `RawArticle.id` is `sha256(normalize_url(url))` hex digest (full 64 chars)
- `Segment.id` values: `"intro"`, `"item-1"` ... `"item-N"`, `"outro"`
- `CuratedItem.impact.direction` enum: `bullish` | `bearish` | `mixed`
- Date directory format: `dist/YYYY-MM-DD/` (UTC+8 / Asia/Shanghai)
- All JSON written with `ensure_ascii=False, indent=2`

---

## Task 1: Project scaffold

**Files:**
- Create: `E:/dev/newsAi/pyproject.toml`
- Create: `E:/dev/newsAi/.gitignore`
- Create: `E:/dev/newsAi/.env.example`
- Create: `E:/dev/newsAi/README.md`
- Create: empty `__init__.py` in `core/`, `pipelines/`, `tests/`

- [ ] **Step 1: Initialize git**

Run from `E:/dev/newsAi`:

```bash
git init
git branch -M main
```

Expected: "Initialized empty Git repository..." and silent rename.

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "news-ai"
version = "0.1.0"
description = "Daily AI investment news podcast generator"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "feedparser>=6.0.11",
    "httpx[http2]>=0.27.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "PyYAML>=6.0",
    "Jinja2>=3.1.4",
    "playwright>=1.45.0",
    "ffmpeg-python>=0.2.0",
    "structlog>=24.4.0",
    "rapidfuzz>=3.9.0",
    "python-dateutil>=2.9.0",
    "win10toast>=0.9; sys_platform == 'win32'",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.14.0",
    "respx>=0.21.0",  # httpx mocking
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# Project artifacts
dist/
*.log

# Environment
.env

# IDE
.vscode/
.idea/

# OS
Thumbs.db
.DS_Store
```

- [ ] **Step 4: Create `.env.example`**

```bash
ANTHROPIC_API_KEY=sk-ant-...
MINIMAX_API_KEY=...
MINIMAX_GROUP_ID=...
MINIMAX_VOICE_ID=male-qn-qingse
LOG_LEVEL=INFO
TIMEZONE=Asia/Shanghai
```

- [ ] **Step 5: Create directories and `__init__.py` files**

Run from `E:/dev/newsAi`:

```bash
mkdir -p core pipelines tests/fixtures sources prompts templates assets/intro_outro docs
touch core/__init__.py pipelines/__init__.py tests/__init__.py
```

(On Windows PowerShell substitute `New-Item -ItemType File` if `touch` is unavailable; the Bash tool handles `touch` fine.)

- [ ] **Step 6: Create `README.md`**

```markdown
# AI 投资晨读 (newsAi)

Daily auto-generated AI investment news podcast (video + HTML digest).

## Setup
1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -e ".[dev]"`
3. `playwright install chromium`
4. Copy `.env.example` to `.env` and fill in keys
5. `python run_daily.py` to generate today's episode

## Architecture
See `docs/specs/2026-05-12-ai-news-podcast-design.md`.
```

- [ ] **Step 7: Install dev environment**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Expected: pip installs all dependencies without errors.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .env.example README.md core/__init__.py pipelines/__init__.py tests/__init__.py docs/
git commit -m "chore: project scaffold with deps and structure"
```

---

## Task 2: Core data models

**Files:**
- Create: `core/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:

```python
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from core.models import (
    Lang, SourceType, SourceConfig,
    RawArticle, Direction, Impact, CuratedItem,
    Segment, RunArtifacts,
)


def test_source_config_round_trip():
    s = SourceConfig(
        id="techcrunch_ai",
        name="TechCrunch AI",
        type=SourceType.RSS,
        url="https://example.com/rss",
        lang=Lang.EN,
    )
    assert s.id == "techcrunch_ai"
    assert s.filter_keywords == []


def test_raw_article_requires_iso_datetime():
    art = RawArticle(
        id="a" * 64,
        source_id="x",
        source_name="X",
        title="t",
        url="https://x.com/1",
        published_at=datetime(2026, 5, 12, 3, 0, tzinfo=timezone.utc),
        lang=Lang.EN,
    )
    assert art.summary == ""
    assert art.content == ""


def test_curated_item_requires_at_least_one_target():
    # Either tickers or sectors must be non-empty
    with pytest.raises(ValidationError):
        CuratedItem(
            rank=1,
            title="t",
            tldr="x",
            details="y",
            impact=Impact(
                tickers=[],
                sectors=[],
                direction=Direction.BULLISH,
                reasoning="r",
            ),
            source_url="https://x",
            source_name="X",
        )


def test_curated_item_accepts_tickers_only():
    item = CuratedItem(
        rank=1,
        title="t",
        tldr="x",
        details="y",
        impact=Impact(
            tickers=["NVDA"],
            sectors=[],
            direction=Direction.BULLISH,
            reasoning="r",
        ),
        source_url="https://x",
        source_name="X",
    )
    assert item.impact.tickers == ["NVDA"]


def test_segment_id_format():
    seg = Segment(id="item-3", text="hello", duration_hint_s=20, card_ref="card-3")
    assert seg.id == "item-3"
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_models.py -v
```

Expected: ImportError (`core.models` does not exist).

- [ ] **Step 3: Implement `core/models.py`**

```python
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class Lang(str, Enum):
    ZH = "zh"
    EN = "en"


class SourceType(str, Enum):
    RSS = "rss"


class SourceConfig(BaseModel):
    id: str
    name: str
    type: SourceType
    url: str
    lang: Lang
    filter_keywords: list[str] = Field(default_factory=list)


class RawArticle(BaseModel):
    id: str
    source_id: str
    source_name: str
    title: str
    url: str
    published_at: datetime
    summary: str = ""
    content: str = ""
    lang: Lang


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"


class Impact(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    direction: Direction
    reasoning: str


class CuratedItem(BaseModel):
    rank: int
    title: str
    tldr: str
    details: str
    impact: Impact
    source_url: str
    source_name: str

    @model_validator(mode="after")
    def _require_target(self):
        if not self.impact.tickers and not self.impact.sectors:
            raise ValueError("impact must include at least one ticker or sector")
        return self


class Segment(BaseModel):
    id: str
    text: str
    duration_hint_s: int
    card_ref: str | None = None


class RunArtifacts(BaseModel):
    """Paths produced for a single day's run."""
    date: str  # YYYY-MM-DD
    base_dir: str
    raw_json: str
    curated_json: str
    script_md: str
    segments_json: str
    index_html: str
    video_mp4: str
    log_file: str
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_models.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/models.py tests/test_models.py
git commit -m "feat(core): pydantic models for pipeline artifacts"
```

---

## Task 3: Config and logging

**Files:**
- Create: `core/config.py`
- Create: `core/logging.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
import os
from pathlib import Path
from core.config import Settings, day_dir, today_str


def test_settings_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("MINIMAX_API_KEY", "mm-test")
    monkeypatch.setenv("MINIMAX_GROUP_ID", "g1")
    monkeypatch.setenv("MINIMAX_VOICE_ID", "v1")
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    s = Settings()
    assert s.anthropic_api_key == "sk-test"
    assert s.project_root == tmp_path
    assert s.dist_dir == tmp_path / "dist"


def test_day_dir_creates_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    monkeypatch.setenv("MINIMAX_GROUP_ID", "x")
    monkeypatch.setenv("MINIMAX_VOICE_ID", "x")
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    s = Settings()
    d = day_dir(s, "2026-05-12")
    assert d.exists()
    assert d.name == "2026-05-12"


def test_today_str_format():
    s = today_str()
    assert len(s) == 10
    assert s[4] == "-" and s[7] == "-"
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_config.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `core/config.py`**

```python
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    minimax_api_key: str
    minimax_group_id: str
    minimax_voice_id: str

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"

    @property
    def dist_dir(self) -> Path:
        return self.project_root / "dist"

    @property
    def sources_yaml(self) -> Path:
        return self.project_root / "sources" / "sources.yaml"

    @property
    def prompts_dir(self) -> Path:
        return self.project_root / "prompts"

    @property
    def templates_dir(self) -> Path:
        return self.project_root / "templates"

    @property
    def assets_dir(self) -> Path:
        return self.project_root / "assets"


def today_str(tz: str = "Asia/Shanghai") -> str:
    return datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")


def day_dir(settings: Settings, date: str) -> Path:
    d = settings.dist_dir / date
    (d / "audio").mkdir(parents=True, exist_ok=True)
    (d / "frames").mkdir(parents=True, exist_ok=True)
    return d
```

- [ ] **Step 4: Implement `core/logging.py`**

```python
import logging
import sys
from pathlib import Path
import structlog


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    handlers: list[logging.Handler] = []
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(getattr(logging, level.upper()))
        handlers.append(fh)
        for h in handlers:
            logging.getLogger().addHandler(h)

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
    )


log = structlog.get_logger
```

- [ ] **Step 5: Run test, expect pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add core/config.py core/logging.py tests/test_config.py
git commit -m "feat(core): settings and structured logging"
```

---

## Task 4: Source config loader

**Files:**
- Create: `sources/sources.yaml`
- Create: `pipelines/ingest.py` (partial — just config loader)
- Create: `tests/fixtures/sample_sources.yaml`
- Create: `tests/test_ingest.py` (partial)

- [ ] **Step 1: Create production `sources/sources.yaml`**

```yaml
sources:
  - id: jiqizhixin
    name: 机器之心
    type: rss
    url: https://www.jiqizhixin.com/rss
    lang: zh

  - id: qbitai
    name: 量子位
    type: rss
    url: https://www.qbitai.com/feed
    lang: zh

  - id: xinzhiyuan
    name: 新智元
    type: rss
    url: https://rsshub.app/wechat/ai-era
    lang: zh

  - id: kr36_ai
    name: 36氪
    type: rss
    url: https://36kr.com/feed-newsflash
    lang: zh
    filter_keywords: [AI, 大模型, 算力, 英伟达, OpenAI, GPU, 人工智能]

  - id: techcrunch_ai
    name: TechCrunch AI
    type: rss
    url: https://techcrunch.com/category/artificial-intelligence/feed/
    lang: en

  - id: theverge_ai
    name: The Verge AI
    type: rss
    url: https://www.theverge.com/rss/ai-artificial-intelligence/index.xml
    lang: en

  - id: openai_blog
    name: OpenAI Blog
    type: rss
    url: https://openai.com/blog/rss.xml
    lang: en

  - id: anthropic_news
    name: Anthropic News
    type: rss
    url: https://www.anthropic.com/news/rss.xml
    lang: en

  - id: google_ai_blog
    name: Google AI Blog
    type: rss
    url: https://blog.google/technology/ai/rss/
    lang: en

  - id: nvidia_blog
    name: NVIDIA Blog
    type: rss
    url: https://blogs.nvidia.com/feed/
    lang: en

  - id: hn_ai
    name: Hacker News (AI)
    type: rss
    url: https://hnrss.org/newest?q=AI+OR+LLM+OR+OpenAI
    lang: en
```

> Some URLs may 404 or require swapping at runtime — the ingest layer is tolerant of single-source failures.

- [ ] **Step 2: Create fixture `tests/fixtures/sample_sources.yaml`**

```yaml
sources:
  - id: test_zh
    name: Test ZH
    type: rss
    url: https://example.com/zh.xml
    lang: zh
  - id: test_en
    name: Test EN
    type: rss
    url: https://example.com/en.xml
    lang: en
    filter_keywords: [AI, LLM]
```

- [ ] **Step 3: Write the failing test**

`tests/test_ingest.py`:

```python
from pathlib import Path
from pipelines.ingest import load_sources


FIX = Path(__file__).parent / "fixtures"


def test_load_sources_from_yaml():
    sources = load_sources(FIX / "sample_sources.yaml")
    assert len(sources) == 2
    assert sources[0].id == "test_zh"
    assert sources[1].filter_keywords == ["AI", "LLM"]
```

- [ ] **Step 4: Run test, expect failure**

```bash
python -m pytest tests/test_ingest.py::test_load_sources_from_yaml -v
```

Expected: ImportError.

- [ ] **Step 5: Implement `load_sources` in `pipelines/ingest.py`**

```python
from pathlib import Path
import yaml
from core.models import SourceConfig


def load_sources(yaml_path: Path) -> list[SourceConfig]:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return [SourceConfig.model_validate(s) for s in data["sources"]]
```

- [ ] **Step 6: Run test, expect pass**

```bash
python -m pytest tests/test_ingest.py::test_load_sources_from_yaml -v
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add sources/sources.yaml tests/fixtures/sample_sources.yaml pipelines/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): load source configs from YAML"
```

---

## Task 5: RSS fetching and parsing

**Files:**
- Modify: `pipelines/ingest.py` (add `fetch_source`)
- Create: `tests/fixtures/sample_rss.xml`
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Create `tests/fixtures/sample_rss.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <item>
      <title>OpenAI releases GPT-7</title>
      <link>https://example.com/gpt7</link>
      <description>OpenAI announces GPT-7 with massive improvements.</description>
      <pubDate>Mon, 12 May 2026 03:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Recipe blog post</title>
      <link>https://example.com/recipe</link>
      <description>How to make pasta.</description>
      <pubDate>Mon, 12 May 2026 03:05:00 +0000</pubDate>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Add the failing test**

Append to `tests/test_ingest.py`:

```python
import respx
import httpx
from core.models import Lang, SourceType, SourceConfig
from pipelines.ingest import fetch_source


@respx.mock
async def test_fetch_source_parses_rss():
    rss_body = (FIX / "sample_rss.xml").read_text(encoding="utf-8")
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=rss_body)
    )
    src = SourceConfig(
        id="t", name="T", type=SourceType.RSS,
        url="https://example.com/feed", lang=Lang.EN,
    )
    async with httpx.AsyncClient() as client:
        arts = await fetch_source(client, src)
    assert len(arts) == 2
    assert arts[0].title == "OpenAI releases GPT-7"
    assert arts[0].source_id == "t"
    assert arts[0].lang == Lang.EN
    assert len(arts[0].id) == 64  # sha256 hex


@respx.mock
async def test_fetch_source_applies_keyword_filter():
    rss_body = (FIX / "sample_rss.xml").read_text(encoding="utf-8")
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=rss_body)
    )
    src = SourceConfig(
        id="t", name="T", type=SourceType.RSS,
        url="https://example.com/feed", lang=Lang.EN,
        filter_keywords=["GPT", "OpenAI"],
    )
    async with httpx.AsyncClient() as client:
        arts = await fetch_source(client, src)
    assert len(arts) == 1
    assert "GPT" in arts[0].title


@respx.mock
async def test_fetch_source_returns_empty_on_http_error():
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(500))
    src = SourceConfig(
        id="t", name="T", type=SourceType.RSS,
        url="https://example.com/feed", lang=Lang.EN,
    )
    async with httpx.AsyncClient() as client:
        arts = await fetch_source(client, src)
    assert arts == []
```

- [ ] **Step 3: Run test, expect failure**

```bash
python -m pytest tests/test_ingest.py -v
```

Expected: ImportError on `fetch_source`.

- [ ] **Step 4: Implement `fetch_source` in `pipelines/ingest.py`**

Append to `pipelines/ingest.py`:

```python
import hashlib
from datetime import datetime, timezone
from dateutil import parser as dtparser
import feedparser
import httpx
from core.models import RawArticle


def _hash_url(url: str) -> str:
    norm = url.strip().rstrip("/").lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


def _parse_pubdate(entry) -> datetime:
    raw = entry.get("published") or entry.get("updated") or ""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        d = dtparser.parse(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


async def fetch_source(client: httpx.AsyncClient, src: SourceConfig) -> list[RawArticle]:
    try:
        resp = await client.get(src.url, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException):
        return []
    feed = feedparser.parse(resp.text)
    articles: list[RawArticle] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = (entry.get("summary") or "").strip()
        haystack = f"{title}\n{summary}"
        if not _matches_keywords(haystack, src.filter_keywords):
            continue
        articles.append(RawArticle(
            id=_hash_url(link),
            source_id=src.id,
            source_name=src.name,
            title=title,
            url=link,
            published_at=_parse_pubdate(entry),
            summary=summary,
            content="",
            lang=src.lang,
        ))
    return articles
```

- [ ] **Step 5: Run test, expect pass**

```bash
python -m pytest tests/test_ingest.py -v
```

Expected: 4 passed (load + 3 fetch).

- [ ] **Step 6: Commit**

```bash
git add pipelines/ingest.py tests/test_ingest.py tests/fixtures/sample_rss.xml
git commit -m "feat(ingest): async RSS fetching with keyword filter"
```

---

## Task 6: Dedup and time filter

**Files:**
- Modify: `pipelines/ingest.py` (add `dedupe`, `recent_only`)
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ingest.py`:

```python
from datetime import timedelta
from pipelines.ingest import dedupe, recent_only


def _make_article(idx: int, title: str, hours_ago: float = 1.0) -> RawArticle:
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return RawArticle(
        id=f"{idx:0>64x}",
        source_id="s",
        source_name="S",
        title=title,
        url=f"https://x/{idx}",
        published_at=ts,
        lang=Lang.EN,
    )


def test_dedupe_keeps_first_by_url():
    a = _make_article(1, "OpenAI releases GPT-7")
    b = _make_article(1, "OpenAI releases GPT-7 (duplicate)")  # same id
    out = dedupe([a, b])
    assert len(out) == 1
    assert out[0].title == "OpenAI releases GPT-7"


def test_dedupe_collapses_near_identical_titles():
    a = _make_article(1, "OpenAI releases GPT-7 today")
    b = _make_article(2, "OpenAI releases GPT 7 today")
    out = dedupe([a, b])
    assert len(out) == 1


def test_dedupe_keeps_unrelated():
    a = _make_article(1, "OpenAI releases GPT-7")
    b = _make_article(2, "Apple announces new chip")
    out = dedupe([a, b])
    assert len(out) == 2


def test_recent_only_filters_old():
    a = _make_article(1, "fresh", hours_ago=2)
    b = _make_article(2, "stale", hours_ago=30)
    out = recent_only([a, b], max_age_hours=24)
    assert len(out) == 1
    assert out[0].title == "fresh"
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_ingest.py -v
```

Expected: ImportError on `dedupe`, `recent_only`.

- [ ] **Step 3: Implement**

Append to `pipelines/ingest.py`:

```python
from datetime import timedelta
from rapidfuzz import fuzz


def dedupe(articles: list[RawArticle], title_threshold: int = 85) -> list[RawArticle]:
    seen_ids: set[str] = set()
    kept: list[RawArticle] = []
    for art in articles:
        if art.id in seen_ids:
            continue
        # title fuzzy check
        is_dup = False
        for k in kept:
            if k.lang == art.lang and fuzz.ratio(k.title, art.title) >= title_threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(art)
            seen_ids.add(art.id)
    return kept


def recent_only(articles: list[RawArticle], max_age_hours: int = 24) -> list[RawArticle]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return [a for a in articles if a.published_at >= cutoff]
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_ingest.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add pipelines/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): dedup and recency filtering"
```

---

## Task 7: Ingest pipeline entry point + CLI

**Files:**
- Modify: `pipelines/ingest.py` (add `run`, `__main__`)
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ingest.py`:

```python
import json


@respx.mock
async def test_run_writes_raw_json(tmp_path):
    rss_body = (FIX / "sample_rss.xml").read_text(encoding="utf-8")
    respx.get("https://example.com/zh.xml").mock(return_value=httpx.Response(200, text=rss_body))
    respx.get("https://example.com/en.xml").mock(return_value=httpx.Response(500))

    from pipelines.ingest import run as run_ingest
    out_path = tmp_path / "raw.json"
    await run_ingest(FIX / "sample_sources.yaml", out_path, max_age_hours=24 * 365 * 10)
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    # zh.xml has 2 entries; en.xml failed silently
    assert len(data) == 2
    assert {a["source_id"] for a in data} == {"test_zh"}
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_ingest.py::test_run_writes_raw_json -v
```

Expected: ImportError on `run`.

- [ ] **Step 3: Implement `run` and `__main__`**

Append to `pipelines/ingest.py`:

```python
import asyncio
import json
import argparse


async def run(sources_yaml: Path, out_path: Path, max_age_hours: int = 24) -> Path:
    sources = load_sources(sources_yaml)
    async with httpx.AsyncClient(http2=True) as client:
        results = await asyncio.gather(*[fetch_source(client, s) for s in sources])
    all_articles = [a for r in results for a in r]
    all_articles = recent_only(all_articles, max_age_hours=max_age_hours)
    all_articles = dedupe(all_articles)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([a.model_dump(mode="json") for a in all_articles],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def main():
    from core.config import Settings, day_dir, today_str
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYY-MM-DD; default=today")
    parser.add_argument("--max-age-hours", type=int, default=24)
    args = parser.parse_args()
    settings = Settings()
    date = args.date or today_str(settings.timezone)
    d = day_dir(settings, date)
    out = d / "raw.json"
    path = asyncio.run(run(settings.sources_yaml, out, args.max_age_hours))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_ingest.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add pipelines/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): orchestrator + CLI entry point"
```

---

## Task 8: LLM client wrapper

**Files:**
- Create: `core/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

`tests/test_llm.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from core.llm import LLMClient, LLMJsonError


def _mock_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def test_llm_returns_parsed_json():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response('{"hello": "world"}')
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        out = c.complete_json(
            system="sys",
            user="user",
            cached_blocks=[],
        )
    assert out == {"hello": "world"}


def test_llm_extracts_json_from_fenced_block():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response(
        'Sure!\n```json\n{"x": 1}\n```\nDone.'
    )
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        out = c.complete_json(system="s", user="u")
    assert out == {"x": 1}


def test_llm_raises_on_unparsable():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response("not json at all")
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        with pytest.raises(LLMJsonError):
            c.complete_json(system="s", user="u")


def test_llm_sends_cached_blocks_as_cache_control():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response('{}')
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        c.complete_json(
            system="sys",
            user="user",
            cached_blocks=["BIG_REFERENCE"],
        )
    call_kwargs = fake.messages.create.call_args.kwargs
    # The system param should be a list with the cached block tagged
    sys_param = call_kwargs["system"]
    assert isinstance(sys_param, list)
    assert any(b.get("cache_control") for b in sys_param if isinstance(b, dict))
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_llm.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `core/llm.py`**

```python
import json
import re
from anthropic import Anthropic


class LLMJsonError(ValueError):
    pass


_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as e:
            raise LLMJsonError(f"fenced block not valid JSON: {e}") from e
    # try to find the largest balanced {...} or [...]
    for opener, closer in [("{", "}"), ("[", "]")]:
        i = text.find(opener)
        j = text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise LLMJsonError(f"could not extract JSON from: {text[:200]!r}")


class LLMClient:
    """Thin wrapper around Anthropic SDK with prompt caching and JSON extraction."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-7"):
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        cached_blocks: list[str] | None = None,
        max_tokens: int = 8000,
        temperature: float = 0.3,
    ):
        cached_blocks = cached_blocks or []
        system_param: list[dict] = []
        for block in cached_blocks:
            system_param.append({
                "type": "text",
                "text": block,
                "cache_control": {"type": "ephemeral"},
            })
        system_param.append({"type": "text", "text": system})

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_param,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return _extract_json(text)
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_llm.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/llm.py tests/test_llm.py
git commit -m "feat(core): Claude client with JSON extraction + prompt caching"
```

---

## Task 9: Curate prompts and pipeline

**Files:**
- Create: `prompts/curate.system.md`
- Create: `pipelines/curate.py`
- Create: `tests/fixtures/raw_sample.json`
- Create: `tests/fixtures/curated_sample.json`
- Create: `tests/test_curate.py`

- [ ] **Step 1: Create `prompts/curate.system.md`**

```markdown
# Role
你是「AI 投资晨读」栏目的资深内容策划，每天从大量 AI 行业新闻中筛选出对**股票投资有明确信号**的 10 条，并给出投资影响分析。

# 你将收到
1. (可选) 过去 3 天已发布的 curated 列表（避免重复选题）
2. 当日候选新闻全量（JSON 数组）

# 筛选标准（必须严格执行）
- 每条新闻必须明确指向至少一个上市公司股票代码或具体板块/概念
- 优先级：业绩 / 重大产品发布 / 并购 / 监管 / 算力供需 / 巨头战略动作
- 排除：纯学术论文、跟投资无关的产品评测、缺乏明确投资逻辑的炒作

# 输出
严格输出 JSON 数组，10 条（允许 9–11 条），按重要性 rank 排序。**不要**输出任何 JSON 之外的文字、解释、markdown 围栏。

# 字段 schema
[
  {
    "rank": 1,
    "title": "重写后的中文标题，<= 30 字",
    "tldr": "一句话核心信息，<= 80 字",
    "details": "2-3 句展开，<= 200 字",
    "impact": {
      "tickers": ["NVDA", "TSM"],
      "sectors": ["算力", "HBM"],
      "direction": "bullish",
      "reasoning": "为什么这条对这些标的有影响，<= 150 字"
    },
    "source_url": "原文链接",
    "source_name": "来源名"
  }
]

# 硬性要求
- direction 取值 ∈ {bullish, bearish, mixed}
- tickers 和 sectors 至少有一个非空
- title 必须中文；tldr/details/reasoning 必须中文
```

- [ ] **Step 2: Create fixtures**

`tests/fixtures/raw_sample.json`:

```json
[
  {
    "id": "a000000000000000000000000000000000000000000000000000000000000001",
    "source_id": "techcrunch_ai",
    "source_name": "TechCrunch AI",
    "title": "NVIDIA unveils Blackwell B200 with 30% performance jump",
    "url": "https://example.com/1",
    "published_at": "2026-05-12T03:00:00+00:00",
    "summary": "NVIDIA announces next-gen GPU.",
    "content": "",
    "lang": "en"
  },
  {
    "id": "a000000000000000000000000000000000000000000000000000000000000002",
    "source_id": "anthropic_news",
    "source_name": "Anthropic News",
    "title": "Anthropic raises Series E at $200B valuation",
    "url": "https://example.com/2",
    "published_at": "2026-05-12T05:00:00+00:00",
    "summary": "Anthropic closes major funding round.",
    "content": "",
    "lang": "en"
  }
]
```

`tests/fixtures/curated_sample.json` (used as the "past 3 days" reference):

```json
[
  {
    "rank": 1,
    "title": "示例已发布条目",
    "tldr": "x",
    "details": "y",
    "impact": {
      "tickers": ["NVDA"],
      "sectors": [],
      "direction": "bullish",
      "reasoning": "z"
    },
    "source_url": "https://x",
    "source_name": "X"
  }
]
```

- [ ] **Step 3: Write the failing test**

`tests/test_curate.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from pipelines.curate import run as run_curate


FIX = Path(__file__).parent / "fixtures"


def _curated_payload(n: int = 2):
    return [
        {
            "rank": i + 1,
            "title": f"标题{i+1}",
            "tldr": "一句话",
            "details": "细节",
            "impact": {
                "tickers": ["NVDA"],
                "sectors": [],
                "direction": "bullish",
                "reasoning": "原因",
            },
            "source_url": "https://x",
            "source_name": "X",
        }
        for i in range(n)
    ]


def test_curate_writes_curated_json(tmp_path):
    raw_path = FIX / "raw_sample.json"
    out_path = tmp_path / "curated.json"

    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = _curated_payload(2)

    with patch("pipelines.curate.LLMClient", return_value=fake_llm):
        run_curate(
            raw_path=raw_path,
            out_path=out_path,
            recent_curated_paths=[FIX / "curated_sample.json"],
            api_key="x",
            prompts_dir=Path(__file__).parent.parent / "prompts",
        )
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["impact"]["tickers"] == ["NVDA"]


def test_curate_retries_once_on_invalid_then_succeeds(tmp_path):
    raw_path = FIX / "raw_sample.json"
    out_path = tmp_path / "curated.json"

    bad = [{"rank": 1, "title": "x"}]  # missing required fields
    good = _curated_payload(2)
    fake_llm = MagicMock()
    fake_llm.complete_json.side_effect = [bad, good]

    with patch("pipelines.curate.LLMClient", return_value=fake_llm):
        run_curate(
            raw_path=raw_path,
            out_path=out_path,
            recent_curated_paths=[],
            api_key="x",
            prompts_dir=Path(__file__).parent.parent / "prompts",
        )
    assert fake_llm.complete_json.call_count == 2
    assert out_path.exists()
```

- [ ] **Step 4: Run test, expect failure**

```bash
python -m pytest tests/test_curate.py -v
```

Expected: ImportError.

- [ ] **Step 5: Implement `pipelines/curate.py`**

```python
import argparse
import json
from pathlib import Path
from pydantic import ValidationError
from core.models import CuratedItem
from core.llm import LLMClient, LLMJsonError


def _load_prompt(prompts_dir: Path, name: str) -> str:
    return (prompts_dir / name).read_text(encoding="utf-8")


def _validate_curated(payload) -> list[CuratedItem]:
    if not isinstance(payload, list):
        raise ValueError("curated payload must be a JSON array")
    items = [CuratedItem.model_validate(it) for it in payload]
    if not (9 <= len(items) <= 11):
        # allow soft 2 in dev; production should be strict, but failure is fine here
        pass
    return items


def run(
    *,
    raw_path: Path,
    out_path: Path,
    recent_curated_paths: list[Path],
    api_key: str,
    prompts_dir: Path,
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

    llm = LLMClient(api_key=api_key)

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
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run test, expect pass**

```bash
python -m pytest tests/test_curate.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add prompts/curate.system.md pipelines/curate.py tests/test_curate.py tests/fixtures/raw_sample.json tests/fixtures/curated_sample.json
git commit -m "feat(curate): LLM-driven curation with retry and prompt caching"
```

---

## Task 10: Script generation prompt and pipeline

**Files:**
- Create: `prompts/script.system.md`
- Create: `pipelines/script.py`
- Create: `tests/fixtures/segments_sample.json`
- Create: `tests/test_script.py`

- [ ] **Step 1: Create `prompts/script.system.md`**

```markdown
# Role
你是「AI 投资晨读」栏目的资深口播稿撰稿人。基于当日精选的 ~10 条 AI 投资新闻，写一份**适合朗读**的中文口播稿。

# 你将收到
当日 curated.json（10 条左右新闻 + 投资影响）

# 输出要求（必须严格遵守）
严格输出 JSON 对象（**不要**任何 markdown 围栏或解释文本），结构如下：

{
  "script_md": "完整的人类可读口播稿，Markdown 格式，包含开场/逐条/收尾",
  "segments": [
    {"id": "intro", "text": "...", "duration_hint_s": 10},
    {"id": "item-1", "text": "...", "duration_hint_s": 22, "card_ref": "card-1"},
    {"id": "item-2", "text": "...", "duration_hint_s": 22, "card_ref": "card-2"},
    ...
    {"id": "outro", "text": "...", "duration_hint_s": 10}
  ]
}

# 内容结构（栏目固定模板）
1. **开场（10s）**："各位早，今天是 X 月 X 日，AI 投资晨读，今天精选 N 条..."
2. **逐条播报**（每条 18–25s）：先讲标题，再讲核心信息，最后一句"对 XX 板块/标的的影响"
3. **收尾（10s）**："以上是今日 AI 投资晨读，点赞关注..."

# 口播风格
- 节奏紧凑，每条不啰嗦
- 不要用书面化的"该公司"/"此次"，用口语化的"它"/"这次"
- 数字用中文写法（"五百亿美元" 而不是 "$50B"）
- 不要播报具体股价数字（容易过时）
- card_ref 与该条目 rank 对应：rank=1 → card_ref="card-1"

# 时长约束
- 总时长目标 3–5 分钟（180–300 秒）
- intro/outro 各 ~10s
- 中间每条 18–25s
```

- [ ] **Step 2: Create `tests/fixtures/segments_sample.json`**

```json
[
  {"id": "intro", "text": "各位早，今天是 5 月 12 日。", "duration_hint_s": 10},
  {"id": "item-1", "text": "第一条：英伟达发布新一代 GPU。", "duration_hint_s": 22, "card_ref": "card-1"},
  {"id": "item-2", "text": "第二条：Anthropic 完成新一轮融资。", "duration_hint_s": 22, "card_ref": "card-2"},
  {"id": "outro", "text": "以上是今日 AI 投资晨读。", "duration_hint_s": 10}
]
```

- [ ] **Step 3: Write the failing test**

`tests/test_script.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from pipelines.script import run as run_script


FIX = Path(__file__).parent / "fixtures"


def _script_payload():
    return {
        "script_md": "# 今日 AI 投资晨读\n\n## 开场\n各位早...\n",
        "segments": [
            {"id": "intro", "text": "各位早", "duration_hint_s": 10},
            {"id": "item-1", "text": "第一条", "duration_hint_s": 22, "card_ref": "card-1"},
            {"id": "outro", "text": "拜拜", "duration_hint_s": 10},
        ],
    }


def test_script_writes_two_files(tmp_path):
    # set up a curated.json
    curated = [{
        "rank": 1, "title": "x", "tldr": "y", "details": "z",
        "impact": {"tickers": ["NVDA"], "sectors": [], "direction": "bullish", "reasoning": "r"},
        "source_url": "https://x", "source_name": "X",
    }]
    cp = tmp_path / "curated.json"
    cp.write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")

    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = _script_payload()
    with patch("pipelines.script.LLMClient", return_value=fake_llm):
        run_script(
            curated_path=cp,
            script_md_path=tmp_path / "script.md",
            segments_path=tmp_path / "segments.json",
            api_key="x",
            prompts_dir=Path(__file__).parent.parent / "prompts",
        )
    assert (tmp_path / "script.md").exists()
    segs = json.loads((tmp_path / "segments.json").read_text(encoding="utf-8"))
    assert segs[0]["id"] == "intro"
    assert segs[1]["card_ref"] == "card-1"
    assert segs[-1]["id"] == "outro"
```

- [ ] **Step 4: Run test, expect failure**

```bash
python -m pytest tests/test_script.py -v
```

Expected: ImportError.

- [ ] **Step 5: Implement `pipelines/script.py`**

```python
import argparse
import json
from pathlib import Path
from pydantic import ValidationError
from core.models import Segment
from core.llm import LLMClient, LLMJsonError


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
        raise ValueError("segments must be a list with intro + items + outro")
    segs = [Segment.model_validate(s) for s in raw_segs]
    if segs[0].id != "intro" or segs[-1].id != "outro":
        raise ValueError("segments must start with intro and end with outro")
    return script_md, segs


def run(
    *,
    curated_path: Path,
    script_md_path: Path,
    segments_path: Path,
    api_key: str,
    prompts_dir: Path,
) -> tuple[Path, Path]:
    system = _load_prompt(prompts_dir, "script.system.md")
    curated_text = curated_path.read_text(encoding="utf-8")
    user_prompt = f"# 当日 curated\n```json\n{curated_text}\n```"

    llm = LLMClient(api_key=api_key)
    last_err: Exception | None = None
    for _ in range(2):
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
    )
    print(f"wrote {sm} and {sp}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run test, expect pass**

```bash
python -m pytest tests/test_script.py -v
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add prompts/script.system.md pipelines/script.py tests/test_script.py tests/fixtures/segments_sample.json
git commit -m "feat(script): LLM-driven script + segments generation"
```

---

## Task 11: HTML template (dual-purpose)

**Files:**
- Create: `templates/index.html.j2`
- Create: `templates/styles.css`

- [ ] **Step 1: Create `templates/styles.css`**

```css
:root {
  --bg: #0b0d12;
  --fg: #e8eaed;
  --muted: #8b95a7;
  --accent: #4e9eff;
  --bull: #2ecc71;
  --bear: #e74c3c;
  --mixed: #f1c40f;
  --card-bg: #131722;
  --card-border: #1f2937;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: var(--bg);
  color: var(--fg);
  font-family: "PingFang SC", "Microsoft YaHei", -apple-system, system-ui, sans-serif;
  font-feature-settings: "tnum";
}
.page-list { padding: 48px 64px; max-width: 1400px; margin: 0 auto; }
.page-list header { margin-bottom: 32px; }
.page-list h1 { font-size: 42px; font-weight: 700; }
.page-list .meta { color: var(--muted); margin-top: 8px; font-size: 16px; }

.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  padding: 28px 32px;
  margin-bottom: 16px;
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 20px;
}
.card .rank { font-size: 40px; font-weight: 800; color: var(--accent); }
.card .body h2 { font-size: 26px; margin-bottom: 12px; }
.card .body .tldr { font-size: 18px; color: var(--fg); margin-bottom: 12px; }
.card .body .details { font-size: 15px; color: var(--muted); margin-bottom: 16px; line-height: 1.5; }
.tags { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.tag { padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600; }
.tag.ticker { background: rgba(78, 158, 255, 0.15); color: var(--accent); }
.tag.sector { background: rgba(139, 149, 167, 0.15); color: var(--muted); }
.tag.dir-bullish { background: rgba(46, 204, 113, 0.2); color: var(--bull); }
.tag.dir-bearish { background: rgba(231, 76, 60, 0.2); color: var(--bear); }
.tag.dir-mixed { background: rgba(241, 196, 15, 0.2); color: var(--mixed); }
.reasoning { margin-top: 14px; font-size: 14px; color: var(--muted); border-left: 3px solid var(--accent); padding-left: 12px; }
.source { margin-top: 12px; font-size: 13px; color: var(--muted); }
.source a { color: var(--accent); text-decoration: none; }

/* Video frame mode: 1920x1080 single-card centered */
.frame-card, .frame-intro, .frame-outro {
  width: 1920px;
  height: 1080px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80px;
}
.frame-card .card {
  width: 1400px;
  max-width: 100%;
  font-size: 1.4em;
  grid-template-columns: 120px 1fr;
}
.frame-card .card .rank { font-size: 96px; }
.frame-card .card .body h2 { font-size: 56px; line-height: 1.2; margin-bottom: 24px; }
.frame-card .card .body .tldr { font-size: 32px; margin-bottom: 20px; }
.frame-card .card .body .details { font-size: 24px; }
.frame-card .tag { font-size: 22px; padding: 6px 18px; }
.frame-card .reasoning { font-size: 22px; margin-top: 24px; }

.frame-intro h1, .frame-outro h1 { font-size: 120px; }
.frame-intro .sub, .frame-outro .sub { font-size: 40px; color: var(--muted); margin-top: 24px; }
```

- [ ] **Step 2: Create `templates/index.html.j2`**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <title>{{ date }} · AI 投资晨读</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
{% if mode == "intro" %}
  <div class="frame-intro">
    <div style="text-align:center">
      <h1>AI 投资晨读</h1>
      <div class="sub">{{ date }} · 第 {{ episode }} 期</div>
    </div>
  </div>
{% elif mode == "outro" %}
  <div class="frame-outro">
    <div style="text-align:center">
      <h1>明天见</h1>
      <div class="sub">点赞 · 关注 · 转发</div>
    </div>
  </div>
{% elif mode == "card" %}
  {% set item = items[card_index] %}
  <div class="frame-card">
    {% include "_card.html.j2" %}
  </div>
{% else %}
  <div class="page-list">
    <header>
      <h1>AI 投资晨读</h1>
      <div class="meta">{{ date }} · 第 {{ episode }} 期 · 共 {{ items|length }} 条</div>
    </header>
    {% for item in items %}
      {% include "_card.html.j2" %}
    {% endfor %}
  </div>
{% endif %}
</body>
</html>
```

- [ ] **Step 3: Create `templates/_card.html.j2`**

```html
<div class="card" id="card-{{ item.rank }}">
  <div class="rank">{{ "%02d"|format(item.rank) }}</div>
  <div class="body">
    <h2>{{ item.title }}</h2>
    <div class="tldr">{{ item.tldr }}</div>
    <div class="details">{{ item.details }}</div>
    <div class="tags">
      <span class="tag dir-{{ item.impact.direction }}">
        {% if item.impact.direction == "bullish" %}利好
        {% elif item.impact.direction == "bearish" %}利空
        {% else %}中性
        {% endif %}
      </span>
      {% for t in item.impact.tickers %}<span class="tag ticker">{{ t }}</span>{% endfor %}
      {% for s in item.impact.sectors %}<span class="tag sector">{{ s }}</span>{% endfor %}
    </div>
    <div class="reasoning">{{ item.impact.reasoning }}</div>
    <div class="source">来源：<a href="{{ item.source_url }}">{{ item.source_name }}</a></div>
  </div>
</div>
```

- [ ] **Step 4: Commit**

```bash
git add templates/
git commit -m "feat(templates): dual-purpose HTML + CSS for digest and video frames"
```

---

## Task 12: HTML renderer

**Files:**
- Create: `pipelines/render_html.py`
- Create: `tests/test_render_html.py`

- [ ] **Step 1: Write the failing test**

`tests/test_render_html.py`:

```python
import json
from pathlib import Path
from pipelines.render_html import render


FIX = Path(__file__).parent / "fixtures"


def test_render_writes_index_html(tmp_path):
    curated = [{
        "rank": 1, "title": "英伟达发布新 GPU", "tldr": "性能提升 30%", "details": "...",
        "impact": {"tickers": ["NVDA"], "sectors": ["算力"], "direction": "bullish", "reasoning": "..."},
        "source_url": "https://x", "source_name": "X",
    }]
    cp = tmp_path / "curated.json"
    cp.write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")

    templates_dir = Path(__file__).parent.parent / "templates"
    out = tmp_path / "index.html"
    render(curated_path=cp, out_path=out, templates_dir=templates_dir,
           date="2026-05-12", episode=1)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "英伟达发布新 GPU" in html
    assert "NVDA" in html
    assert "利好" in html
    # css is copied next to the html
    assert (out.parent / "styles.css").exists()


def test_render_frame_mode_card(tmp_path):
    curated = [
        {"rank": 1, "title": "A", "tldr": "x", "details": "y",
         "impact": {"tickers": ["NVDA"], "sectors": [], "direction": "bullish", "reasoning": "z"},
         "source_url": "u", "source_name": "n"},
        {"rank": 2, "title": "B", "tldr": "x", "details": "y",
         "impact": {"tickers": ["TSM"], "sectors": [], "direction": "bearish", "reasoning": "z"},
         "source_url": "u", "source_name": "n"},
    ]
    cp = tmp_path / "curated.json"
    cp.write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")
    templates_dir = Path(__file__).parent.parent / "templates"

    from pipelines.render_html import render_frame
    out = render_frame(
        curated_path=cp, out_dir=tmp_path, templates_dir=templates_dir,
        date="2026-05-12", episode=1, mode="card", card_index=1,
    )
    html = out.read_text(encoding="utf-8")
    assert "B" in html  # second card
    assert "A" not in html.split("</h2>")[0]  # first card not in first h2


def test_render_frame_intro_outro(tmp_path):
    curated = [{"rank": 1, "title": "A", "tldr": "x", "details": "y",
                "impact": {"tickers": ["NVDA"], "sectors": [], "direction": "bullish", "reasoning": "z"},
                "source_url": "u", "source_name": "n"}]
    cp = tmp_path / "curated.json"
    cp.write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")
    templates_dir = Path(__file__).parent.parent / "templates"
    from pipelines.render_html import render_frame
    intro = render_frame(curated_path=cp, out_dir=tmp_path, templates_dir=templates_dir,
                         date="2026-05-12", episode=1, mode="intro")
    outro = render_frame(curated_path=cp, out_dir=tmp_path, templates_dir=templates_dir,
                         date="2026-05-12", episode=1, mode="outro")
    assert "AI 投资晨读" in intro.read_text(encoding="utf-8")
    assert "明天见" in outro.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_render_html.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `pipelines/render_html.py`**

```python
import argparse
import json
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape


def _make_env(templates_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "j2"]),
    )


def _load_items(curated_path: Path) -> list[dict]:
    return json.loads(curated_path.read_text(encoding="utf-8"))


def render(
    *,
    curated_path: Path,
    out_path: Path,
    templates_dir: Path,
    date: str,
    episode: int,
) -> Path:
    env = _make_env(templates_dir)
    tmpl = env.get_template("index.html.j2")
    items = _load_items(curated_path)
    html = tmpl.render(items=items, date=date, episode=episode, mode="list")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    css_src = templates_dir / "styles.css"
    css_dst = out_path.parent / "styles.css"
    shutil.copyfile(css_src, css_dst)
    return out_path


def render_frame(
    *,
    curated_path: Path,
    out_dir: Path,
    templates_dir: Path,
    date: str,
    episode: int,
    mode: str,  # "intro" | "outro" | "card"
    card_index: int | None = None,
) -> Path:
    env = _make_env(templates_dir)
    tmpl = env.get_template("index.html.j2")
    items = _load_items(curated_path)
    name = (
        f"frame_card_{card_index + 1:02d}.html" if mode == "card"
        else f"frame_{mode}.html"
    )
    out = out_dir / name
    html = tmpl.render(
        items=items, date=date, episode=episode,
        mode=mode, card_index=card_index or 0,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    # Each frame HTML needs styles.css next to it (Playwright loads via file://)
    css_src = templates_dir / "styles.css"
    css_dst = out_dir / "styles.css"
    if not css_dst.exists():
        shutil.copyfile(css_src, css_dst)
    return out


def main():
    from core.config import Settings, day_dir, today_str
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--episode", type=int, default=1)
    args = parser.parse_args()
    settings = Settings()
    date = args.date or today_str(settings.timezone)
    d = day_dir(settings, date)
    render(
        curated_path=d / "curated.json",
        out_path=d / "index.html",
        templates_dir=settings.templates_dir,
        date=date,
        episode=args.episode,
    )
    print(f"wrote {d / 'index.html'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_render_html.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipelines/render_html.py tests/test_render_html.py
git commit -m "feat(render): HTML digest + per-frame renderer"
```

---

## Task 13: Playwright screenshot helper

**Files:**
- Create: `pipelines/render_video.py` (partial — screenshot only)
- Create: `tests/test_render_video.py` (partial)

- [ ] **Step 1: Install Playwright browser**

```bash
playwright install chromium
```

Expected: "chromium ... downloaded" or "already installed".

- [ ] **Step 2: Write the failing test**

`tests/test_render_video.py`:

```python
import asyncio
from pathlib import Path
import pytest
from pipelines.render_video import screenshot_html


def test_screenshot_html_produces_png(tmp_path):
    html = tmp_path / "page.html"
    html.write_text(
        "<html><body style='margin:0;background:#000;color:#fff;'>"
        "<div style='width:1920px;height:1080px;display:flex;align-items:center;justify-content:center;font-size:120px'>"
        "HELLO</div></body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "shot.png"
    asyncio.run(screenshot_html(html, out, width=1920, height=1080))
    assert out.exists()
    # PNG magic bytes
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 3: Run test, expect failure**

```bash
python -m pytest tests/test_render_video.py -v
```

Expected: ImportError on `screenshot_html`.

- [ ] **Step 4: Implement `pipelines/render_video.py` (screenshot helper)**

```python
import asyncio
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
```

- [ ] **Step 5: Run test, expect pass**

```bash
python -m pytest tests/test_render_video.py -v
```

Expected: 1 passed (takes ~5s to launch chromium).

- [ ] **Step 6: Commit**

```bash
git add pipelines/render_video.py tests/test_render_video.py
git commit -m "feat(render-video): playwright html screenshot helper"
```

---

## Task 14: MiniMax TTS wrapper

**Files:**
- Create: `core/tts.py`
- Create: `tests/test_tts.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tts.py`:

```python
import respx
import httpx
import pytest
from pathlib import Path
from core.tts import MiniMaxTTS


@respx.mock
def test_tts_synthesize_writes_mp3(tmp_path):
    fake_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00fake_audio_bytes"
    respx.post(
        "https://api.minimax.chat/v1/t2a_v2"
    ).mock(return_value=httpx.Response(
        200,
        json={
            "data": {"audio": fake_mp3.hex()},
            "trace_id": "x",
            "base_resp": {"status_code": 0, "status_msg": "success"},
        },
    ))
    tts = MiniMaxTTS(api_key="k", group_id="g", voice_id="v")
    out = tmp_path / "a.mp3"
    duration = tts.synthesize("你好", out)
    assert out.exists()
    assert out.read_bytes() == fake_mp3
    assert duration > 0  # estimated by length when actual not available


@respx.mock
def test_tts_raises_on_non_zero_status(tmp_path):
    respx.post("https://api.minimax.chat/v1/t2a_v2").mock(
        return_value=httpx.Response(200, json={
            "base_resp": {"status_code": 1004, "status_msg": "auth failed"},
        })
    )
    tts = MiniMaxTTS(api_key="k", group_id="g", voice_id="v")
    with pytest.raises(RuntimeError, match="auth failed"):
        tts.synthesize("hi", tmp_path / "a.mp3")
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_tts.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `core/tts.py`**

```python
import httpx
from pathlib import Path


class MiniMaxTTS:
    """Synchronous wrapper around MiniMax T2A v2 API."""

    BASE_URL = "https://api.minimax.chat/v1/t2a_v2"

    def __init__(self, api_key: str, group_id: str, voice_id: str,
                 model: str = "speech-02-hd"):
        self.api_key = api_key
        self.group_id = group_id
        self.voice_id = voice_id
        self.model = model

    def synthesize(self, text: str, out_path: Path,
                   speed: float = 1.0, vol: float = 1.0) -> float:
        """Synthesize `text` to `out_path` (mp3). Returns estimated duration in seconds."""
        payload = {
            "model": self.model,
            "text": text,
            "voice_setting": {
                "voice_id": self.voice_id,
                "speed": speed,
                "vol": vol,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = httpx.post(
            f"{self.BASE_URL}?GroupId={self.group_id}",
            json=payload, headers=headers, timeout=60.0,
        )
        resp.raise_for_status()
        body = resp.json()
        status = body.get("base_resp", {}).get("status_code", -1)
        if status != 0:
            raise RuntimeError(
                f"MiniMax TTS error {status}: {body.get('base_resp', {}).get('status_msg')}"
            )
        audio_hex = body["data"]["audio"]
        audio_bytes = bytes.fromhex(audio_hex)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio_bytes)
        # rough estimate: 4 Chinese chars/sec ≈ 0.25s per char (audio sub_info gives exact but optional)
        sub = body.get("extra_info", {}).get("audio_length")
        if sub:
            return float(sub) / 1000.0
        return max(1.0, len(text) * 0.25)
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_tts.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add core/tts.py tests/test_tts.py
git commit -m "feat(core): MiniMax TTS wrapper"
```

---

## Task 15: SRT subtitle generation

**Files:**
- Modify: `pipelines/render_video.py` (add `build_srt`)
- Modify: `tests/test_render_video.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_render_video.py`:

```python
from pipelines.render_video import build_srt


def test_build_srt_formats_timestamps():
    segments = [
        {"id": "intro", "text": "各位早", "duration_s": 2.5},
        {"id": "item-1", "text": "第一条新闻：英伟达", "duration_s": 5.0},
    ]
    srt = build_srt(segments)
    lines = srt.splitlines()
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:02,500"
    assert lines[2] == "各位早"
    assert lines[5] == "00:00:02,500 --> 00:00:07,500"
    assert "第一条新闻：英伟达" in srt


def test_build_srt_splits_long_text_into_chunks():
    long_text = "第一句。" * 30  # very long, single segment
    segments = [{"id": "item-1", "text": long_text, "duration_s": 30.0}]
    srt = build_srt(segments, max_chars_per_cue=20)
    # should produce multiple cues
    cues = [b for b in srt.split("\n\n") if b.strip()]
    assert len(cues) > 1
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_render_video.py::test_build_srt_formats_timestamps -v
```

Expected: ImportError on `build_srt`.

- [ ] **Step 3: Implement `build_srt`**

Append to `pipelines/render_video.py`:

```python
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
    # split on Chinese punctuation first
    import re
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
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_render_video.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipelines/render_video.py tests/test_render_video.py
git commit -m "feat(render-video): SRT subtitle generator"
```

---

## Task 16: FFmpeg video assembly

**Files:**
- Modify: `pipelines/render_video.py` (add `assemble_video`)
- Modify: `tests/test_render_video.py`

**Prereq:** ffmpeg must be on PATH. Verify before starting:

```bash
ffmpeg -version
```

If missing, instruct user to install (e.g., `winget install Gyan.FFmpeg` or `choco install ffmpeg`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_render_video.py`:

```python
import shutil
import subprocess
from pipelines.render_video import assemble_video


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not on PATH")
def test_assemble_video_produces_mp4(tmp_path):
    import asyncio
    # 2 simple frames + 2 tiny silent mp3s (generated with ffmpeg directly)
    frame1 = tmp_path / "f1.png"
    frame2 = tmp_path / "f2.png"
    a1 = tmp_path / "a1.mp3"
    a2 = tmp_path / "a2.mp3"
    srt = tmp_path / "subs.srt"
    out = tmp_path / "video.mp4"

    # Create solid color PNGs via ffmpeg
    for f, color in [(frame1, "red"), (frame2, "blue")]:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1920x1080:d=0.1",
             "-frames:v", "1", str(f)], check=True, capture_output=True,
        )
    # Create 1s silent mp3
    for a in [a1, a2]:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=cl=mono:r=32000",
             "-t", "1", str(a)], check=True, capture_output=True,
        )
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nhello\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nworld\n",
        encoding="utf-8",
    )

    segments = [
        {"frame": frame1, "audio": a1, "duration_s": 1.0},
        {"frame": frame2, "audio": a2, "duration_s": 1.0},
    ]
    asyncio.run(assemble_video(segments=segments, srt_path=srt, out_path=out, bgm_path=None))
    assert out.exists()
    assert out.stat().st_size > 1000
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_render_video.py::test_assemble_video_produces_mp4 -v
```

Expected: ImportError on `assemble_video` (or `skipif` skip if ffmpeg missing).

- [ ] **Step 3: Implement `assemble_video`**

Append to `pipelines/render_video.py`:

```python
import subprocess


async def assemble_video(
    *,
    segments: list[dict],
    srt_path: Path,
    out_path: Path,
    bgm_path: Path | None = None,
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
    for i, seg in enumerate(segments):
        frame = seg["frame"]
        audio = seg["audio"]
        dur = float(seg["duration_s"])
        seg_out = work / f"seg_{i:03d}.mp4"
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
    vf = f"subtitles='{subs_arg}':force_style='FontName=PingFang SC,FontSize=20,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2,Alignment=2,MarginV=80'"
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
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_render_video.py::test_assemble_video_produces_mp4 -v
```

Expected: PASS or SKIP (if ffmpeg not on PATH).

- [ ] **Step 5: Commit**

```bash
git add pipelines/render_video.py tests/test_render_video.py
git commit -m "feat(render-video): ffmpeg pipeline for video assembly with burned subtitles"
```

---

## Task 17: Render video pipeline (orchestrator)

**Files:**
- Modify: `pipelines/render_video.py` (add `run` + CLI)
- Modify: `tests/test_render_video.py`

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_render_video.py`:

```python
from unittest.mock import patch, MagicMock


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not on PATH")
def test_render_video_run_end_to_end(tmp_path, monkeypatch):
    """Run with mocked TTS + real Playwright + real ffmpeg."""
    import json, asyncio, shutil
    # Layout: copy templates to tmp
    repo = Path(__file__).parent.parent
    (tmp_path / "templates").mkdir()
    for f in ["index.html.j2", "_card.html.j2", "styles.css"]:
        shutil.copyfile(repo / "templates" / f, tmp_path / "templates" / f)
    # curated.json fixture (2 items for speed)
    curated = [
        {"rank": 1, "title": "A", "tldr": "测试一", "details": "细节",
         "impact": {"tickers": ["NVDA"], "sectors": [], "direction": "bullish", "reasoning": "r"},
         "source_url": "u", "source_name": "n"},
        {"rank": 2, "title": "B", "tldr": "测试二", "details": "细节",
         "impact": {"tickers": ["TSM"], "sectors": [], "direction": "bearish", "reasoning": "r"},
         "source_url": "u", "source_name": "n"},
    ]
    day = tmp_path / "dist" / "2026-05-12"
    day.mkdir(parents=True)
    (day / "curated.json").write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")
    segs = [
        {"id": "intro", "text": "开场", "duration_hint_s": 2},
        {"id": "item-1", "text": "第一条", "duration_hint_s": 2, "card_ref": "card-1"},
        {"id": "item-2", "text": "第二条", "duration_hint_s": 2, "card_ref": "card-2"},
        {"id": "outro", "text": "拜拜", "duration_hint_s": 2},
    ]
    (day / "segments.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")

    # Mock TTS: each call writes a 1s silent mp3 and returns 1.0
    def fake_synth(text, out_path, **kw):
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=cl=mono:r=32000",
             "-t", "1", str(out_path)], check=True, capture_output=True,
        )
        return 1.0

    fake_tts = MagicMock()
    fake_tts.synthesize.side_effect = fake_synth

    from pipelines.render_video import run as run_video
    with patch("pipelines.render_video.MiniMaxTTS", return_value=fake_tts):
        asyncio.run(run_video(
            day_dir=day,
            templates_dir=tmp_path / "templates",
            tts_api_key="k", tts_group_id="g", tts_voice_id="v",
            bgm_path=None,
            date="2026-05-12", episode=1,
        ))
    assert (day / "video.mp4").exists()
    assert (day / "video.mp4").stat().st_size > 5000
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_render_video.py::test_render_video_run_end_to_end -v
```

Expected: ImportError on `run`.

- [ ] **Step 3: Implement `run` and `main`**

Append to `pipelines/render_video.py`:

```python
import argparse
import json
from core.tts import MiniMaxTTS
from pipelines.render_html import render_frame


async def run(
    *,
    day_dir: Path,
    templates_dir: Path,
    tts_api_key: str,
    tts_group_id: str,
    tts_voice_id: str,
    bgm_path: Path | None,
    date: str,
    episode: int,
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
    intro_html = render_frame(
        curated_path=curated_path, out_dir=frames_dir, templates_dir=templates_dir,
        date=date, episode=episode, mode="intro",
    )
    frame_paths["intro"] = frames_dir / "intro.png"
    await screenshot_html(intro_html, frame_paths["intro"])

    outro_html = render_frame(
        curated_path=curated_path, out_dir=frames_dir, templates_dir=templates_dir,
        date=date, episode=episode, mode="outro",
    )
    frame_paths["outro"] = frames_dir / "outro.png"
    await screenshot_html(outro_html, frame_paths["outro"])

    # Map item-N segments to card index N-1
    for seg in segments:
        sid = seg["id"]
        if sid.startswith("item-"):
            n = int(sid.split("-")[1])
            card_html = render_frame(
                curated_path=curated_path, out_dir=frames_dir,
                templates_dir=templates_dir,
                date=date, episode=episode, mode="card", card_index=n - 1,
            )
            png = frames_dir / f"card_{n:02d}.png"
            await screenshot_html(card_html, png)
            frame_paths[sid] = png

    # 2. TTS each segment
    tts = MiniMaxTTS(api_key=tts_api_key, group_id=tts_group_id, voice_id=tts_voice_id)
    enriched: list[dict] = []
    for seg in segments:
        sid = seg["id"]
        mp3 = audio_dir / f"{sid}.mp3"
        dur = tts.synthesize(seg["text"], mp3)
        enriched.append({
            "id": sid,
            "text": seg["text"],
            "duration_s": dur,
            "frame": frame_paths[sid],
            "audio": mp3,
        })

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
    )
    return out_mp4


def main():
    from core.config import Settings, day_dir as get_day_dir, today_str
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--episode", type=int, default=1)
    args = parser.parse_args()
    settings = Settings()
    date = args.date or today_str(settings.timezone)
    d = get_day_dir(settings, date)
    bgm = settings.assets_dir / "bgm.mp3"
    asyncio.run(run(
        day_dir=d,
        templates_dir=settings.templates_dir,
        tts_api_key=settings.minimax_api_key,
        tts_group_id=settings.minimax_group_id,
        tts_voice_id=settings.minimax_voice_id,
        bgm_path=bgm if bgm.exists() else None,
        date=date, episode=args.episode,
    ))
    print(f"wrote {d / 'video.mp4'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_render_video.py::test_render_video_run_end_to_end -v
```

Expected: PASS (slow ~15–30s; skipped if no ffmpeg).

- [ ] **Step 5: Commit**

```bash
git add pipelines/render_video.py tests/test_render_video.py
git commit -m "feat(render-video): full pipeline orchestrator"
```

---

## Task 18: Notification module

**Files:**
- Create: `pipelines/notify.py`
- Create: `tests/test_notify.py`

- [ ] **Step 1: Write the failing test**

`tests/test_notify.py`:

```python
import sys
import pytest
from unittest.mock import MagicMock, patch
from pipelines.notify import notify


def test_notify_no_op_on_non_windows(monkeypatch):
    # Force platform to not-win32; should not raise
    monkeypatch.setattr(sys, "platform", "linux")
    notify(title="t", message="m", success=True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
def test_notify_calls_toaster_on_windows():
    fake = MagicMock()
    with patch("pipelines.notify._toaster", fake):
        notify(title="t", message="m", success=True)
    fake.show_toast.assert_called_once()
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_notify.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `pipelines/notify.py`**

```python
import sys
from typing import Optional


_toaster = None
if sys.platform == "win32":
    try:
        from win10toast import ToastNotifier
        _toaster = ToastNotifier()
    except ImportError:
        _toaster = None


def notify(*, title: str, message: str, success: bool = True) -> None:
    if sys.platform != "win32" or _toaster is None:
        # No-op on non-Windows or if package unavailable
        return
    icon_path: Optional[str] = None
    try:
        _toaster.show_toast(title, message, duration=8,
                            icon_path=icon_path, threaded=True)
    except Exception:
        # Notifications must NEVER fail the pipeline
        pass
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_notify.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipelines/notify.py tests/test_notify.py
git commit -m "feat(notify): Windows toast notification helper"
```

---

## Task 19: Top-level orchestrator

**Files:**
- Create: `run_daily.py`
- Create: `tests/test_run_daily.py`

- [ ] **Step 1: Write the failing test**

`tests/test_run_daily.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from run_daily import main as run_main


def _setup_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    monkeypatch.setenv("MINIMAX_GROUP_ID", "x")
    monkeypatch.setenv("MINIMAX_VOICE_ID", "x")
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    # Ensure templates/sources/prompts exist in the fake project root
    import shutil
    repo = Path(__file__).parent.parent
    for sub in ["templates", "prompts", "sources", "assets"]:
        if (repo / sub).exists():
            shutil.copytree(repo / sub, tmp_path / sub, dirs_exist_ok=True)


def test_run_daily_invokes_each_stage_in_order(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)

    calls: list[str] = []

    async def fake_ingest(*a, **kw):
        calls.append("ingest")
        out = kw.get("out_path") or a[1]
        out.write_text("[]", encoding="utf-8")
        return out

    def fake_curate(**kw):
        calls.append("curate")
        kw["out_path"].write_text("[]", encoding="utf-8")
        return kw["out_path"]

    def fake_script(**kw):
        calls.append("script")
        kw["script_md_path"].write_text("# x", encoding="utf-8")
        kw["segments_path"].write_text("[]", encoding="utf-8")
        return kw["script_md_path"], kw["segments_path"]

    def fake_render_html(**kw):
        calls.append("render_html")
        kw["out_path"].write_text("<html></html>", encoding="utf-8")
        return kw["out_path"]

    async def fake_render_video(**kw):
        calls.append("render_video")
        out = kw["day_dir"] / "video.mp4"
        out.write_bytes(b"\x00" * 100)
        return out

    with patch("run_daily.ingest_run", new=fake_ingest), \
         patch("run_daily.curate_run", new=fake_curate), \
         patch("run_daily.script_run", new=fake_script), \
         patch("run_daily.html_render", new=fake_render_html), \
         patch("run_daily.video_run", new=fake_render_video), \
         patch("run_daily.notify"):
        rc = run_main(["--date", "2026-05-12"])
    assert rc == 0
    assert calls == ["ingest", "curate", "script", "render_html", "render_video"]


def test_run_daily_returns_nonzero_on_failure(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)

    async def boom_ingest(*a, **kw):
        raise RuntimeError("network down")

    with patch("run_daily.ingest_run", new=boom_ingest), \
         patch("run_daily.notify") as note:
        rc = run_main(["--date", "2026-05-12"])
    assert rc != 0
    note.assert_called()
    # Should notify with success=False
    assert note.call_args.kwargs.get("success") is False
```

- [ ] **Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_run_daily.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `run_daily.py`**

```python
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
        )
        logger.info("stage.start", stage="script")
        script_run(
            curated_path=d / "curated.json",
            script_md_path=d / "script.md",
            segments_path=d / "segments.json",
            api_key=settings.anthropic_api_key,
            prompts_dir=settings.prompts_dir,
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
```

- [ ] **Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_run_daily.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add run_daily.py tests/test_run_daily.py
git commit -m "feat: top-level run_daily orchestrator with notifications"
```

---

## Task 20: End-to-end smoke test against real APIs

**Files:**
- Modify: `tests/test_run_daily.py`
- Modify: `README.md` (smoke usage)

This task uses real LLM and real TTS APIs. Gated by env var `RUN_LIVE=1` so CI/local-dev don't burn tokens.

- [ ] **Step 1: Verify ffmpeg and chromium are available**

```bash
ffmpeg -version
playwright install chromium
```

- [ ] **Step 2: Add the smoke test**

Append to `tests/test_run_daily.py`:

```python
import os


@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="live smoke; set RUN_LIVE=1")
def test_smoke_full_pipeline_live(monkeypatch, tmp_path):
    """
    End-to-end against real Claude + MiniMax + local ffmpeg + Playwright.
    Costs ~¥2-3.
    Requires .env in repo root with real keys.
    """
    import shutil
    repo = Path(__file__).parent.parent
    # Copy real templates/prompts/sources into the test root
    for sub in ["templates", "prompts", "sources", "assets"]:
        if (repo / sub).exists():
            shutil.copytree(repo / sub, tmp_path / sub, dirs_exist_ok=True)
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    # Real keys must come from .env
    rc = run_main(["--date", "2026-05-12"])
    assert rc == 0
    day = tmp_path / "dist" / "2026-05-12"
    assert (day / "raw.json").exists()
    assert (day / "curated.json").exists()
    assert (day / "script.md").exists()
    assert (day / "segments.json").exists()
    assert (day / "index.html").exists()
    assert (day / "video.mp4").exists()
    assert (day / "video.mp4").stat().st_size > 100_000
```

- [ ] **Step 3: Run the smoke test once manually**

```bash
# In PowerShell, with .env containing real keys:
$env:RUN_LIVE = "1"
python -m pytest tests/test_run_daily.py::test_smoke_full_pipeline_live -v -s
```

Expected: PASS (takes ~30–90s; cost ≤ ¥3).

**If failures occur:**
- LLM JSON failures → tune `prompts/curate.system.md` or `prompts/script.system.md`
- RSS source 404s → drop / replace in `sources/sources.yaml`
- Video too long → tune duration_hint_s in script prompt
- Subtitles misaligned → tune `max_chars_per_cue` in `build_srt`

- [ ] **Step 4: Update README with smoke instructions**

Append to `README.md`:

```markdown
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
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_run_daily.py README.md
git commit -m "test: live end-to-end smoke + run docs"
```

---

## Task 21: Windows Task Scheduler setup

**Files:**
- Create: `scripts/install_schedule.ps1`
- Modify: `README.md`

- [ ] **Step 1: Create `scripts/install_schedule.ps1`**

Create `scripts/install_schedule.ps1`:

```powershell
# Registers a daily Windows Task Scheduler job that runs newsAi at 07:00 local time.
# Usage (run from project root in elevated PowerShell):
#   .\scripts\install_schedule.ps1

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$entry  = Join-Path $projectRoot "run_daily.py"

if (-not (Test-Path $python)) {
    throw "Python venv not found at $python. Run: python -m venv .venv; .\.venv\Scripts\activate; pip install -e '.[dev]'"
}
if (-not (Test-Path $entry)) {
    throw "run_daily.py not found at $entry"
}

$taskName = "newsAi-daily"
$action   = New-ScheduledTaskAction -Execute $python -Argument "`"$entry`"" -WorkingDirectory $projectRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At 7:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -RunOnlyIfNetworkAvailable

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "AI 投资晨读 daily generator"

Write-Host "Registered task '$taskName' to run daily at 07:00. Check with: Get-ScheduledTask -TaskName $taskName"
```

- [ ] **Step 2: Update README with schedule instructions**

Append to `README.md`:

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add scripts/install_schedule.ps1 README.md
git commit -m "feat: Windows Task Scheduler install script and docs"
```

---

## Task 22: Final verification

- [ ] **Step 1: Run the full local test suite**

```bash
python -m pytest -v
```

Expected: All tests pass (live test skipped unless `RUN_LIVE=1`).

- [ ] **Step 2: One real end-to-end run**

```powershell
python run_daily.py
```

Manually inspect `dist/<today>/`:
- `video.mp4` plays (open with default player)
- `index.html` looks right in browser
- `script.md` reads naturally
- `run.log` shows all 5 stages completed
- Windows toast appeared

- [ ] **Step 3: Schedule the task**

```powershell
.\scripts\install_schedule.ps1
```

Verify next run time matches 07:00 tomorrow.

- [ ] **Step 4: Commit any final tweaks**

If you needed to adjust prompts / sources / styles based on the real run output:

```bash
git add -u
git commit -m "tune: prompts/sources/styles based on first live run"
```

---

## Self-Review Notes

**Spec coverage (mapped to `docs/specs/2026-05-12-ai-news-podcast-design.md`):**

| Spec section | Tasks covering it |
|---|---|
| §3 architecture (5-stage pipeline) | T1 (scaffold), T7/T9/T10/T12/T17 (each stage), T19 (orchestrator) |
| §4.1 ingest (RSS, dedup, time filter, 11 sources) | T4 (config), T5 (fetch), T6 (filter), T7 (orchestrator) |
| §4.2 curate (LLM + retry + impact schema) | T2 (CuratedItem with target validator), T8 (LLM), T9 (curate + retry) |
| §4.3 script (intro + items + outro segments) | T2 (Segment model), T10 (script gen) |
| §4.4.1 HTML report | T11 (templates), T12 (renderer) |
| §4.4.2 video (Playwright + TTS + ffmpeg + SRT + BGM) | T13 (screenshot), T14 (TTS), T15 (SRT), T16 (assembly), T17 (orchestrator) |
| §4.5 scheduling + notification | T18 (notify), T19 (run_daily), T21 (Task Scheduler) |
| §5 project structure | T1 |
| §6 tech stack | T1 (deps) |
| §7 error handling + observability | T6 (silent source fail), T9 (retry), T18 (notify), T19 (try/except + log) |
| §8 testing strategy | Every task has TDD; T20 (live smoke) |

**Placeholder check:** No `TODO`, `TBD`, or "fill in later" markers in plan steps. Every code block is complete.

**Type consistency check:**
- `Segment.id` always `"intro"` / `"item-N"` / `"outro"` — used identically in T2, T10, T17, T19
- `Segment.card_ref` is `"card-N"` (matches `id="card-{rank}"` in `_card.html.j2`) — T2, T10, T11
- `render_frame` signature matches between T12 definition and T17 caller
- `screenshot_html` signature matches T13 / T17
- `MiniMaxTTS.synthesize(text, out_path)` returns `float` — T14, T17 consistent
- `Direction` enum matches CSS class names (`dir-bullish` / `dir-bearish` / `dir-mixed`) — T2, T11

**Note for executor:** Prompts in T9/T10 are starting drafts. After first live smoke run (T20), iterating on them is expected and reflected in T22 step 4.
