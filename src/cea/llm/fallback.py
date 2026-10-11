"""Primary-then-fallback client (plan 010): Gemini first, the local Ollama model on any LLMError."""
from __future__ import annotations

import logging

from cea.llm.base import LLMClient, LLMError

log = logging.getLogger("cea.llm")


class FallbackClient:
    """``complete()`` tries ``primary``; on ``LLMError`` it tries ``fallback`` once.

    ``last_used`` is ``"primary"``, ``"fallback"`` or ``None`` (nothing answered yet).
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient):
        self.primary = primary
        self.fallback = fallback
        self.last_used: str | None = None

    def __repr__(self) -> str:
        return f"FallbackClient(primary={self.primary!r}, fallback={self.fallback!r})"

    def complete(self, messages: list[dict], *, json_schema: dict | None = None,
                 max_tokens: int = 400, temperature: float = 0.2) -> str:
        kwargs = {"json_schema": json_schema, "max_tokens": max_tokens, "temperature": temperature}
        try:
            text = self.primary.complete(messages, **kwargs)
            self.last_used = "primary"
            return text
        except LLMError as first:
            log.warning("primary LLM failed, trying fallback: %s", first)
            try:
                text = self.fallback.complete(messages, **kwargs)
            except LLMError as second:
                raise LLMError(f"primary failed: {first}; fallback failed: {second}",
                               status=second.status) from None
            self.last_used = "fallback"
            return text
