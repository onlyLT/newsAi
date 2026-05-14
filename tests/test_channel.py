"""Tests for core/channel.py — loader, list, and model behavior."""
import pytest
from pathlib import Path

import yaml

from core.channel import Channel, PublishConfig, load_channel, list_channels


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_channel_yaml(ch_dir: Path, data: dict) -> None:
    ch_dir.mkdir(parents=True, exist_ok=True)
    (ch_dir / "channel.yaml").write_text(
        yaml.dump(data, allow_unicode=True), encoding="utf-8"
    )


def _minimal_channel_data(channel_id: str = "test-ch") -> dict:
    return {
        "id": channel_id,
        "name": "测试频道",
        "brand_title": "测试频道早报",
        "voice_id": "Podcast_girl",
        "voice_speed": 1.1,
        "bgm": "",
        "sfx": "page_turn.mp3",
        "publish": {
            "tid": 188,
            "title_prefix": "早报",
            "base_tags": ["AI", "投资"],
        },
    }


# ---------------------------------------------------------------------------
# test_load_channel
# ---------------------------------------------------------------------------

def test_load_channel_round_trip(tmp_path):
    """load_channel returns a Channel with correct field values."""
    ch_dir = tmp_path / "channels" / "test-ch"
    _write_channel_yaml(ch_dir, _minimal_channel_data("test-ch"))

    ch = load_channel(tmp_path / "channels", "test-ch")
    assert ch.id == "test-ch"
    assert ch.name == "测试频道"
    assert ch.brand_title == "测试频道早报"
    assert ch.voice_id == "Podcast_girl"
    assert ch.voice_speed == 1.1
    assert ch.bgm == ""
    assert ch.sfx == "page_turn.mp3"
    assert ch.publish.tid == 188
    assert ch.publish.title_prefix == "早报"
    assert ch.publish.base_tags == ["AI", "投资"]


def test_load_channel_root_path(tmp_path):
    """Channel.root is set to the channel sub-directory."""
    ch_dir = tmp_path / "channels" / "test-ch"
    _write_channel_yaml(ch_dir, _minimal_channel_data("test-ch"))
    ch = load_channel(tmp_path / "channels", "test-ch")
    assert ch.root == ch_dir


def test_load_channel_missing_yaml_raises(tmp_path):
    """load_channel raises FileNotFoundError when channel.yaml is absent."""
    channels_dir = tmp_path / "channels"
    channels_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        load_channel(channels_dir, "nonexistent")


def test_load_channel_sources_yaml_property(tmp_path):
    """Channel.sources_yaml points to sources.yaml inside the channel dir."""
    ch_dir = tmp_path / "channels" / "test-ch"
    _write_channel_yaml(ch_dir, _minimal_channel_data("test-ch"))
    ch = load_channel(tmp_path / "channels", "test-ch")
    assert ch.sources_yaml == ch_dir / "sources.yaml"


def test_load_channel_prompts_dir_property(tmp_path):
    """Channel.prompts_dir points to prompts/ inside the channel dir."""
    ch_dir = tmp_path / "channels" / "test-ch"
    _write_channel_yaml(ch_dir, _minimal_channel_data("test-ch"))
    ch = load_channel(tmp_path / "channels", "test-ch")
    assert ch.prompts_dir == ch_dir / "prompts"


# ---------------------------------------------------------------------------
# test_list_channels
# ---------------------------------------------------------------------------

def test_list_channels_returns_sorted(tmp_path):
    """list_channels returns sorted channel IDs."""
    channels_dir = tmp_path / "channels"
    for cid in ["zebra-ch", "alpha-ch", "beta-ch"]:
        _write_channel_yaml(channels_dir / cid, _minimal_channel_data(cid))

    ids = list_channels(channels_dir)
    assert ids == ["alpha-ch", "beta-ch", "zebra-ch"]


def test_list_channels_excludes_dirs_without_yaml(tmp_path):
    """list_channels only includes dirs that have channel.yaml."""
    channels_dir = tmp_path / "channels"
    # One valid channel
    _write_channel_yaml(channels_dir / "valid-ch", _minimal_channel_data("valid-ch"))
    # One dir without channel.yaml
    (channels_dir / "no-yaml-ch").mkdir(parents=True)

    ids = list_channels(channels_dir)
    assert ids == ["valid-ch"]


def test_list_channels_empty_when_missing_dir(tmp_path):
    """list_channels returns [] when channels/ does not exist."""
    ids = list_channels(tmp_path / "nonexistent")
    assert ids == []


def test_list_channels_real_channels_dir():
    """list_channels returns at least ai-invest and cn-finance from the real channels/."""
    repo = Path(__file__).resolve().parent.parent
    channels_dir = repo / "channels"
    ids = list_channels(channels_dir)
    assert "ai-invest" in ids
    assert "cn-finance" in ids


# ---------------------------------------------------------------------------
# test_channel_templates_fallback
# ---------------------------------------------------------------------------

def test_channel_templates_override_none_when_absent(tmp_path):
    """templates_dir_override returns None when templates/ sub-dir does not exist."""
    ch_dir = tmp_path / "channels" / "test-ch"
    _write_channel_yaml(ch_dir, _minimal_channel_data("test-ch"))
    ch = load_channel(tmp_path / "channels", "test-ch")
    assert ch.templates_dir_override is None


def test_channel_templates_override_returns_path_when_present(tmp_path):
    """templates_dir_override returns the path when templates/ sub-dir exists."""
    ch_dir = tmp_path / "channels" / "test-ch"
    _write_channel_yaml(ch_dir, _minimal_channel_data("test-ch"))
    tmpl_dir = ch_dir / "templates"
    tmpl_dir.mkdir()
    ch = load_channel(tmp_path / "channels", "test-ch")
    assert ch.templates_dir_override == tmpl_dir


# ---------------------------------------------------------------------------
# test load both real channels
# ---------------------------------------------------------------------------

def test_load_ai_invest_channel():
    """load_channel works for the real ai-invest channel."""
    repo = Path(__file__).resolve().parent.parent
    ch = load_channel(repo / "channels", "ai-invest")
    assert ch.id == "ai-invest"
    assert ch.publish.tid == 188
    assert ch.sources_yaml.exists()
    assert ch.prompts_dir.exists()


def test_load_cn_finance_channel():
    """load_channel works for the real cn-finance channel."""
    repo = Path(__file__).resolve().parent.parent
    ch = load_channel(repo / "channels", "cn-finance")
    assert ch.id == "cn-finance"
    assert ch.publish.tid == 95
    assert ch.sources_yaml.exists()
    assert ch.prompts_dir.exists()
