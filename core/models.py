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
