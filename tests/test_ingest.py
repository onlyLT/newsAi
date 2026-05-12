from pathlib import Path
from pipelines.ingest import load_sources


FIX = Path(__file__).parent / "fixtures"


def test_load_sources_from_yaml():
    sources = load_sources(FIX / "sample_sources.yaml")
    assert len(sources) == 2
    assert sources[0].id == "test_zh"
    assert sources[1].filter_keywords == ["AI", "LLM"]
