import json
import re
from anthropic import Anthropic


class LLMJsonError(ValueError):
    pass


_FENCE = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.DOTALL)


def _extract_json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as e:
            raise LLMJsonError(f"fenced block not valid JSON: {e}") from e
    # try to find the largest balanced {...} or [...]
    for opener, closer in [("{", "}"), ("[", "]")]:
        i = text.find(opener)
        j = text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise LLMJsonError(f"could not extract JSON from: {text[:200]!r}")


class LLMClient:
    """Thin wrapper around Anthropic SDK with prompt caching and JSON extraction."""

    def __init__(self, api_key: str, model: str = "deepseek-v4-flash",
                 base_url: str | None = None):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = Anthropic(**kwargs)
        self.model = model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        cached_blocks: list[str] | None = None,
        max_tokens: int = 8000,
        temperature: float = 0.3,
    ):
        cached_blocks = cached_blocks or []
        system_param: list[dict] = []
        for block in cached_blocks:
            system_param.append({
                "type": "text",
                "text": block,
                "cache_control": {"type": "ephemeral"},
            })
        system_param.append({"type": "text", "text": system})

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_param,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return _extract_json(text)
