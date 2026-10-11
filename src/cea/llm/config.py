"""Build the configured LLM client from environment variables (plan 010).

Variables (documented in ``.env.example``; a ``.env`` file in the repo root is
read too, and real environment variables win over it):

- ``CEA_LLM_BASE_URL``, ``CEA_LLM_API_KEY``, ``CEA_LLM_MODEL``: the primary
  (Gemini: ``https://generativelanguage.googleapis.com/v1beta/openai/``).
  The primary is configured when BASE_URL and MODEL are both non-empty.
- ``CEA_LLM_FALLBACK_BASE_URL`` (default ``http://localhost:11434/v1``) and
  ``CEA_LLM_FALLBACK_MODEL``: the local Ollama fallback, configured when
  FALLBACK_MODEL is non-empty.
- ``CEA_LLM_TIMEOUT`` (default 30) and ``CEA_LLM_FALLBACK_TIMEOUT``
  (default 120): seconds per request.

Both configured -> ``FallbackClient``; one -> that client; none -> ``LLMError``.
Nothing here logs or returns a key value.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from cea.llm.base import LLMClient, LLMError
from cea.llm.fallback import FallbackClient
from cea.llm.openai_compat import OpenAICompatClient

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_FALLBACK_BASE_URL = "http://localhost:11434/v1"


def read_env_file(path: Path | str) -> dict[str, str]:
    """``KEY=VALUE`` lines of a .env file. Blank lines, ``#`` comments and malformed lines are skipped."""
    values: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name.strip()] = value
    return values


def _seconds(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise LLMError(f"{name} must be a number of seconds") from None


def client_from_env(environ: Mapping[str, str] | None = None, *,
                    env_file: Path | str | None = DEFAULT_ENV_FILE) -> LLMClient:
    """The configured client. ``environ`` defaults to ``os.environ``; ``env_file=None`` skips the .env file."""
    env: dict[str, str] = dict(read_env_file(env_file)) if env_file is not None else {}
    env.update(os.environ if environ is None else environ)
    primary = fallback = None
    base, model = env.get("CEA_LLM_BASE_URL", "").strip(), env.get("CEA_LLM_MODEL", "").strip()
    if base and model:
        primary = OpenAICompatClient(base, model, env.get("CEA_LLM_API_KEY", "").strip() or None,
                                     timeout=_seconds(env, "CEA_LLM_TIMEOUT", 30.0), name="primary")
    fb_model = env.get("CEA_LLM_FALLBACK_MODEL", "").strip()
    if fb_model:
        fb_base = env.get("CEA_LLM_FALLBACK_BASE_URL", "").strip() or DEFAULT_FALLBACK_BASE_URL
        fallback = OpenAICompatClient(fb_base, fb_model, None,
                                      timeout=_seconds(env, "CEA_LLM_FALLBACK_TIMEOUT", 120.0), name="fallback")
    if primary and fallback:
        return FallbackClient(primary, fallback)
    if primary or fallback:
        return primary or fallback
    raise LLMError("no LLM configured: set CEA_LLM_BASE_URL and CEA_LLM_MODEL, "
                   "or CEA_LLM_FALLBACK_MODEL (see .env.example)")
