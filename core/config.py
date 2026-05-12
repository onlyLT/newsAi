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
    llm_model: str = "deepseek-v4-flash"

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
