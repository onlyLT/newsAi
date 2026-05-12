from pathlib import Path

import yaml

from core.models import SourceConfig


def load_sources(yaml_path: Path) -> list[SourceConfig]:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return [SourceConfig.model_validate(s) for s in data["sources"]]
