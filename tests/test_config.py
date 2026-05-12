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
