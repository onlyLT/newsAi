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
