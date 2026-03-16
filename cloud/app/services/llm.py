import time

import anthropic

from app.config import settings

MODEL_NAME = "claude-opus-4-5-20251101"


def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 1024):
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    start = time.time()
    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency_ms = int((time.time() - start) * 1000)
    content = "".join(block.text for block in message.content)
    usage = message.usage
    return {
        "content": content,
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "latency_ms": latency_ms,
        "raw": message.model_dump(),
    }
