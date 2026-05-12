import json
import pytest
from unittest.mock import MagicMock, patch
from core.llm import LLMClient, LLMJsonError


def _mock_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def test_llm_returns_parsed_json():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response('{"hello": "world"}')
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        out = c.complete_json(
            system="sys",
            user="user",
            cached_blocks=[],
        )
    assert out == {"hello": "world"}


def test_llm_extracts_json_from_fenced_block():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response(
        'Sure!\n```json\n{"x": 1}\n```\nDone.'
    )
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        out = c.complete_json(system="s", user="u")
    assert out == {"x": 1}


def test_llm_raises_on_unparsable():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response("not json at all")
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        with pytest.raises(LLMJsonError):
            c.complete_json(system="s", user="u")


def test_llm_sends_cached_blocks_as_cache_control():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response('{}')
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        c.complete_json(
            system="sys",
            user="user",
            cached_blocks=["BIG_REFERENCE"],
        )
    call_kwargs = fake.messages.create.call_args.kwargs
    # The system param should be a list with the cached block tagged
    sys_param = call_kwargs["system"]
    assert isinstance(sys_param, list)
    assert any(b.get("cache_control") for b in sys_param if isinstance(b, dict))


def test_llm_extracts_nested_json_from_fenced_block():
    fake = MagicMock()
    fake.messages.create.return_value = _mock_response(
        'Here you go:\n```json\n[{"a": {"b": 1}, "c": [1, 2, 3]}, {"a": {"b": 2}}]\n```'
    )
    with patch("core.llm.Anthropic", return_value=fake):
        c = LLMClient(api_key="x")
        out = c.complete_json(system="s", user="u")
    assert out == [{"a": {"b": 1}, "c": [1, 2, 3]}, {"a": {"b": 2}}]
