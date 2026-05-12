import httpx
from pathlib import Path


class MiniMaxTTS:
    """Synchronous wrapper around MiniMax T2A v2 API."""

    BASE_URL = "https://api.minimax.chat/v1/t2a_v2"

    def __init__(self, api_key: str, group_id: str, voice_id: str,
                 model: str = "speech-02-hd"):
        self.api_key = api_key
        self.group_id = group_id
        self.voice_id = voice_id
        self.model = model

    def synthesize(self, text: str, out_path: Path,
                   speed: float = 1.0, vol: float = 1.0) -> float:
        """Synthesize `text` to `out_path` (mp3). Returns estimated duration in seconds."""
        payload = {
            "model": self.model,
            "text": text,
            "voice_setting": {
                "voice_id": self.voice_id,
                "speed": speed,
                "vol": vol,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = httpx.post(
            f"{self.BASE_URL}?GroupId={self.group_id}",
            json=payload, headers=headers, timeout=60.0,
        )
        resp.raise_for_status()
        body = resp.json()
        status = body.get("base_resp", {}).get("status_code", -1)
        if status != 0:
            raise RuntimeError(
                f"MiniMax TTS error {status}: {body.get('base_resp', {}).get('status_msg')}"
            )
        audio_hex = body["data"]["audio"]
        audio_bytes = bytes.fromhex(audio_hex)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio_bytes)
        # rough estimate: 4 Chinese chars/sec ≈ 0.25s per char (audio_length gives exact, in ms)
        sub = body.get("extra_info", {}).get("audio_length")
        if sub:
            return float(sub) / 1000.0
        return max(1.0, len(text) * 0.25)
