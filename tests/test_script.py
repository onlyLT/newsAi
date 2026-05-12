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
