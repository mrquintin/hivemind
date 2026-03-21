"""
Claude LLM adapter implementing Hivemind Core LLMInterface.
"""

from __future__ import annotations

from typing import Any, Iterator

from app.config import settings
from hivemind_core.interfaces import LLMInterface
from hivemind_core.llm import ClaudeLLM


class ClaudeAdapter(LLMInterface):
    """
    Claude adapter that uses the existing config for API key.

    This is a thin wrapper around the core ClaudeLLM that pulls
    the API key from the app config.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or "claude-opus-4-5-20251101"
        self._llm: ClaudeLLM | None = None

    @property
    def llm(self) -> ClaudeLLM:
        if self._llm is None:
            if not self.api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not configured")
            self._llm = ClaudeLLM(api_key=self.api_key, model=self.model)
        return self._llm

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        return self.llm.call(system_prompt, user_prompt, max_tokens)

    def call_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> Iterator[dict[str, Any]]:
        return self.llm.call_streaming(system_prompt, user_prompt, max_tokens)
