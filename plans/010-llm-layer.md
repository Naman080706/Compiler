# Plan 010: Build the LLM layer `src/cea/llm/` (OpenAI-compatible client, fallback, fake, cache, config)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md` (the "Milestone 2" table, row 010), unless a reviewer
> dispatched you and told you they maintain the index. End your final report
> with a **Viva notes** list: the decisions, trade-offs or deviations an
> examiner might ask about (see `plans/README.md`, "Viva notes convention").
> Do not edit `VIVA.md`; the advisor folds your notes into it.
>
> Every code block marked "exact content" is the whole file to write; copy it
> verbatim. Blocks marked "replace … with" are exact edits. Do not reformat or
> "improve" them. The advisor ran exactly this code on a copy of the repo
> (`40d4ef9` plus plans 008 and 009) and got every number quoted below. If a
> verification fails and your file is identical to the plan, STOP and report.
>
> **No network, no secrets.** No test may reach the internet. Never put a real
> API key anywhere (files, commands, commit messages, your report). You do NOT
> need any key or any LLM to execute this plan. Do not run `ollama pull`.
>
> **Never open, read, list or run anything under `tests/corpus/heldout/`.**
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat 40d4ef9..HEAD -- .gitignore requirements-dev.txt pyproject.toml tests/unit/test_no_print.py` must print **nothing**.
> 2. `ls src/cea/llm requirements.txt .env.example tools/llm_smoke.py tests/unit/test_llm_client.py tests/unit/test_llm_support.py 2>&1 | grep -c "No such file"` must print `6`.
> 3. `.venv/Scripts/python -m pytest -q` must end with `883 passed, 20 deselected` (plans 008 and 009 merged). This plan does not need 008/009; if they are not merged yet, write down the number you get as **B** and read every count below as "B + (count − 883)". Any other failure: STOP.
>
> If check 1 or 2 fails, STOP and report which one.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (new package; the only edit to existing code is the no-print test, which gets stricter)
- **Depends on**: none
- **Category**: direction (milestone 2, PRD F3 infrastructure)
- **Planned at**: commit `40d4ef9`, 2026-10-11

## Why this matters

The project is a course compiler for a strict C99 subset (Python, `src/cea/`) with an AI error-assistant layer. Milestone 2 adds PRD F3, a compiler-scoped AI agent (plan 011), which needs one way to call an LLM. The owner chose Gemini's free tier as the primary model and a local Ollama model as the fallback, both through ONE OpenAI-compatible client, so that switching provider is a configuration change. This plan builds that layer with the standard library only: the client (`urllib`, a timeout, every failure mapped to `LLMError`), a primary→fallback wrapper, a scripted `FakeLLM` that every test uses (tests never touch the network), an on-disk explanation cache (PRD: "cache explanations by error signature to save quota") and `client_from_env()`. It also adds the repo plumbing the contract asks for: `requirements.txt`, `.env.example`, `.cea_cache/` in `.gitignore`, and an optional live smoke script that pytest never collects. The API key is never logged or put in an exception message; tests prove it with a dummy key.

## Current state

- `plans/m2-architecture.md` §2 (binding contract), quoted:
  ```python
  # llm/ (plan 010)
  class LLMClient(Protocol):
      def complete(self, messages: list[dict], *, json_schema: dict | None = None,
                   max_tokens: int = 400, temperature: float = 0.2) -> str: ...
  class OpenAICompatClient:   # stdlib urllib POST {base_url}/chat/completions; timeout; raises LLMError
  class FallbackClient:       # tries primary, then fallback, on LLMError
  class FakeLLM:              # deterministic, scripted responses; used by ALL tests (no network in tests)
  class ExplanationCache:     # JSON file under .cea_cache/ (git-ignored); key = sha256 of the error signature + mode
  def client_from_env() -> LLMClient: ...
  ```
  "Environment variables, documented in `.env.example`, which is committed (`.env` itself is git-ignored): `CEA_LLM_BASE_URL`, `CEA_LLM_API_KEY`, `CEA_LLM_MODEL` for the primary. The Gemini OpenAI-compatible endpoint is `https://generativelanguage.googleapis.com/v1beta/openai/`. `CEA_LLM_FALLBACK_BASE_URL` (default `http://localhost:11434/v1`), `CEA_LLM_FALLBACK_MODEL` for Ollama. **Never commit or log a key value.** Key-handling tests use dummy strings only."
  "Runtime dependencies go in a NEW `requirements.txt` (plan 010 creates it …). `requirements-dev.txt` gains `-r requirements.txt` plus test-only packages."
  §5: "No network in tests … One optional live smoke script (`tools/llm_smoke.py`) runs only when a key is present. It is never part of `pytest`." "`print` only in `cli.py`. The no-print test from plan 005 still applies to every new module."
- PRD notes (from `cd project prd.docx`): "LLM access: OpenAI-compatible client, switching only base URL, key and model name." "Notes: cache explanations by error signature to save quota, and never send the student ID or personal data to the LLM, only the error context. Free-tier limits change, so check the provider's current page before the demo." Risk table: "API cost or rate limits during demos — Cache explanations by error signature; keep a small local fallback."
- `.gitignore` lines 15–18 today (`.env` is already ignored; `.cea_cache/` is not):
  ```
  # Local data and secrets
  .env
  *.sqlite3
  chroma_db/
  ```
- `requirements-dev.txt` today is one line: `pytest>=8,<9`. There is no `requirements.txt`.
- `pyproject.toml`: `testpaths = ["tests"]`, `pythonpath = ["src"]`. Pytest collects only `tests/`, so a script in `tools/` is never collected.
- `tests/unit/test_no_print.py` (plan 005) checks only `src/cea/*.py` (top level), lines 21–29:
  ```python
  def test_no_module_except_cli_prints():
      offenders = []
      for path in sorted(PKG.glob("*.py")):
          if path.name in ALLOWED:
              continue
          for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
              if FORBIDDEN.search(line):
                  offenders.append(f"{path.name}:{n}: {line.strip()}")
      assert not offenders, "console output outside cli.py:\n" + "\n".join(offenders)
  ```
  A new subpackage `src/cea/llm/` would escape it, so Step 2 makes it recursive.
- Repo conventions (`plans/m1-architecture.md` §6): module docstring on every file, type hints, `@dataclass` for data, stdlib only, unit tests in `tests/unit/test_<module>.py` with plain `assert` and `pytest.mark.parametrize` (model: `tests/unit/test_pipeline_cli.py`). `catalog.py` finds the repo root as `Path(__file__).resolve().parents[2]`; inside `src/cea/llm/` the same root is `parents[3]`.
- Logging: the package logs through `logging.getLogger("cea.llm")` (not `print`). Logging is allowed by the no-print rule; the CLI does not configure handlers, so nothing appears unless a caller enables logging.

## Advisor's verification (what you should reproduce)

On a scratch copy at `40d4ef9` + plans 008 and 009 (Python 3.13.1, gcc on PATH):
- Full suite after each step: 883 → 883 → 903 → 926 passed, 20 deselected.
- `tests/unit/test_llm_client.py`: 20 passed (about 2–3 s; one test waits for a 0.3 s timeout, one for a refused connection). `tests/unit/test_llm_support.py`: 23 passed.
- `python tools/llm_smoke.py --no-env-file` with no `CEA_LLM_*` variables prints `SKIPPED: no LLM configured: …` and exits 0.
- Optional live check (NOT required, not part of any test): with Ollama running and `llama3.1` already pulled, `CEA_LLM_FALLBACK_MODEL=llama3.1 python tools/llm_smoke.py --no-env-file` printed `OK: provider=fallback model=llama3.1 seconds=13.48` and `parsed: {'answer': ';'}`, so Ollama's `/v1/chat/completions` accepts the `response_format: json_schema` request this client sends. Gemini was not tried (no key).

Without `gcc` on PATH, one gcc test is skipped: read every "N passed" as "N-1 passed, 1 skipped".

## Commands you will need

| Purpose | Command (project root, Git Bash) | Expected on success |
|---|---|---|
| venv (once, if missing) | `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt` | exit 0 |
| Tests | `.venv/Scripts/python -m pytest -q` | see each step |
| One file | `.venv/Scripts/python -m pytest -q tests/unit/test_llm_client.py` | see each step |
| Smoke (skip path) | `env -u CEA_LLM_BASE_URL -u CEA_LLM_MODEL -u CEA_LLM_FALLBACK_MODEL .venv/Scripts/python tools/llm_smoke.py --no-env-file` | `SKIPPED: no LLM configured: ...`, exit 0 |
| Ignore check | `git check-ignore .env .cea_cache/explanations.json` | both paths printed |

## Scope

**In scope** (the only files you may create or modify):
- `src/cea/llm/__init__.py`, `src/cea/llm/base.py`, `src/cea/llm/openai_compat.py`, `src/cea/llm/fallback.py`, `src/cea/llm/fake.py`, `src/cea/llm/cache.py`, `src/cea/llm/config.py` (all create)
- `tests/unit/test_llm_client.py`, `tests/unit/test_llm_support.py` (create), `tests/unit/test_no_print.py` (one function)
- `tools/llm_smoke.py` (create)
- `requirements.txt` (create), `requirements-dev.txt`, `.env.example` (create), `.gitignore` (one line)
- `plans/README.md` (status row 010 only)

**Out of scope** (do NOT touch):
- Every other file under `src/cea/` (the compiler core stays standard-library only and does not import `cea.llm`; plan 011 wires the agent and the CLI).
- `.env` itself: do not create it. `.cea_cache/`: do not create or commit it.
- `pyproject.toml` (no new pytest options; `tools/` is already outside `testpaths`).
- Any third-party HTTP or LLM package (`requests`, `openai`, `httpx`, `google-genai`, …): the contract requires stdlib `urllib`.
- `docs/**`, `tests/corpus/**`, `VIVA.md`, `plans/m2-architecture.md`.

## Git workflow

- Branch: `advisor/010-llm-layer` from `main`.
- One commit per step. Stage by explicit path (never `git add -A` / `git add .`). Message style as in `git log` (e.g. `cea: F2 clustering module wired into the pipeline (plan 009 step 1)`). Every commit message ends with a blank line and then:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
- Do NOT push (there is no remote). Do NOT merge; the owner reviews first.

## Steps

### Step 1: Repo plumbing: `requirements.txt`, `requirements-dev.txt`, `.env.example`, `.gitignore`

1a. Create `requirements.txt`, exact content:

````text
# Runtime dependencies of the cea package (plans/m2-architecture.md section 2).
# The compiler core and the LLM layer (src/cea/llm/, plan 010) use the Python
# standard library only, so this file lists no packages yet. Plan 012 adds FastAPI.
````

1b. Replace `requirements-dev.txt` with this exact content:

````text
-r requirements.txt
pytest>=8,<9
````

1c. Create `.env.example`, exact content (no value after `CEA_LLM_API_KEY=`; never put a key here):

````text
# Copy this file to .env (git-ignored) and fill in the values. Never commit a real key.
# Real environment variables win over .env. Check `python tools/llm_smoke.py`.

# Primary LLM: Google Gemini free tier, through its OpenAI-compatible endpoint.
# It is used only when CEA_LLM_BASE_URL and CEA_LLM_MODEL are both set.
# Pick a current free-tier model name from Google's model page (free-tier limits change).
CEA_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
CEA_LLM_API_KEY=
CEA_LLM_MODEL=
# CEA_LLM_TIMEOUT=30

# Fallback LLM: a local Ollama server (https://ollama.com), used when the primary fails
# or is not configured. Pull a model first, e.g. `ollama pull llama3.1`.
CEA_LLM_FALLBACK_BASE_URL=http://localhost:11434/v1
CEA_LLM_FALLBACK_MODEL=
# CEA_LLM_FALLBACK_TIMEOUT=120
````

1d. `.gitignore`: replace the two lines
```
# Local data and secrets
.env
```
with
```
# Local data and secrets
.env
.cea_cache/
```

**Verify**:
- `.venv/Scripts/python -m pip install -r requirements-dev.txt` → exit 0 (a requirements file with only comments is valid).
- `git check-ignore .env .cea_cache/explanations.json` → prints both paths.
- `git check-ignore .env.example; echo "exit=$?"` → `exit=1` (the example IS committed).
- `.venv/Scripts/python -m pytest -q` → `883 passed, 20 deselected`

Commit: `build: requirements.txt, .env.example, ignore .cea_cache (plan 010 step 1)`, staging `requirements.txt requirements-dev.txt .env.example .gitignore`.

### Step 2: The `cea.llm` package, the HTTP tests, and a recursive no-print check

2a. Create `src/cea/llm/base.py`, exact content:

````python
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
````

2b. Create `src/cea/llm/openai_compat.py`, exact content:

````python
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
````

Notes (do not change the code because of them): the JSON schema is sent as `response_format = {"type": "json_schema", "json_schema": {"name": "cea_response", "schema": …}}`, the OpenAI structured-output shape that both Gemini's and Ollama's OpenAI endpoints accept. `raise … from None` drops the original exception chain so no `Request` object (which holds the `Authorization` header) is attached to the error. Only `http`/`https` URLs are accepted, so `urllib` can never open a `file://` URL.

2c. Create `src/cea/llm/fallback.py`, exact content:

````python
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
````

2d. Create `src/cea/llm/fake.py`, exact content:

````python
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
````

2e. Create `src/cea/llm/cache.py`, exact content:

````python
"""On-disk explanation cache (plan 010; PRD: "cache explanations by error signature to save quota").

One JSON file, by default ``<repo root>/.cea_cache/explanations.json``
(git-ignored). The key is the sha256 of the error signature plus the mode, so
the file holds no source text in its keys. Values are small JSON objects chosen
by the caller (plan 011's agent). A missing or corrupt file counts as empty;
the cache never raises on read.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_PATH = REPO_ROOT / ".cea_cache" / "explanations.json"


class ExplanationCache:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else DEFAULT_CACHE_PATH
        self._data: dict[str, dict] | None = None

    @staticmethod
    def key(signature: object, mode: str) -> str:
        """sha256 hex of the canonical JSON of (signature, mode)."""
        text = json.dumps({"signature": signature, "mode": mode}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load(self) -> dict[str, dict]:
        if self._data is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._data = {}
        return self._data

    def get(self, signature: object, mode: str) -> dict | None:
        value = self._load().get(self.key(signature, mode))
        return dict(value) if isinstance(value, dict) else None

    def put(self, signature: object, mode: str, value: dict) -> None:
        data = self._load()
        data[self.key(signature, mode)] = dict(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def __len__(self) -> int:
        return len(self._load())
````

2f. Create `src/cea/llm/config.py`, exact content:

````python
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
````

2g. Create `src/cea/llm/__init__.py`, exact content:

````python
"""LLM layer for the F3 agent (plan 010, plans/m2-architecture.md section 2).

One OpenAI-compatible client serves every provider; switching provider is a
configuration change (environment variables, see ``.env.example``). Tests use
``FakeLLM`` only and never touch the network. Nothing in this package prints.
"""
from cea.llm.base import LLMClient, LLMError
from cea.llm.cache import ExplanationCache
from cea.llm.config import client_from_env
from cea.llm.fake import FakeLLM
from cea.llm.fallback import FallbackClient
from cea.llm.openai_compat import OpenAICompatClient

__all__ = ["LLMClient", "LLMError", "OpenAICompatClient", "FallbackClient", "FakeLLM",
           "ExplanationCache", "client_from_env"]
````

2h. `tests/unit/test_no_print.py`: replace the function `test_no_module_except_cli_prints` (lines 21–29, quoted in "Current state") with this exact text:

```python
def test_no_module_except_cli_prints():
    offenders = []
    for path in sorted(PKG.rglob("*.py")):                  # subpackages too (cea/llm/, plan 010)
        rel = path.relative_to(PKG).as_posix()
        if rel in ALLOWED:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, "console output outside cli.py:\n" + "\n".join(offenders)
```

(`ALLOWED = {"cli.py"}` stays; it now matches the relative path, so only the top-level `src/cea/cli.py` may print.)

2i. Create `tests/unit/test_llm_client.py`, exact content:

````python
"""OpenAICompatClient and FallbackClient against a local fake HTTP server (plan 010).

The server is stdlib ``http.server`` on 127.0.0.1 in a background thread; it
records every request and answers from a per-test script. No test reaches the
real network. The key used here is a dummy string.
"""
import json
import logging
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cea.llm import FallbackClient, FakeLLM, LLMError, OpenAICompatClient

DUMMY_KEY = "dummy-key-0123456789-DO-NOT-USE"


def ok_body(content):
    return {"id": "x", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}]}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                     "body": json.loads(raw.decode("utf-8"))})
        status, payload, delay = self.server.script.pop(0) if self.server.script else (200, ok_body("default"), 0)
        if payload == "ECHO_AUTH":                      # a provider that echoes the auth header in its error
            payload = {"error": {"message": f"bad credentials: {self.headers.get('Authorization')}"}}
        if delay:
            time.sleep(delay)
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass                                         # the client already gave up (timeout test)

    def log_message(self, *args):
        pass                                             # keep pytest output clean


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        pass


@pytest.fixture
def server():
    srv = _Server(("127.0.0.1", 0), _Handler)
    srv.requests, srv.script = [], []
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    srv.base_url = f"http://127.0.0.1:{srv.server_address[1]}/v1/"
    yield srv
    srv.shutdown()
    srv.server_close()


def client(srv, **kw):
    kw.setdefault("timeout", 5.0)
    return OpenAICompatClient(srv.base_url, "test-model", DUMMY_KEY, **kw)


MSGS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "héllo"}]


# ---------------------------------------------------------------- request and response
def test_request_shape_and_reply(server):
    server.script.append((200, ok_body("Hi there ✓"), 0))
    assert client(server).complete(MSGS, max_tokens=123, temperature=0.0) == "Hi there ✓"
    (req,) = server.requests
    assert req["path"] == "/v1/chat/completions"                       # trailing slash of base_url handled
    assert req["headers"]["authorization"] == f"Bearer {DUMMY_KEY}"
    assert req["headers"]["content-type"] == "application/json"
    assert req["body"] == {"model": "test-model", "messages": MSGS, "max_tokens": 123, "temperature": 0.0}


def test_json_schema_becomes_response_format(server):
    schema = {"type": "object", "properties": {"explanation": {"type": "string"}}, "required": ["explanation"]}
    server.script.append((200, ok_body('{"explanation": "x"}'), 0))
    assert client(server).complete(MSGS, json_schema=schema) == '{"explanation": "x"}'
    body = server.requests[0]["body"]
    assert body["response_format"] == {"type": "json_schema",
                                       "json_schema": {"name": "cea_response", "schema": schema}}
    assert (body["max_tokens"], body["temperature"]) == (400, 0.2)       # contract defaults


def test_no_key_sends_no_authorization_header(server):
    server.script.append((200, ok_body("ok"), 0))
    OpenAICompatClient(server.base_url, "m", None, timeout=5).complete(MSGS)
    assert "authorization" not in server.requests[0]["headers"]


# ---------------------------------------------------------------- error mapping
@pytest.mark.parametrize("status,payload,fragment", [
    (401, {"error": {"message": "API key not valid"}}, "HTTP 401"),
    (429, {"error": {"message": "quota exceeded"}}, "HTTP 429"),
    (500, b"<html>oops</html>", "HTTP 500"),
    (200, b"not json at all", "malformed response"),
    (200, {"choices": []}, "malformed response"),
    (200, {"choices": [{"message": {"content": None}}]}, "empty completion"),
    (200, ok_body("   "), "empty completion"),
])
def test_errors_map_to_llmerror(server, status, payload, fragment):
    server.script.append((status, payload, 0))
    with pytest.raises(LLMError) as info:
        client(server).complete(MSGS)
    assert fragment in str(info.value)
    assert info.value.status == (status if status != 200 else None)


def test_timeout_maps_to_llmerror(server):
    server.script.append((200, ok_body("late"), 1.5))
    with pytest.raises(LLMError, match="timed out"):
        client(server, timeout=0.3).complete(MSGS)


def test_unreachable_server_maps_to_llmerror():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]                       # closed again: nothing listens there
    c = OpenAICompatClient(f"http://127.0.0.1:{port}/v1", "m", DUMMY_KEY, timeout=1.0)
    with pytest.raises(LLMError) as info:
        c.complete(MSGS)
    assert DUMMY_KEY not in str(info.value)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/v1", "localhost:11434/v1"])
def test_only_http_urls_are_accepted(url):
    with pytest.raises(ValueError):
        OpenAICompatClient(url, "m")


# ---------------------------------------------------------------- the key never leaks
def test_key_not_in_error_message_logs_or_repr(server, caplog):
    caplog.set_level(logging.DEBUG, logger="cea.llm")
    server.script.append((401, "ECHO_AUTH", 0))
    c = client(server)
    with pytest.raises(LLMError) as info:
        c.complete(MSGS)
    assert "bad credentials: Bearer ***" in str(info.value)             # the echoed key was redacted
    assert DUMMY_KEY not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert DUMMY_KEY not in caplog.text
    assert DUMMY_KEY not in repr(c) and "api_key=set" in repr(c)


def test_key_not_in_fallback_error(server, caplog):
    caplog.set_level(logging.DEBUG, logger="cea.llm")
    server.script += [(401, "ECHO_AUTH", 0), (503, "ECHO_AUTH", 0)]
    fb = FallbackClient(client(server, name="primary"), client(server, name="fallback"))
    with pytest.raises(LLMError) as info:
        fb.complete(MSGS)
    text = str(info.value)
    assert "primary failed" in text and "fallback failed" in text and info.value.status == 503
    assert DUMMY_KEY not in text and DUMMY_KEY not in caplog.text and DUMMY_KEY not in repr(fb)


# ---------------------------------------------------------------- fallback
def test_fallback_used_when_primary_fails(server):
    server.script += [(429, {"error": {"message": "quota"}}, 0), (200, ok_body("from fallback"), 0)]
    fb = FallbackClient(client(server, name="primary"), client(server, name="fallback"))
    assert fb.complete(MSGS, json_schema={"type": "object"}, max_tokens=50) == "from fallback"
    assert fb.last_used == "fallback"
    assert len(server.requests) == 2
    assert server.requests[0]["body"] == server.requests[1]["body"]     # same request sent to both


def test_primary_success_skips_fallback():
    primary, fallback = FakeLLM(["primary says hi"]), FakeLLM(["never"])
    fb = FallbackClient(primary, fallback)
    assert fb.complete(MSGS) == "primary says hi"
    assert fb.last_used == "primary" and len(fallback.calls) == 0


def test_fallback_passes_arguments_through():
    primary, fallback = FakeLLM([LLMError("down")]), FakeLLM(["ok"])
    FallbackClient(primary, fallback).complete(MSGS, json_schema={"type": "object"}, max_tokens=7, temperature=0.5)
    assert fallback.calls[0]["json_schema"] == {"type": "object"}
    assert (fallback.calls[0]["max_tokens"], fallback.calls[0]["temperature"]) == (7, 0.5)
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_llm_client.py` → `20 passed`
- `.venv/Scripts/python -m pytest -q tests/unit/test_no_print.py` → `3 passed`
- Mutation check of the recursive no-print test: append the line `print("x")` to the end of `src/cea/llm/fake.py`, run `.venv/Scripts/python -m pytest -q tests/unit/test_no_print.py` → `1 failed, 2 passed` (the failure names `llm/fake.py`); then delete that line again (the file must match 2d exactly) and re-run → `3 passed`.
- `.venv/Scripts/python -m pytest -q` → `903 passed, 20 deselected`
- `grep -rn "import requests\|import openai\|import httpx" src/` → no output

Commit: `cea: LLM layer - OpenAI-compatible client, fallback, fake, cache, config (plan 010 step 2)`, staging `src/cea/llm/__init__.py src/cea/llm/base.py src/cea/llm/openai_compat.py src/cea/llm/fallback.py src/cea/llm/fake.py src/cea/llm/cache.py src/cea/llm/config.py tests/unit/test_llm_client.py tests/unit/test_no_print.py`.

### Step 3: Optional live smoke script and the support tests

3a. Create `tools/llm_smoke.py`, exact content:

````python
"""Optional live smoke test of the configured LLM (plan 010). NOT part of pytest.

Sends one tiny JSON-schema request through ``cea.llm.client_from_env()`` and
prints which provider answered, the latency and the parsed reply. It never
prints the API key. With nothing configured it prints ``SKIPPED: ...`` and
exits 0 without any network access.

Usage (from the project root):
    python tools/llm_smoke.py                 # reads .env, then the environment
    python tools/llm_smoke.py --no-env-file   # environment variables only

Exit status: 0 success or skipped, 1 the LLM call failed.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cea.llm import FallbackClient, LLMError, client_from_env  # noqa: E402
from cea.llm.config import DEFAULT_ENV_FILE  # noqa: E402

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
MESSAGES = [
    {"role": "system", "content": "Reply with a single JSON object only."},
    {"role": "user", "content": 'In C, which character ends a statement? Reply as {"answer": "<character>"}.'},
]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python tools/llm_smoke.py", description=__doc__.splitlines()[0])
    ap.add_argument("--no-env-file", action="store_true", help="ignore the .env file")
    args = ap.parse_args(argv)
    try:
        client = client_from_env(env_file=None if args.no_env_file else DEFAULT_ENV_FILE)
    except LLMError as exc:
        print(f"SKIPPED: {exc}")
        return 0
    started = time.monotonic()
    try:
        text = client.complete(MESSAGES, json_schema=SCHEMA, max_tokens=100, temperature=0.0)
    except LLMError as exc:
        print(f"FAILED: {exc}")
        return 1
    elapsed = time.monotonic() - started
    used = client
    if isinstance(client, FallbackClient):
        used = client.primary if client.last_used == "primary" else client.fallback
    print(f"OK: provider={used.name} model={used.model} seconds={elapsed:.2f}")
    print(f"raw reply: {text!r}")
    try:
        print(f"parsed: {json.loads(text)}")
    except ValueError:
        print("parsed: (reply is not valid JSON)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
````

3b. Create `tests/unit/test_llm_support.py`, exact content:

````python
"""FakeLLM, ExplanationCache, client_from_env and tools/llm_smoke.py (plan 010). No network."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cea.llm import (ExplanationCache, FakeLLM, FallbackClient, LLMClient, LLMError, OpenAICompatClient,
                     client_from_env)
from cea.llm.config import read_env_file

ROOT = Path(__file__).resolve().parents[2]
DUMMY_KEY = "dummy-key-0123456789-DO-NOT-USE"
MSGS = [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------- FakeLLM
def test_fake_llm_script_then_default_and_records_calls():
    fake = FakeLLM(["one", LLMError("boom"), lambda m, s: f"n={len(m)} schema={s is not None}"], default="dflt")
    assert fake.complete(MSGS) == "one"
    with pytest.raises(LLMError, match="boom"):
        fake.complete(MSGS)
    assert fake.complete(MSGS, json_schema={"type": "object"}) == "n=1 schema=True"
    assert fake.complete(MSGS) == "dflt"
    assert len(fake.calls) == 4 and fake.calls[2]["json_schema"] == {"type": "object"}
    assert fake.calls[0] == {"messages": MSGS, "json_schema": None, "max_tokens": 400, "temperature": 0.2}


def test_fake_llm_without_default_raises_when_empty():
    with pytest.raises(LLMError):
        FakeLLM().complete(MSGS)


def test_fake_llm_copies_messages():
    fake, msgs = FakeLLM(default="x"), [{"role": "user", "content": "a"}]
    fake.complete(msgs)
    msgs[0]["content"] = "changed"
    assert fake.calls[0]["messages"][0]["content"] == "a"


@pytest.mark.parametrize("obj", [FakeLLM(), OpenAICompatClient("http://localhost:1/v1", "m"),
                                 FallbackClient(FakeLLM(), FakeLLM())])
def test_every_client_satisfies_the_protocol(obj):
    assert isinstance(obj, LLMClient)


# ---------------------------------------------------------------- ExplanationCache
SIG = {"code": "SYN-MISSING-SEMICOLON", "line": 5, "snippet": "x = 1\ny = 2"}


def test_cache_roundtrip_and_persistence(tmp_path):
    path = tmp_path / "c" / "explanations.json"
    cache = ExplanationCache(path)
    assert cache.get(SIG, "short") is None and len(cache) == 0
    cache.put(SIG, "short", {"text": "Missing ';'."})
    assert cache.get(SIG, "short") == {"text": "Missing ';'."}
    assert cache.get(SIG, "expand") is None                             # mode is part of the key
    again = ExplanationCache(path)                                      # a new process reads the file
    assert again.get(SIG, "short") == {"text": "Missing ';'."} and len(again) == 1


def test_cache_key_is_sha256_and_order_independent():
    k = ExplanationCache.key(SIG, "short")
    assert len(k) == 64 and int(k, 16) >= 0
    assert k == ExplanationCache.key(dict(reversed(list(SIG.items()))), "short")
    assert k != ExplanationCache.key(SIG, "expand")


def test_cache_file_has_no_plain_source_in_keys(tmp_path):
    cache = ExplanationCache(tmp_path / "e.json")
    cache.put(SIG, "short", {"text": "t"})
    data = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    assert list(data) == [ExplanationCache.key(SIG, "short")]


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", ""])
def test_corrupt_cache_file_counts_as_empty(tmp_path, content):
    path = tmp_path / "e.json"
    path.write_text(content, encoding="utf-8")
    cache = ExplanationCache(path)
    assert cache.get(SIG, "short") is None
    cache.put(SIG, "short", {"text": "t"})
    assert ExplanationCache(path).get(SIG, "short") == {"text": "t"}


def test_default_cache_path_is_git_ignored_folder():
    assert ExplanationCache().path == ROOT / ".cea_cache" / "explanations.json"


# ---------------------------------------------------------------- client_from_env
def test_nothing_configured_raises():
    with pytest.raises(LLMError, match="no LLM configured"):
        client_from_env({}, env_file=None)


def test_primary_only():
    c = client_from_env({"CEA_LLM_BASE_URL": "https://example.invalid/v1beta/openai/",
                         "CEA_LLM_API_KEY": DUMMY_KEY, "CEA_LLM_MODEL": "gemini-x"}, env_file=None)
    assert isinstance(c, OpenAICompatClient)
    assert (c.name, c.model, c.timeout) == ("primary", "gemini-x", 30.0)
    assert c.url == "https://example.invalid/v1beta/openai/chat/completions"
    assert DUMMY_KEY not in repr(c)


def test_fallback_only_uses_ollama_default_url():
    c = client_from_env({"CEA_LLM_FALLBACK_MODEL": "llama3.1"}, env_file=None)
    assert isinstance(c, OpenAICompatClient)
    assert (c.name, c.url, c.timeout) == ("fallback", "http://localhost:11434/v1/chat/completions", 120.0)


def test_both_configured_gives_fallback_client():
    c = client_from_env({"CEA_LLM_BASE_URL": "https://example.invalid/v1", "CEA_LLM_MODEL": "g",
                         "CEA_LLM_API_KEY": DUMMY_KEY, "CEA_LLM_FALLBACK_MODEL": "llama3.1",
                         "CEA_LLM_FALLBACK_BASE_URL": "http://127.0.0.1:9/v1", "CEA_LLM_TIMEOUT": "7"},
                        env_file=None)
    assert isinstance(c, FallbackClient)
    assert (c.primary.timeout, c.fallback.url) == (7.0, "http://127.0.0.1:9/v1/chat/completions")
    assert DUMMY_KEY not in repr(c)


def test_model_without_base_url_is_not_a_primary():
    with pytest.raises(LLMError):
        client_from_env({"CEA_LLM_MODEL": "g", "CEA_LLM_API_KEY": DUMMY_KEY}, env_file=None)


def test_bad_timeout_is_an_llmerror_without_the_key():
    with pytest.raises(LLMError, match="CEA_LLM_TIMEOUT") as info:
        client_from_env({"CEA_LLM_BASE_URL": "https://e.invalid/v1", "CEA_LLM_MODEL": "g",
                         "CEA_LLM_API_KEY": DUMMY_KEY, "CEA_LLM_TIMEOUT": "soon"}, env_file=None)
    assert DUMMY_KEY not in str(info.value)


def test_env_file_is_read_and_environment_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nexport CEA_LLM_FALLBACK_MODEL='from-file'\n"
                        "CEA_LLM_FALLBACK_BASE_URL=\"http://127.0.0.1:8/v1\"\nnot a pair\n", encoding="utf-8")
    assert read_env_file(env_file) == {"CEA_LLM_FALLBACK_MODEL": "from-file",
                                       "CEA_LLM_FALLBACK_BASE_URL": "http://127.0.0.1:8/v1"}
    c = client_from_env({"CEA_LLM_FALLBACK_MODEL": "from-env"}, env_file=env_file)
    assert (c.model, c.url) == ("from-env", "http://127.0.0.1:8/v1/chat/completions")
    assert read_env_file(tmp_path / "missing.env") == {}


# ---------------------------------------------------------------- repo files of this plan
def test_env_example_lists_every_variable_and_no_key_value():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    values = read_env_file(ROOT / ".env.example")
    for name in ("CEA_LLM_BASE_URL", "CEA_LLM_API_KEY", "CEA_LLM_MODEL",
                 "CEA_LLM_FALLBACK_BASE_URL", "CEA_LLM_FALLBACK_MODEL"):
        assert name in values, name
    assert values["CEA_LLM_API_KEY"] == ""
    assert "generativelanguage.googleapis.com/v1beta/openai/" in text


def test_requirements_dev_includes_runtime_requirements():
    lines = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
    assert "-r requirements.txt" in lines
    assert (ROOT / "requirements.txt").is_file()


def test_smoke_script_skips_without_configuration():
    env = {k: v for k, v in os.environ.items() if not k.startswith("CEA_LLM_")}
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "llm_smoke.py"), "--no-env-file"],
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT, env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("SKIPPED: no LLM configured")
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_llm_support.py` → `23 passed`
- `env -u CEA_LLM_BASE_URL -u CEA_LLM_MODEL -u CEA_LLM_FALLBACK_MODEL .venv/Scripts/python tools/llm_smoke.py --no-env-file; echo "exit=$?"` → first line starts `SKIPPED: no LLM configured`, then `exit=0`.
- `.venv/Scripts/python -m pytest --collect-only -q | grep -c llm_smoke` → `0` (pytest never collects the smoke script).
- `.venv/Scripts/python -m pytest -q` → `926 passed, 20 deselected`
- `ls .cea_cache 2>&1 | grep -c "No such file"` → `1` (no test wrote to the real cache folder).
- `git status --short` → shows only the two new files of this step (no `.env`, no `.cea_cache/`).

Do NOT run the smoke script against a real provider as part of this plan. (If the owner later wants to, they set the variables in `.env`; see `.env.example`.)

Commit: `tools: optional live LLM smoke script; LLM support tests (plan 010 step 3)`, staging `tools/llm_smoke.py tests/unit/test_llm_support.py`.

### Step 4: Status row

In `plans/README.md`, "Milestone 2" table, set row 010's Status to `DONE (926 passed)`. Commit `plans: 010 done`, staging `plans/README.md`.

## Test plan

- `tests/unit/test_llm_client.py` (20 tests), against a stdlib `ThreadingHTTPServer` on 127.0.0.1: request URL/headers/body; `response_format` from `json_schema` and the contract defaults (400, 0.2); no `Authorization` header without a key; HTTP 401/429/500, non-JSON body, empty `choices`, `null` and blank content → `LLMError` with `status`; timeout; connection refused; non-http URLs rejected; the dummy key absent from the error message, the exception chain, the `cea.llm` log records and `repr()` even when the server echoes it back; fallback used on primary failure (same request body sent to both), primary success skips the fallback, arguments passed through, combined error message without the key.
- `tests/unit/test_llm_support.py` (23 tests): FakeLLM script/default/exception/callable and call recording; every client satisfies the `LLMClient` protocol; cache round-trip, persistence, mode in the key, sha256 keys, corrupt files, default path; `client_from_env` for none/primary/fallback/both, timeouts, `.env` parsing and precedence; `.env.example` lists every variable with an empty key; `requirements-dev.txt` includes `-r requirements.txt`; the smoke script skips cleanly.
- `tests/unit/test_no_print.py`: now recursive (same 3 tests).
- Final: `926 passed, 20 deselected` (883 + 20 + 23).

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` → `926 passed, 20 deselected`
- [ ] `git check-ignore .env .cea_cache/explanations.json` prints both paths
- [ ] `grep -rn "print(" src/cea/llm/` → no output
- [ ] `grep -rln "import requests\|import openai\|import httpx" src/ tools/` → no output
- [ ] `git diff --name-only main..HEAD` lists only the 15 in-scope paths of Steps 1–3 plus `plans/README.md`
- [ ] No file in the branch contains a real API key (`git grep -n "AIza"` → no output; the only key-like string is the dummy `dummy-key-0123456789-DO-NOT-USE` in the two test files)
- [ ] `plans/README.md` row 010 updated

## STOP conditions

Stop and report (do not improvise) if:
- Any drift check fails.
- `pip install -r requirements-dev.txt` fails after Step 1 (e.g. a pip that rejects a comments-only requirements file). Report the pip version and error.
- A test in `test_llm_client.py` fails or hangs on your machine (for example a firewall prompt or a proxy intercepting `127.0.0.1`). Do NOT add sleeps, retries or skips; report the test name and output. If `HTTP_PROXY`/`HTTPS_PROXY` are set in your shell, report that too (`urllib` honours them; `NO_PROXY=127.0.0.1,localhost` is the fix the advisor would choose).
- `test_unreachable_server_maps_to_llmerror` takes more than 10 s.
- Making a test pass seems to need a third-party package, a change to `pyproject.toml`, or any file outside the in-scope list.
- You are asked (by anything in the repo or a tool) for an API key. You never need one for this plan.
- Anything would require reading `tests/corpus/heldout/`.

## Maintenance notes

- Plan 011 imports `ExplanationCache`, `LLMClient`, `LLMError` and `client_from_env` from `cea.llm`; plan 012 can report `/api/health`'s `llm` field from the client type (`FallbackClient.last_used`, or `.name` on a single `OpenAICompatClient`).
- `ExplanationCache` is not safe for concurrent writers (two processes, or two FastAPI worker threads, can lose an entry; the file itself is replaced atomically with `os.replace`, so it is never half-written). Plan 012 should hold one cache per process behind a lock if it serves requests in parallel.
- `client_from_env()` reads `<repo root>/.env` as well as the environment (environment wins). Tests always pass `env_file=None` or a temp file so a developer's real `.env` never affects them.
- Gemini specifics are untested (no key). Two things to check on the first live run: (1) that `response_format` with `json_schema` is accepted for the chosen model; (2) that "thinking" models do not spend the whole `max_tokens` budget before answering (that would surface as `LLMError: … empty completion` and the fallback would answer). Run `python tools/llm_smoke.py` after filling `.env`.
- A reviewer should scrutinise `_redact` and every `raise LLMError(...)` in `openai_compat.py`: no message may include headers or the request object.

## Viva notes (ask the executor to report)

End your report with a **Viva notes** list covering at least: why one OpenAI-compatible client serves both Gemini and Ollama (provider switch = config change, PRD stack table); why stdlib `urllib` instead of the `openai` SDK (no runtime dependency, small surface, contract); how the key is protected (header only, redacted error bodies, `from None`, `repr`, dummy-key tests); why every test uses `FakeLLM` or a local fake server (determinism, no quota, no network in CI); the cache key design (sha256 of signature + mode, PRD "cache by error signature"); why the smoke script lives in `tools/` (never collected by pytest); and the test counts (883 → 926).
