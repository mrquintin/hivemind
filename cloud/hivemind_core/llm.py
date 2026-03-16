"""LLM abstraction for Hivemind core.

Provides a clean interface for LLM calls that can be implemented
by different providers (Claude, OpenAI, local models, etc.).
"""
from __future__ import annotations

import time
from typing import Any

from hivemind_core.types import LLMInterface


class ClaudeLLM(LLMInterface):
    """Claude API implementation of the LLM interface."""

    MODEL_NAME = "claude-opus-4-5-20251101"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        start = time.time()
        kwargs: dict[str, Any] = dict(
            model=self.MODEL_NAME,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        if tools:
            kwargs["tools"] = tools
        message = client.messages.create(**kwargs)
        latency_ms = int((time.time() - start) * 1000)

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in message.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            elif getattr(block, "type", None) == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        usage = message.usage
        return {
            "content": "".join(text_parts),
            "tool_calls": tool_calls,
            "input_tokens": usage.input_tokens if usage else None,
            "output_tokens": usage.output_tokens if usage else None,
            "latency_ms": latency_ms,
            "raw": message.model_dump(),
        }


class MockLLM(LLMInterface):
    """Mock LLM for testing without API calls."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.call_history: list[dict] = []

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.call_history.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": max_tokens,
                "tools": tools,
            }
        )
        response = self.responses.get(user_prompt, f"Mock response to: {user_prompt[:50]}...")
        return {
            "content": response,
            "tool_calls": [],
            "input_tokens": len(system_prompt) // 4 + len(user_prompt) // 4,
            "output_tokens": len(response) // 4,
            "latency_ms": 100,
            "raw": {},
        }
