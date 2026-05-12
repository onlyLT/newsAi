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
    # Frame must render the SECOND card (rank-2 "B"), not the first
    assert "<h2>B</h2>" in html
    assert "<h2>A</h2>" not in html
    assert 'id="card-2"' in html
    assert 'id="card-1"' not in html


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
