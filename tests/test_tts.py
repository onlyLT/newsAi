import respx
import httpx
import pytest
from pathlib import Path
from core.tts import MiniMaxTTS


@respx.mock
def test_tts_synthesize_writes_mp3(tmp_path):
    fake_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00fake_audio_bytes"
    respx.post(
        "https://api.minimax.chat/v1/t2a_v2"
    ).mock(return_value=httpx.Response(
        200,
        json={
            "data": {"audio": fake_mp3.hex()},
            "trace_id": "x",
            "base_resp": {"status_code": 0, "status_msg": "success"},
        },
    ))
    tts = MiniMaxTTS(api_key="k", group_id="g", voice_id="v")
    out = tmp_path / "a.mp3"
    duration = tts.synthesize("你好", out)
    assert out.exists()
    assert out.read_bytes() == fake_mp3
    assert duration > 0  # estimated by length when actual not available


@respx.mock
def test_tts_raises_on_non_zero_status(tmp_path):
    respx.post("https://api.minimax.chat/v1/t2a_v2").mock(
        return_value=httpx.Response(200, json={
            "base_resp": {"status_code": 1004, "status_msg": "auth failed"},
        })
    )
    tts = MiniMaxTTS(api_key="k", group_id="g", voice_id="v")
    with pytest.raises(RuntimeError, match="auth failed"):
        tts.synthesize("hi", tmp_path / "a.mp3")
