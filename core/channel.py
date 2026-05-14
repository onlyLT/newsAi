"""
Channel model and loader for the multi-channel architecture.

Each channel has its own sources, prompts, voice/brand config, and
publish settings. Channels live under channels/{channel_id}/.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class PublishConfig(BaseModel):
    tid: int
    title_prefix: str
    base_tags: list[str]


class CoverConfig(BaseModel):
    """Optional manual override of cover-frame block coords (at 1920x1080).
    Each block is [left, top, right, bottom] in pixels. If absent, auto-detect."""
    top_block: Optional[list[int]] = None
    bottom_block: Optional[list[int]] = None


class Channel(BaseModel):
    id: str
    name: str
    brand_title: str
    voice_id: str
    voice_speed: float = 1.1
    bgm: str = ""
    sfx: str = ""
    publish: PublishConfig
    cover: Optional[CoverConfig] = None

    # root path — set by loader, not from yaml; excluded from serialisation
    root: Path = Field(exclude=True, default=Path("."))

    model_config = {"arbitrary_types_allowed": True}

    @property
    def sources_yaml(self) -> Path:
        return self.root / "sources.yaml"

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"

    @property
    def templates_dir_override(self) -> Optional[Path]:
        """Return channel-local templates/ dir if it exists, else None."""
        d = self.root / "templates"
        return d if d.exists() else None


def load_channel(channels_dir: Path, channel_id: str) -> Channel:
    """Load and return a Channel for the given channel_id."""
    ch_dir = channels_dir / channel_id
    yaml_path = ch_dir / "channel.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"channel.yaml not found: {yaml_path}")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return Channel(root=ch_dir, **data)


def list_channels(channels_dir: Path) -> list[str]:
    """Return sorted channel IDs (subdirs of channels/ with channel.yaml)."""
    if not channels_dir.exists():
        return []
    return sorted(
        d.name
        for d in channels_dir.iterdir()
        if d.is_dir() and (d / "channel.yaml").exists()
    )
