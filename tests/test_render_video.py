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
