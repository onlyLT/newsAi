import time
import httpx
from pathlib import Path


class MiniMaxTTS:
    """Synchronous wrapper around MiniMax T2A v2 API (CN region: api.minimaxi.com)."""

    BASE_URL = "https://api.minimaxi.com/v1/t2a_v2"

    def __init__(self, api_key: str, group_id: str = "", voice_id: str = "Podcast_girl",
                 model: str = "speech-2.8-hd", throttle_s: float = 3.5):
        self.api_key = api_key
        self.group_id = group_id  # not used by t2a_v2 endpoint; kept for future MiniMax APIs
        self.voice_id = voice_id
        self.model = model
        self.throttle_s = throttle_s

    def synthesize(self, text: str, out_path: Path,
                   speed: float = 1.0, vol: float = 1.0, pitch: float = 0.0) -> float:
        """Synthesize `text` to `out_path` (mp3). Returns duration in seconds.

        Throttles before the HTTP call to stay under MiniMax's RPM limit.
        """
        if self.throttle_s > 0:
            time.sleep(self.throttle_s)
        payload = {
            "model": self.model,
            "text": text,
            "voice_setting": {
                "voice_id": self.voice_id,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = httpx.post(self.BASE_URL, json=payload, headers=headers, timeout=60.0)
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
        sub = body.get("extra_info", {}).get("audio_length")
        if sub:
            return float(sub) / 1000.0
        return max(1.0, len(text) * 0.25)
