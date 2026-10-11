"""OpenAI-compatible chat client over the standard library (plan 010).

One client serves every provider (PRD: "OpenAI-compatible client, switching only
base URL, key and model name"): Gemini's OpenAI endpoint, a local Ollama server
(``http://localhost:11434/v1``) or anything else that implements
``POST {base_url}/chat/completions``.

The API key is sent only in the ``Authorization`` header. It is never logged,
never shown by ``repr()`` and never placed in an ``LLMError`` message: any
text that could echo it (an error body) is redacted first.
"""
from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from cea.llm.base import LLMError

log = logging.getLogger("cea.llm")

SCHEMA_NAME = "cea_response"
BODY_EXCERPT = 200          # characters of an HTTP error body kept in the LLMError message


class OpenAICompatClient:
    """``complete()`` POSTs one chat request and returns ``choices[0].message.content``."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None, *,
                 timeout: float = 30.0, name: str = "primary"):
        scheme = urllib.parse.urlsplit(base_url).scheme
        if scheme not in ("http", "https"):
            raise ValueError(f"base_url must start with http:// or https://, got scheme {scheme!r}")
        if not model:
            raise ValueError("model must not be empty")
        self.base_url = base_url
        self.model = model
        self._api_key = api_key or None
        self.timeout = timeout
        self.name = name

    def __repr__(self) -> str:
        key = "set" if self._api_key else "none"
        return f"OpenAICompatClient(name={self.name!r}, base_url={self.base_url!r}, model={self.model!r}, api_key={key})"

    @property
    def url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "***") if self._api_key else text

    def complete(self, messages: list[dict], *, json_schema: dict | None = None,
                 max_tokens: int = 400, temperature: float = 0.2) -> str:
        body: dict = {"model": self.model, "messages": messages,
                      "max_tokens": max_tokens, "temperature": temperature}
        if json_schema is not None:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": SCHEMA_NAME, "schema": json_schema}}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = self._redact(exc.read(4096).decode("utf-8", "replace"))[:BODY_EXCERPT]
            log.warning("%s: HTTP %s from %s", self.name, exc.code, self.url)
            raise LLMError(f"{self.name}: HTTP {exc.code} from {self.url}: {detail}", status=exc.code) from None
        except (TimeoutError, socket.timeout):
            log.warning("%s: timed out after %ss", self.name, self.timeout)
            raise LLMError(f"{self.name}: timed out after {self.timeout}s calling {self.url}") from None
        except urllib.error.URLError as exc:
            reason = self._redact(str(exc.reason))
            log.warning("%s: cannot reach %s (%s)", self.name, self.url, reason)
            raise LLMError(f"{self.name}: cannot reach {self.url} ({reason})") from None
        except OSError as exc:
            reason = self._redact(str(exc))
            raise LLMError(f"{self.name}: connection error calling {self.url} ({reason})") from None
        log.debug("%s: %s answered in %.2fs", self.name, self.model, time.monotonic() - started)
        try:
            data = json.loads(raw.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError(f"{self.name}: malformed response from {self.url}") from None
        if not isinstance(content, str) or not content.strip():
            raise LLMError(f"{self.name}: empty completion from {self.url}")
        return content
