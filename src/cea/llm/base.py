"""The LLM client interface and its one error type (plan 010, plans/m2-architecture.md section 2).

Every client takes OpenAI-style chat ``messages`` and returns the reply text.
Every failure (network, HTTP status, timeout, malformed reply, nothing
configured) is raised as ``LLMError``. Messages of an ``LLMError`` never
contain an API key.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Any failure to get a completion. ``status`` is the HTTP status when there was one."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, messages: list[dict], *, json_schema: dict | None = None,
                 max_tokens: int = 400, temperature: float = 0.2) -> str:
        """Return the assistant's reply text. With ``json_schema``, ask for JSON matching it."""
        ...
