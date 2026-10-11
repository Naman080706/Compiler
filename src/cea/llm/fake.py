"""A deterministic, scripted LLM for tests (plan 010). No test may use the network.

``FakeLLM(["reply 1", LLMError("down"), lambda messages, schema: "..."], default=...)``
answers each call with the next scripted item: a string is returned, an
exception is raised, a callable is called with ``(messages, json_schema)``.
When the script is used up it answers with ``default`` (same three kinds); with
no default it raises ``LLMError``. Every call is recorded in ``calls``.
"""
from __future__ import annotations

import copy
from collections import deque
from collections.abc import Iterable

from cea.llm.base import LLMError


class FakeLLM:
    def __init__(self, script: Iterable = (), *, default=None):
        self._script: deque = deque(script)
        self.default = default
        self.calls: list[dict] = []
        self.name = "fake"

    def complete(self, messages: list[dict], *, json_schema: dict | None = None,
                 max_tokens: int = 400, temperature: float = 0.2) -> str:
        self.calls.append({"messages": copy.deepcopy(messages), "json_schema": json_schema,
                           "max_tokens": max_tokens, "temperature": temperature})
        item = self._script.popleft() if self._script else self.default
        if item is None:
            raise LLMError("FakeLLM: no scripted reply left")
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return item(messages, json_schema)
        return item
