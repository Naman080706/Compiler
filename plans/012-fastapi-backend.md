# Plan 012: Serve the compiler and the F3 agent over a FastAPI backend (`src/cea/api.py`)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md` (the "Milestone 2" table, row 012), unless a reviewer
> dispatched you and told you they maintain the index. End your final report
> with a **Viva notes** list: the decisions, trade-offs or deviations an
> examiner might ask about (see `plans/README.md`, "Viva notes convention").
> Do not edit `VIVA.md`; the advisor folds your notes into it.
>
> Every code block marked "exact content" is the whole file to write; copy it
> verbatim. Do not reformat or "improve" it. The advisor ran exactly this
> `api.py` and `test_api.py` (Python 3.13.1, the pinned versions below) on a
> scratch copy of `40d4ef9` + plan 009's code + the real `src/cea/llm/`,
> `src/cea/agent.py` and `src/cea/rules.py` listings of plans 010 and 011, and
> got every count quoted below. If a verification
> fails and your file is identical to the plan, STOP and report.
>
> **Never open, read, list or run anything under `tests/corpus/heldout/`.**
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat 40d4ef9..HEAD -- src/cea/api.py tests/unit/test_api.py web` must print nothing, and `ls src/cea/api.py tests/unit/test_api.py 2>&1 | grep -c "No such file"` must print `2`.
> 2. Plan 009 has landed: `grep -c "clusters: list\[Cluster\]" src/cea/pipeline.py` prints `1`.
> 3. `ls requirements.txt requirements-dev.txt` lists both files (plan 010 creates `requirements.txt`), and `grep -c "^-r requirements.txt" requirements-dev.txt` prints `1`.
> 4. `grep -ci "fastapi\|uvicorn\|httpx" requirements.txt requirements-dev.txt` prints `0` for both files.
> 5. The contract names from plans 010/011 exist with the expected shapes. This must print `x True ok`:
>    ```
>    PYTHONPATH=src .venv/Scripts/python -c "from cea.llm import ExplanationCache, FakeLLM, FallbackClient, client_from_env; from cea.agent import Agent, Answer, Explanation, FixSuggestion; f = FakeLLM(['x']); print(f.complete([{'role': 'user', 'content': 'q'}]), FixSuggestion('d', 'p').verified is False, 'ok' if Agent(FakeLLM([])) else '')"
>    ```
> 6. `.venv/Scripts/python -m pytest -q` exits 0. Write down its last line (`B passed, 20 deselected`, maybe with `1 skipped`): **B** is your baseline, used below.
>
> If any check fails, STOP and report which one and its output.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (a new module and new dependencies; nothing existing changes behaviour)
- **Depends on**: `plans/011-*.md` (F3 agent; it needs 009 and 010), all merged into `main`
- **Category**: direction (milestone 2, PRD F2/F3/F4 behind an HTTP API)
- **Planned at**: commit `40d4ef9`, 2026-10-11

## Why this matters

The project is a course compiler for a strict C99 subset (Python, `src/cea/`). Milestone 2 puts it behind a web UI (plan 013, React + Monaco). That UI needs a small JSON API: compile a source and get the records plus the F2 clusters, then ask the F3 agent to explain a record, suggest a fix, or answer a follow-up question. This plan adds `src/cea/api.py` (FastAPI), exactly as specified by the binding contract `plans/m2-architecture.md` §3, with a 64 KB source limit, stateless re-compilation on every request, CORS for the Vite dev origin only, and the agent injected through a FastAPI dependency so every test runs without network. It also guarantees, by test, that a filename or any other extra body field (student name, path) never reaches the agent (PRD privacy note).

## Current state

- `plans/m2-architecture.md` §3 (binding contract), quoted:

  | Method/path | Body | Returns |
  |---|---|---|
  | `POST /api/compile` | `{source}` | `{ok, summary, records:[record.to_dict()], clusters:[{root_id, symptom_ids}]}` |
  | `POST /api/explain` | `{source, record_id, mode}` | `Explanation` as JSON |
  | `POST /api/fix` | `{source, record_id}` | `{diff, patched_source, verified:false}` |
  | `POST /api/ask` | `{source, record_id, question}` | `{text, refused}` |
  | `GET /api/health` | — | `{status:"ok", llm:"primary"\|"fallback"\|"none"}` |

  "The source is size-limited (64 KB). The server re-compiles each request; the server is stateless. CORS is allowed for the Vite dev origin only. Run with `uvicorn cea.api:app`. Tests use FastAPI's `TestClient` with `FakeLLM` injected through a dependency override."
- Contract names this plan uses (and nothing else from 010/011):
  - `cea.pipeline.compile_source(source, filename) -> CompileResult` with `.errors` (records), `.ok`, `.summary()`, `.clusters` (list of `Cluster(root, symptoms)`, plan 009).
  - `cea.records.ErrorRecord.to_dict()` gives the fields `id, phase, code, severity, line, column, found, expected, snippet, root_id, rule_ref, language, caused_by, span_end, message`. No filename field exists.
  - `cea.agent`: `Agent(llm, cache=None)` with `explain(record, source, mode) -> Explanation(text, rule_ref, cited_rule, mode)`, `suggest_fix(record, source) -> FixSuggestion(diff, patched_source, verified=False)`, `ask(record, source, question) -> Answer(text, refused)`.
  - `cea.llm` (plan 010; `src/cea/llm/__init__.py` exports all of these):
    - `FakeLLM(script=(), *, default=None)`: scripted; `FakeLLM(['x']).complete(messages)` returns `'x'`; an exhausted script with no default raises `LLMError`.
    - `ExplanationCache(path=None)`: one JSON file, default `<repo>/.cea_cache/explanations.json` (git-ignored). It is read lazily, so constructing it touches no disk.
    - `client_from_env(environ=None, *, env_file=<repo>/.env) -> LLMClient`: reads `<repo>/.env`, then lets the real environment (`os.environ`, or `environ` when given) win over it. Primary (`CEA_LLM_BASE_URL` and `CEA_LLM_MODEL` non-empty) plus fallback (`CEA_LLM_FALLBACK_MODEL` non-empty) gives a `FallbackClient`; only one gives that `OpenAICompatClient`, whose `.name` is `"primary"` or `"fallback"`; neither raises `LLMError`. A non-numeric `CEA_LLM_TIMEOUT` raises `LLMError`; a non-http URL raises `ValueError`. Building a client makes no network call.
    - The `LLMClient` protocol `complete(messages, *, json_schema=None, max_tokens=400, temperature=0.2) -> str`.
- Contract §5: "`print` only in `cli.py`. … `api.py` returns data; the `uvicorn` server logs." `tests/unit/test_no_print.py` greps every module under `src/cea/` except `cli.py` (plan 010 made it recursive) for `print(` and `sys.stdout`/`sys.stderr`, so `api.py` is checked automatically. `api.py` uses `logging` only and never logs an exception message (it could contain a URL or key), only the exception type name.
- Contract §5: "No network in tests." Every test here uses `SpyAgent` (a stand-in that records its arguments) or the real `Agent` over `FakeLLM`.
- Repo conventions: module docstring on every file, type hints, plain `assert` + `pytest.mark.parametrize` in `tests/unit/test_<module>.py` (model: `tests/unit/test_pipeline_cli.py`). `pyproject.toml` sets `pythonpath = ["src"]`.

### Advisor decisions you must not change

1. **Pinned versions** (installed and run by the advisor on 2026-10-11, Python 3.13.1): `fastapi==0.143.0`, `uvicorn==0.54.0` (plain, not `uvicorn[standard]`; `--reload` works without extras), and for tests the standard `httpx==0.28.1` (the current release). Starlette 1.7 (pulled in by FastAPI 0.143) emits a `StarletteDeprecationWarning` (a `UserWarning` subclass) when its `TestClient` is imported: "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead." The owner chose not to add `httpx2`, so `pyproject.toml` silences exactly that message with one `filterwarnings` entry. The entry names the built-in `UserWarning` category, so pytest never has to import Starlette to read its own configuration.
2. **Extra body fields are ignored, not rejected** (`extra="ignore"`). A client that sends `filename` still works, but the value is dropped before any code sees it. The compiler is always called with the fixed display name `input.c`.
3. **The 64 KB limit counts UTF-8 bytes** (`len(source.encode("utf-8")) > 65536` gives 413), checked before compiling, on every endpoint.
4. **Errors**: unknown `record_id` → 404; invalid body → 422 (FastAPI default); agent or LLM exception → 502 with a fixed message (never the exception text); `client_from_env()` failing → 503 "The AI assistant is not configured. See .env.example." `/api/compile` and `/api/health` never need the agent.
5. **`/api/health` reports configuration, not reachability, through plan 010's own config path.** It calls `client_from_env()` inside a `try`, so `<repo>/.env` counts and real environment variables win. A `FallbackClient` or a client named `"primary"` gives `primary`; a client named `"fallback"` gives `fallback`; any exception gives `none`. Only those fixed words are returned, never a URL, model name or key. It makes no network call.
6. **CORS** allows exactly `http://localhost:5173` (the Vite dev server), methods GET and POST, header `Content-Type`. The UI normally goes through the Vite proxy (same origin), so CORS only matters if someone opens the API from the dev origin directly.
7. **The agent is built once** (`functools.lru_cache`) as `Agent(client_from_env(), cache=ExplanationCache())`, so explanations are cached by error signature in `.cea_cache/`. This saves free-tier quota during demos.

## Commands you will need

| Purpose | Command (project root, Git Bash) | Expected on success |
|---|---|---|
| venv (once, if missing) | `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt` | exit 0 |
| Install after Step 1 | `.venv/Scripts/python -m pip install -r requirements-dev.txt` | exit 0 |
| API tests | `.venv/Scripts/python -m pytest -q tests/unit/test_api.py` | `59 passed` |
| Full suite | `.venv/Scripts/python -m pytest -q` | `B+59 passed, 20 deselected` |
| Run the server | `.venv/Scripts/python -m uvicorn cea.api:app --reload --app-dir src` | `Uvicorn running on http://127.0.0.1:8000` |

## Scope

**In scope** (the only files you may create or modify):
- `requirements.txt` (append 2 lines), `requirements-dev.txt` (append 1 line)
- `pyproject.toml` (one `filterwarnings` line in `[tool.pytest.ini_options]`, nothing else)
- `src/cea/api.py` (create)
- `tests/unit/test_api.py` (create)
- `README.md` (append one section at the end)
- `plans/README.md` (status row 012 only)

**Out of scope** (do NOT touch):
- `src/cea/agent.py`, `src/cea/llm/**`, `src/cea/rules.py` (plans 010/011). If the API seems to need a change there, STOP.
- `src/cea/pipeline.py`, `cluster.py`, `records.py`, and every compiler module: the API only calls them.
- `web/**` (plan 013), `VIVA.md`, `plans/m2-architecture.md`, `docs/**`.
- `tests/corpus/**`. Never read `tests/corpus/heldout/`.
- Any `.env` file. Never write, print or commit a key value.

## Git workflow

- Branch: `advisor/012-fastapi-backend` from `main`.
- One commit per step. Stage by explicit path (never `git add -A` / `git add .`). Message style as in `git log`: `cea: ... (plan 012 step N)`, `deps: ...`, `docs: ...`, `plans: ...`. Every commit message ends with a blank line and then:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
- Do NOT push (there is no remote). Do NOT merge; the owner reviews first.

## Steps

### Step 1: Pin the backend dependencies

Append these two lines to the END of `requirements.txt` (keep everything plan 010 wrote):
```
# FastAPI backend (plan 012)
fastapi==0.143.0
uvicorn==0.54.0
```
Append these two lines to the END of `requirements-dev.txt`:
```
# FastAPI TestClient transport (plan 012)
httpx==0.28.1
```
In `pyproject.toml`, insert this one line directly AFTER the line `addopts = "-m 'not heldout'"` (exact content, a single line):
```
filterwarnings = ["ignore:Using `httpx` with `starlette.testclient` is deprecated:UserWarning"]   # Starlette 1.7 TestClient nudges toward httpx2; the project uses httpx (plan 012)
```
If `[tool.pytest.ini_options]` already has a `filterwarnings` key (another plan added one), STOP and report instead of adding a second key.
Then run `.venv/Scripts/python -m pip install -r requirements-dev.txt`.

**Verify**:
- `grep -c "^fastapi==0.143.0$\|^uvicorn==0.54.0$" requirements.txt` → `2`
- `grep -c "^httpx==0.28.1$" requirements-dev.txt` → `1`
- `grep -c "^filterwarnings = " pyproject.toml` → `1`
- `.venv/Scripts/python -c "import fastapi, uvicorn, starlette, httpx; print(fastapi.__version__, uvicorn.__version__, starlette.__version__, httpx.__version__)"` → `0.143.0 0.54.0 1.7.0 0.28.1`
- `.venv/Scripts/python -m pytest -q` → still `B passed, 20 deselected` (nothing new yet)

Commit: `deps: pin fastapi, uvicorn and httpx for the backend (plan 012 step 1)`, staging `requirements.txt requirements-dev.txt pyproject.toml`.

### Step 2: `src/cea/api.py` and its tests

2a. Create `src/cea/api.py`, exact content:

```python
"""FastAPI backend for the web UI (plan 012, plans/m2-architecture.md section 3).

Endpoints (all JSON):
    POST /api/compile  {source}                      -> {ok, summary, records, clusters}
    POST /api/explain  {source, record_id, mode}     -> Explanation
    POST /api/fix      {source, record_id}           -> {diff, patched_source, verified}
    POST /api/ask      {source, record_id, question} -> {text, refused}
    GET  /api/health                                 -> {status, llm}

The server is stateless: every request re-compiles ``source``, so a record id
is only meaningful together with the source it came from. The request's
filename, paths or any other extra body field are never read (privacy note of
the PRD; pydantic drops unknown fields), and the compiler always sees the
fixed display name ``input.c``. The AI agent is injected through the
``get_agent`` dependency, so tests replace it with ``FakeLLM``
(``app.dependency_overrides[get_agent]``). Nothing here prints; problems go to
the ``cea.api`` logger, which never receives a key value. The LLM
configuration (and ``/api/health``) comes from plan 010's ``client_from_env()``:
``CEA_LLM_*`` environment variables, then ``<repo>/.env``.

Run (from the project root):
    .venv/Scripts/python -m uvicorn cea.api:app --reload --app-dir src
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Literal, TypeVar

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from cea.agent import Agent
from cea.llm import ExplanationCache, FallbackClient, client_from_env
from cea.pipeline import CompileResult, compile_source
from cea.records import ErrorRecord

MAX_SOURCE_BYTES = 64 * 1024          # contract section 3: "The source is size-limited (64 KB)"
MAX_QUESTION_CHARS = 1000
DEV_ORIGIN = "http://localhost:5173"  # the Vite dev server; the only CORS origin allowed
DISPLAY_NAME = "input.c"              # the client's filename is never accepted

logger = logging.getLogger("cea.api")
T = TypeVar("T")

app = FastAPI(title="Compiler Error Assistant API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[DEV_ORIGIN], allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")      # filename, student name, ... are dropped here
    source: str


class FixRequest(CompileRequest):
    record_id: str


class ExplainRequest(FixRequest):
    mode: Literal["short", "expand"] = "short"


class AskRequest(FixRequest):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


@lru_cache(maxsize=1)
def _env_agent() -> Agent:
    """The production agent, built once from plan 010's configuration, with the on-disk explanation cache."""
    return Agent(client_from_env(), cache=ExplanationCache())


def get_agent() -> Agent:
    """FastAPI dependency: the agent used by /api/explain, /api/fix and /api/ask.

    Tests override it: ``app.dependency_overrides[get_agent] = lambda: Agent(FakeLLM(...))``.
    """
    try:
        return _env_agent()
    except Exception as exc:  # any configuration failure becomes a clean 503
        logger.warning("AI assistant could not be configured (%s)", type(exc).__name__)
        raise HTTPException(status_code=503,
                            detail="The AI assistant is not configured. See .env.example.") from exc


def llm_status() -> str:
    """"primary" | "fallback" | "none": which LLM is configured (not whether it is reachable).

    Uses plan 010's ``client_from_env()``, so ``<repo>/.env`` is read and real
    environment variables win over it. Building a client makes no network call.
    Only these fixed words leave this function, never a URL, model or key.
    """
    try:
        client = client_from_env()
    except Exception:  # LLMError (nothing configured, bad timeout) or ValueError (bad URL)
        return "none"
    if isinstance(client, FallbackClient):
        return "primary"                                   # a primary is configured, with a fallback behind it
    return "fallback" if getattr(client, "name", None) == "fallback" else "primary"


def _compile(source: str) -> CompileResult:
    """Re-compile the request's source (stateless server); 413 above 64 KB of UTF-8."""
    if len(source.encode("utf-8", errors="surrogatepass")) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail=f"Source is larger than {MAX_SOURCE_BYTES} bytes.")
    return compile_source(source, DISPLAY_NAME)


def _record(result: CompileResult, record_id: str) -> ErrorRecord:
    """The record with this id in ``result``; 404 when the source has no such record."""
    for rec in result.errors:
        if rec.id == record_id:
            return rec
    raise HTTPException(status_code=404, detail="No error record with that id in this source.")


def _call_agent(call: Callable[..., T], *args: object) -> T:
    """Run one agent call; an LLM or agent failure becomes 502 instead of a stack trace."""
    try:
        return call(*args)
    except Exception as exc:
        logger.warning("AI assistant call failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="The AI assistant did not answer. Try again.") from exc


AgentDep = Annotated[Agent, Depends(get_agent)]


@app.post("/api/compile")
def compile_endpoint(req: CompileRequest) -> dict:
    result = _compile(req.source)
    return {"ok": result.ok, "summary": result.summary(),
            "records": [r.to_dict() for r in result.errors],
            "clusters": [{"root_id": c.root.id, "symptom_ids": [s.id for s in c.symptoms]}
                         for c in result.clusters]}


@app.post("/api/explain")
def explain_endpoint(req: ExplainRequest, agent: AgentDep) -> dict:
    record = _record(_compile(req.source), req.record_id)
    exp = _call_agent(agent.explain, record, req.source, req.mode)
    return {"text": exp.text, "rule_ref": exp.rule_ref, "cited_rule": exp.cited_rule, "mode": exp.mode}


@app.post("/api/fix")
def fix_endpoint(req: FixRequest, agent: AgentDep) -> dict:
    record = _record(_compile(req.source), req.record_id)
    fix = _call_agent(agent.suggest_fix, record, req.source)
    return {"diff": fix.diff, "patched_source": fix.patched_source, "verified": bool(fix.verified)}


@app.post("/api/ask")
def ask_endpoint(req: AskRequest, agent: AgentDep) -> dict:
    record = _record(_compile(req.source), req.record_id)
    answer = _call_agent(agent.ask, record, req.source, req.question)
    return {"text": answer.text, "refused": bool(answer.refused)}


@app.get("/api/health")
def health_endpoint() -> dict:
    return {"status": "ok", "llm": llm_status()}
```

2b. Create `tests/unit/test_api.py`, exact content:

```python
"""FastAPI backend (plan 012, plans/m2-architecture.md section 3), through TestClient.

No network: the agent is injected through the ``get_agent`` dependency, either
as ``SpyAgent`` (records exactly what the API hands the agent) or as the real
``Agent`` over ``FakeLLM``.
"""
import pytest
from fastapi.testclient import TestClient

from cea import api
from cea.agent import Agent, Answer, Explanation, FixSuggestion
from cea.llm import FakeLLM
from cea.llm import client_from_env as real_client_from_env
from cea.pipeline import compile_source
from cea.records import ErrorRecord

SRC_OK = "int main(void) {\n    return 0;\n}\n"
SRC_UNDECLARED = "int main(void) {\n    x = 1;\n    x = 2;\n    return 0;\n}\n"      # E-0001 root, E-0002 symptom
SRC_CASCADE = "int main(void) {\n    int x = 5 @ 2;\n    return x;\n}\n"              # LEX root, SYN symptom
SRC_WARNING = "int main(void) {\n    int unused = 1;\n    return 0;\n}\n"            # one warning only
RECORD_KEYS = ["id", "phase", "code", "severity", "line", "column", "found", "expected", "snippet",
               "root_id", "rule_ref", "language", "caused_by", "span_end", "message"]
PRIVATE = {"filename": "alice-smith-hw3.c", "file_path": "C:/Users/alice.smith/hw3.c",
           "student": "Alice Smith", "student_id": "S1234567"}
DUMMY_KEY = "dummy-key-not-real-0123"
PRIMARY = {"CEA_LLM_BASE_URL": "https://example.invalid/v1/", "CEA_LLM_MODEL": "m", "CEA_LLM_API_KEY": DUMMY_KEY}


class SpyAgent:
    """Stands in for cea.agent.Agent and records every call's arguments."""

    def __init__(self):
        self.calls = []

    def explain(self, record, source, mode="short"):
        self.calls.append(("explain", record, source, mode))
        return Explanation(text=f"why {record.id}", rule_ref=record.rule_ref, cited_rule=None, mode=mode)

    def suggest_fix(self, record, source):
        self.calls.append(("fix", record, source))
        return FixSuggestion(diff="--- a/input.c\n+++ b/input.c\n", patched_source=source + "\n")

    def ask(self, record, source, question):
        self.calls.append(("ask", record, source, question))
        return Answer(text=f"answer to {question}", refused=False)


class BrokenAgent:
    """Every call fails, as an unreachable LLM would."""

    def explain(self, *args):
        raise RuntimeError("model unreachable")

    suggest_fix = ask = explain


class RecordingLLM:
    """Wraps FakeLLM and keeps every message list the agent sends (LLMClient protocol)."""

    def __init__(self, inner):
        self.inner = inner
        self.sent = []

    def complete(self, messages, *, json_schema=None, max_tokens=400, temperature=0.2):
        self.sent.append(messages)
        return self.inner.complete(messages, json_schema=json_schema, max_tokens=max_tokens,
                                   temperature=temperature)


@pytest.fixture
def client():
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    api._env_agent.cache_clear()


@pytest.fixture
def spy():
    agent = SpyAgent()
    api.app.dependency_overrides[api.get_agent] = lambda: agent
    return agent


def body(path, source, **extra):
    """A valid request body for ``path``."""
    data = {"source": source}
    if path != "/api/compile":
        data["record_id"] = "E-0001"
    if path == "/api/explain":
        data["mode"] = "short"
    if path == "/api/ask":
        data["question"] = "Why is this an error?"
    data.update(extra)
    return data


AGENT_PATHS = ["/api/explain", "/api/fix", "/api/ask"]


# ---------------------------------------------------------------- /api/health
def use_config(monkeypatch, environ, env_file=None):
    """Make the API see exactly this configuration through plan 010's real client_from_env()."""
    monkeypatch.setattr(api, "client_from_env", lambda: real_client_from_env(environ, env_file=env_file))


@pytest.mark.parametrize("environ,expected", [
    (PRIMARY, "primary"),
    ({**PRIMARY, "CEA_LLM_FALLBACK_MODEL": "small"}, "primary"),
    ({"CEA_LLM_BASE_URL": "https://example.invalid/v1/", "CEA_LLM_FALLBACK_MODEL": "small"}, "fallback"),
    ({"CEA_LLM_FALLBACK_MODEL": "small"}, "fallback"),
    ({"CEA_LLM_API_KEY": DUMMY_KEY}, "none"),
    ({**PRIMARY, "CEA_LLM_TIMEOUT": "soon"}, "none"),
    ({}, "none"),
])
def test_health(client, monkeypatch, environ, expected):
    use_config(monkeypatch, environ)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "llm": expected}
    assert DUMMY_KEY not in resp.text


def test_health_reads_the_env_file(client, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in PRIMARY.items()), encoding="utf-8")
    use_config(monkeypatch, {}, env_file)
    resp = client.get("/api/health")
    assert resp.json() == {"status": "ok", "llm": "primary"} and DUMMY_KEY not in resp.text


def test_health_environment_wins_over_the_env_file(client, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in PRIMARY.items()), encoding="utf-8")
    use_config(monkeypatch, {"CEA_LLM_MODEL": ""}, env_file)
    assert client.get("/api/health").json() == {"status": "ok", "llm": "none"}


# ---------------------------------------------------------------- /api/compile
def test_compile_valid_program(client):
    resp = client.post("/api/compile", json={"source": SRC_OK})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "summary": "0 fatal, 0 warnings", "records": [], "clusters": []}


def test_compile_undeclared_groups_uses(client):
    data = client.post("/api/compile", json={"source": SRC_UNDECLARED}).json()
    assert data["ok"] is False and data["summary"] == "2 fatal, 0 warnings"
    assert [list(r) for r in data["records"]] == [RECORD_KEYS, RECORD_KEYS]
    assert [(r["id"], r["code"], r["line"], r["root_id"]) for r in data["records"]] == [
        ("E-0001", "SEM-UNDECLARED-VAR", 2, "E-0001"), ("E-0002", "SEM-UNDECLARED-VAR", 3, "E-0001")]
    assert data["clusters"] == [{"root_id": "E-0001", "symptom_ids": ["E-0002"]}]


def test_compile_cascade_has_one_cluster(client):
    data = client.post("/api/compile", json={"source": SRC_CASCADE}).json()
    assert [(r["phase"], r["code"]) for r in data["records"]] == [
        ("lexical", "LEX-INVALID-CHAR"), ("syntax", "SYN-MISSING-SEMICOLON")]
    assert data["clusters"] == [{"root_id": "E-0001", "symptom_ids": ["E-0002"]}]


def test_compile_warning_only_still_ok(client):
    data = client.post("/api/compile", json={"source": SRC_WARNING}).json()
    assert data["ok"] is True and data["summary"] == "0 fatal, 1 warning"
    assert [(r["code"], r["severity"]) for r in data["records"]] == [("WRN-UNUSED-VAR", "warning")]


def test_compile_matches_the_pipeline(client):
    data = client.post("/api/compile", json={"source": SRC_CASCADE}).json()
    assert data["records"] == [r.to_dict() for r in compile_source(SRC_CASCADE, "x.c").errors]


def test_compile_needs_no_agent(client):
    api.app.dependency_overrides[api.get_agent] = BrokenAgent
    assert client.post("/api/compile", json={"source": SRC_OK}).status_code == 200


# ---------------------------------------------------------------- size limit and validation
@pytest.mark.parametrize("path", ["/api/compile", *AGENT_PATHS])
def test_source_over_64kb_is_413(client, spy, path):
    resp = client.post(path, json=body(path, "a" * (64 * 1024 + 1)))
    assert resp.status_code == 413
    assert spy.calls == []


def test_source_of_exactly_64kb_is_accepted(client):
    assert client.post("/api/compile", json={"source": "a" * (64 * 1024)}).status_code == 200


def test_limit_counts_utf8_bytes_not_characters(client):
    source = "\u00e9" * (32 * 1024 + 1)      # 32769 characters, 65538 bytes
    assert client.post("/api/compile", json={"source": source}).status_code == 413


@pytest.mark.parametrize("path,data", [
    ("/api/compile", {}),
    ("/api/compile", {"source": 42}),
    ("/api/explain", {"source": SRC_UNDECLARED}),
    ("/api/explain", {"source": SRC_UNDECLARED, "record_id": "E-0001", "mode": "long"}),
    ("/api/fix", {"record_id": "E-0001"}),
    ("/api/ask", {"source": SRC_UNDECLARED, "record_id": "E-0001"}),
    ("/api/ask", {"source": SRC_UNDECLARED, "record_id": "E-0001", "question": ""}),
    ("/api/ask", {"source": SRC_UNDECLARED, "record_id": "E-0001", "question": "q" * 1001}),
])
def test_invalid_body_is_422(client, spy, path, data):
    assert client.post(path, json=data).status_code == 422
    assert spy.calls == []


# ---------------------------------------------------------------- unknown record ids
@pytest.mark.parametrize("path", AGENT_PATHS)
@pytest.mark.parametrize("source,record_id", [(SRC_UNDECLARED, "E-0099"), (SRC_UNDECLARED, "e-0001"),
                                              (SRC_OK, "E-0001")])
def test_unknown_record_id_is_404(client, spy, path, source, record_id):
    resp = client.post(path, json=body(path, source, record_id=record_id))
    assert resp.status_code == 404
    assert spy.calls == []


# ---------------------------------------------------------------- /api/explain, /api/fix, /api/ask
@pytest.mark.parametrize("mode", ["short", "expand"])
def test_explain(client, spy, mode):
    resp = client.post("/api/explain", json=body("/api/explain", SRC_UNDECLARED, record_id="E-0002", mode=mode))
    assert resp.status_code == 200
    assert resp.json() == {"text": "why E-0002", "rule_ref": "sem.declare_before_use", "cited_rule": None,
                           "mode": mode}
    ((name, record, source, got_mode),) = spy.calls
    assert (name, record.id, source, got_mode) == ("explain", "E-0002", SRC_UNDECLARED, mode)


def test_explain_mode_defaults_to_short(client, spy):
    resp = client.post("/api/explain", json={"source": SRC_UNDECLARED, "record_id": "E-0001"})
    assert resp.status_code == 200 and resp.json()["mode"] == "short"


def test_fix_is_never_verified(client, spy):
    resp = client.post("/api/fix", json=body("/api/fix", SRC_CASCADE))
    assert resp.status_code == 200
    assert resp.json() == {"diff": "--- a/input.c\n+++ b/input.c\n", "patched_source": SRC_CASCADE + "\n",
                           "verified": False}
    assert [(c[0], c[1].code) for c in spy.calls] == [("fix", "LEX-INVALID-CHAR")]


def test_ask(client, spy):
    resp = client.post("/api/ask", json=body("/api/ask", SRC_UNDECLARED, question="Where is x declared?"))
    assert resp.status_code == 200
    assert resp.json() == {"text": "answer to Where is x declared?", "refused": False}
    assert spy.calls[0][3] == "Where is x declared?"


@pytest.mark.parametrize("path", AGENT_PATHS)
def test_agent_failure_is_502(client, path):
    api.app.dependency_overrides[api.get_agent] = BrokenAgent
    resp = client.post(path, json=body(path, SRC_UNDECLARED))
    assert resp.status_code == 502
    assert "model unreachable" not in resp.text


# ---------------------------------------------------------------- privacy: only compiler context reaches the agent
@pytest.mark.parametrize("path", AGENT_PATHS)
def test_filename_and_extra_fields_never_reach_the_agent(client, spy, path):
    resp = client.post(path, json=body(path, SRC_UNDECLARED, **PRIVATE))
    assert resp.status_code == 200
    (call,) = spy.calls
    record, source = call[1], call[2]
    assert isinstance(record, ErrorRecord) and source == SRC_UNDECLARED
    assert len(call) == (3 if path == "/api/fix" else 4)                 # no extra arguments
    seen = repr(call) + repr(record.to_dict())
    for value in PRIVATE.values():
        assert value not in seen
    assert "alice" not in seen.lower()


# ---------------------------------------------------------------- the real Agent over FakeLLM
@pytest.fixture
def fake_agent():
    llm = RecordingLLM(FakeLLM(["not json"] * 20))
    api.app.dependency_overrides[api.get_agent] = lambda: Agent(llm)
    return llm


@pytest.mark.parametrize("path,keys", [("/api/explain", {"text", "rule_ref", "cited_rule", "mode"}),
                                       ("/api/fix", {"diff", "patched_source", "verified"}),
                                       ("/api/ask", {"text", "refused"})])
def test_real_agent_over_fake_llm(client, fake_agent, path, keys):
    resp = client.post(path, json=body(path, SRC_UNDECLARED, **PRIVATE))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) == keys
    if path == "/api/fix":
        assert data["verified"] is False
    sent = repr(fake_agent.sent).lower()
    assert "alice" not in sent and "hw3" not in sent and "s1234567" not in sent


# ---------------------------------------------------------------- the default dependency
def test_get_agent_builds_the_agent_with_the_cache(monkeypatch):
    made = []

    class SpyCache:
        def __init__(self, path=None):
            made.append(path)

    api._env_agent.cache_clear()
    monkeypatch.setattr(api, "client_from_env", lambda: FakeLLM([]))
    monkeypatch.setattr(api, "ExplanationCache", SpyCache)
    try:
        agent = api.get_agent()
        assert isinstance(agent, Agent) and api.get_agent() is agent      # built once
        assert made == [None]                                              # ExplanationCache() at its default path
    finally:
        api._env_agent.cache_clear()


def test_unconfigured_llm_is_503(client, monkeypatch):
    def broken():
        raise RuntimeError("no CEA_LLM_* configuration")
    api._env_agent.cache_clear()
    monkeypatch.setattr(api, "client_from_env", broken)
    resp = client.post("/api/explain", json=body("/api/explain", SRC_UNDECLARED))
    assert resp.status_code == 503


# ---------------------------------------------------------------- CORS and routes
def test_cors_allows_the_vite_dev_origin(client):
    resp = client.options("/api/compile", headers={"Origin": "http://localhost:5173",
                                                   "Access-Control-Request-Method": "POST",
                                                   "Access-Control-Request-Headers": "content-type"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize("origin", ["http://evil.example", "http://127.0.0.1:5173", "http://localhost:3000"])
def test_cors_rejects_other_origins(client, origin):
    pre = client.options("/api/compile", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 400
    assert "access-control-allow-origin" not in pre.headers
    get = client.get("/api/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in get.headers


def test_exactly_the_contract_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {(p, m) for p, ops in paths.items() for m in ops} == {
        ("/api/compile", "post"), ("/api/explain", "post"), ("/api/fix", "post"), ("/api/ask", "post"),
        ("/api/health", "get")}
```

What the 59 tests cover: health (7 configurations through the real `client_from_env` with `env_file=None`, each checking that the dummy key is absent from the response; the `.env` file is read; real environment variables win over it), compile (6: valid, undeclared grouping with the exact record key order, cascade, warnings-only, equality with the pipeline, no agent needed), size limit (4 endpoints over 64 KB, exactly 64 KB accepted, bytes not characters), invalid bodies (8 → 422), unknown record ids (9 → 404), explain (2 modes + default mode), fix (`verified` is `False`), ask, agent failure (3 → 502, exception text not leaked), privacy (3: filename, path, student name and id never reach the agent, and the agent gets exactly the contract arguments), the real `Agent` over `FakeLLM` (3, including what the LLM receives), the default dependency (built once, with `ExplanationCache()` at its default path; 503 when unconfigured), CORS (1 allowed + 3 rejected origins), and the exact route list.

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_api.py` → `59 passed`
- `.venv/Scripts/python -m pytest -q tests/unit/test_no_print.py` → `3 passed`
- `.venv/Scripts/python -m pytest -q` → `B+59 passed, 20 deselected` (e.g. if B was 950, expect 1009)
- `.venv/Scripts/python -m pytest -q tests/unit/test_api.py 2>&1 | grep -ci "warning"` → `0` (the Starlette httpx warning is filtered, and nothing else warns)
- The tests never write the real cache: if `.cea_cache/` did not exist before this step, `ls .cea_cache 2>&1 | grep -c "No such file"` → `1`

If `test_real_agent_over_fake_llm` fails while the `SpyAgent` tests pass, the real `Agent` behaves differently from the contract (for example it raises on invalid model output instead of falling back). STOP and report the failing case and its `resp.text`; do not change `api.py` or the agent.

Commit: `cea: FastAPI backend for compile, explain, fix, ask and health (plan 012 step 2)`, staging `src/cea/api.py tests/unit/test_api.py`.

### Step 3: Smoke-run the server and document the run command

3a. Start the server in the background, call two endpoints, then stop it (Git Bash, project root):
```
.venv/Scripts/python -m uvicorn cea.api:app --app-dir src --port 8000 > /tmp/cea-uvicorn.log 2>&1 &
sleep 4
curl -s http://127.0.0.1:8000/api/health; echo
curl -s -X POST -H "Content-Type: application/json" -d '{"source":"int main(void) {\n    x = 1;\n    return 0;\n}\n"}' http://127.0.0.1:8000/api/compile | head -c 120; echo
kill %1
```
Expected: the first line is `{"status":"ok","llm":"none"}` (or `"primary"`/`"fallback"` if `CEA_LLM_*` is set in your shell or in `.env`; it never contains a URL or key), and the second starts with `{"ok":false,"summary":"1 fatal, 0 warnings","records":[{"id":"E-0001","phase":"semantic","code":"SEM-UNDECLARED-VAR"`. If port 8000 is busy, use `--port 8010` in both the command and the URLs. If `kill %1` does not stop it, find the process with `ps` and kill it; leave no server running.

3b. Append this section to the END of `README.md` (exact content, preceded by one blank line):

```markdown
## Run the web backend (milestone 2)

The FastAPI backend (`src/cea/api.py`, plan 012) serves the compiler and the AI agent to the web UI in `web/`.

    .venv/Scripts/python -m pip install -r requirements-dev.txt
    .venv/Scripts/python -m uvicorn cea.api:app --reload --app-dir src

It listens on `http://127.0.0.1:8000`. Endpoints: `POST /api/compile`, `/api/explain`, `/api/fix`, `/api/ask`, and `GET /api/health`; interactive docs at `http://127.0.0.1:8000/docs`. Sources above 64 KB are rejected (HTTP 413). The AI endpoints need the `CEA_LLM_*` settings described in `.env.example`; without them they answer HTTP 503 and `/api/compile` still works.
```

**Verify**:
- `grep -c "uvicorn cea.api:app --reload --app-dir src" README.md` → `1`
- `.venv/Scripts/python -m pytest -q` → `B+59 passed, 20 deselected`

Commit: `docs: how to run the FastAPI backend (plan 012 step 3)`, staging `README.md`.

### Step 4: Status row

In `plans/README.md`, "Milestone 2" table, set row 012's Status to `DONE (B+59 passed; 59 API tests)` with the real numbers. Commit `plans: 012 done`, staging `plans/README.md`.

## Test plan

- `tests/unit/test_api.py` (59 tests), listed under Step 2. Pattern: `TestClient(api.app)` per test, `app.dependency_overrides[api.get_agent]` for the agent, cleared by the `client` fixture.
- Existing `tests/unit/test_no_print.py` now also checks `api.py`.
- Final: `B+59 passed, 20 deselected`.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q tests/unit/test_api.py` → `59 passed`
- [ ] `.venv/Scripts/python -m pytest -q` → `B+59 passed, 20 deselected`
- [ ] `grep -n "print(" src/cea/api.py` → no output
- [ ] `grep -c "^fastapi==0.143.0$\|^uvicorn==0.54.0$" requirements.txt` → `2`; `grep -c "^httpx==0.28.1$" requirements-dev.txt` → `1`; `grep -c "^filterwarnings = " pyproject.toml` → `1`
- [ ] Step 3 smoke run printed the health and compile JSON; no server left running
- [ ] `git diff --name-only main..HEAD` lists exactly: `README.md`, `plans/README.md`, `pyproject.toml`, `requirements-dev.txt`, `requirements.txt`, `src/cea/api.py`, `tests/unit/test_api.py`
- [ ] `plans/README.md` row 012 updated

## STOP conditions

Stop and report (do not improvise) if:
- Any drift check fails, especially check 5 (the 010/011 names or shapes differ from the contract).
- `pip install` cannot get the pinned versions (no network, or a version is yanked). Do not pick other versions yourself; report the error.
- `test_real_agent_over_fake_llm` fails (the agent does not fall back on invalid model output as contract §2 requires), or any test fails twice with your files identical to this plan.
- Making a test pass seems to need a change to `agent.py`, `llm/`, `pipeline.py` or any compiler module.
- You find yourself passing the request's filename, or anything other than the record, the source and the mode/question, to the agent.
- Anything would require reading `tests/corpus/heldout/`, or writing a real key anywhere.

## Maintenance notes

- Plan 013 (React UI) consumes exactly these JSON shapes. Changing a field name here breaks `web/src/types.ts`.
- When F8 (milestone 4) verifies fixes, `/api/fix` already passes `verified` through from `FixSuggestion`; the UI shows "Verified" only when it is `true`.
- The server is stateless: a `record_id` is meaningful only with the same `source`. If the UI ever sends an edited source with an old id, it gets 404 or a different record. Plan 013 always sends the source it compiled.
- `_env_agent` is cached for the process lifetime. Changing `CEA_LLM_*` or `.env` needs a server restart (`--reload` restarts only on code changes). `/api/health` re-reads the configuration on every call, so it can show a new setting before the agent uses it.
- If a later Starlette changes the warning text, the `filterwarnings` line stops matching and pytest shows the warning again (harmless). Moving to `httpx2` later means swapping the dev pin and deleting that line.
- A reviewer should check: no exception text reaches a response body or the log; `extra="ignore"` on every request model; the 413 check happens before `compile_source`.
- Deferred: rate limiting, auth. Neither is needed for a local demo.

## Open questions (advisor → owner)

1. **Extra fields: ignore or reject?** The plan ignores them (works with any client, provably never forwarded). Rejecting with 422 (`extra="forbid"`) is a one-word change if preferred.

## Viva notes (ask the executor to report)

End your report with a **Viva notes** list covering at least: why the server is stateless and re-compiles per request (no session store, record ids are deterministic for a given source); how privacy is enforced (fixed display name, extra fields dropped, tests prove the filename never reaches the agent or the LLM messages); why the agent is a FastAPI dependency (tests inject `FakeLLM`, no network); the error mapping (404/413/422/502/503) and why exception text is never returned; why health reports configuration (through plan 010's `client_from_env`: `.env` plus environment) rather than pinging the model; the explanation cache; the CORS choice; why `httpx` plus one targeted `filterwarnings` line instead of `httpx2`; the real test counts.
