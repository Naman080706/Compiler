"""FastAPI backend for the web UI (plan 012, plans/m2-architecture.md section 3).

Endpoints (all JSON):
    POST /api/compile  {source, student_id?, session_id?} -> {ok, summary, records, clusters}
    POST /api/explain  {source, record_id, mode, verbosity?, student_id?} -> Explanation (with citations)
    POST /api/fix      {source, record_id}           -> {diff, patched_source, verified, attempts, reason}
                                                        (F8: a diff only when verified; otherwise diff is "")
    GET    /api/profile/{id}/analytics?days=30       -> per-student compile analytics (daily series, totals, streak)
    GET    /api/profile/{id}                         -> the student's error-category counts (F9)
    DELETE /api/profile/{id}                         -> reset (delete) that profile
    POST /api/ask      {source, record_id, question, history} -> {text, refused}
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
import os
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Literal, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from cea.agent import Agent
from cea.llm import ExplanationCache, FallbackClient, client_from_env
from cea.pipeline import CompileResult, compile_source
from cea.profile import STUDENT_ID_RE, ProfileStore, category_of, choose_depth
from cea.records import ErrorRecord
from cea.verifier import DEFAULT_TIMEOUT, verify_fix

MAX_SOURCE_BYTES = 64 * 1024          # contract section 3: "The source is size-limited (64 KB)"
MAX_QUESTION_CHARS = 1000
MAX_HISTORY_TURNS = 50                # request-size bound; the agent itself keeps only the last few
DEV_ORIGIN = "http://localhost:5173"  # the Vite dev server; the only CORS origin allowed
DISPLAY_NAME = "input.c"              # the client's filename is never accepted

logger = logging.getLogger("cea.api")
T = TypeVar("T")

app = FastAPI(title="Compiler Error Assistant API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[DEV_ORIGIN], allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Content-Type"])


ID_PATTERN = STUDENT_ID_RE.pattern


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")      # filename, student name, ... are dropped here
    source: str
    # F9: pseudonymous random tokens made by the browser. Only the profile store sees them, never the LLM.
    student_id: str | None = Field(default=None, pattern=ID_PATTERN)
    session_id: str | None = Field(default=None, pattern=ID_PATTERN)
    # "auto": our compiler, with the gcc fallback for features outside the course subset; "cea"/"gcc" force one
    engine: Literal["auto", "cea", "gcc"] = "auto"


class FixRequest(CompileRequest):
    record_id: str


class ExplainRequest(FixRequest):
    mode: Literal["short", "expand"] = "short"
    # None = automatic (F9 with a student_id, else "beginner"); an explicit F5 choice always wins
    verbosity: Literal["beginner", "expert"] | None = None


class HistoryTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    answer: str = Field(max_length=4000)


class AskRequest(FixRequest):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    # the client's thread for this one error; the agent uses only the last MAX_HISTORY turns
    history: list[HistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


@lru_cache(maxsize=1)
def _env_agent() -> Agent:
    """The production agent, built once from plan 010's configuration, with the on-disk explanation cache."""
    return Agent(client_from_env(), cache=ExplanationCache())


@lru_cache(maxsize=1)
def _env_profiles() -> ProfileStore:
    return ProfileStore()


def get_profiles() -> ProfileStore:
    """FastAPI dependency: the F9 profile store (tests override it with a temp-file store)."""
    return _env_profiles()


def fix_timeout() -> float:
    """Overall F8 time budget in seconds: CEA_FIX_TIMEOUT (environment, then .env), default 10.

    Local models need more: each attempt can take 6-10 s, so set e.g. CEA_FIX_TIMEOUT=60 for Ollama.
    """
    from cea.llm.config import DEFAULT_ENV_FILE, read_env_file
    raw = os.environ.get("CEA_FIX_TIMEOUT")
    if raw is None:
        raw = read_env_file(DEFAULT_ENV_FILE).get("CEA_FIX_TIMEOUT", DEFAULT_TIMEOUT) if DEFAULT_ENV_FILE.exists() else DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


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


def _compile(source: str, engine: str = "auto") -> CompileResult:
    """Re-compile the request's source (stateless server); 413 above 64 KB of UTF-8."""
    if len(source.encode("utf-8", errors="surrogatepass")) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail=f"Source is larger than {MAX_SOURCE_BYTES} bytes.")
    return compile_source(source, DISPLAY_NAME, engine=engine)


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
ProfilesDep = Annotated[ProfileStore, Depends(get_profiles)]


def _profile_id(student_id: str) -> str:
    if not STUDENT_ID_RE.fullmatch(student_id):
        raise HTTPException(status_code=422, detail="Invalid student id.")
    return student_id


@app.post("/api/compile")
def compile_endpoint(req: CompileRequest, profiles: ProfilesDep) -> dict:
    result = _compile(req.source, req.engine)
    if req.student_id:
        roots = [c.root for c in result.clusters]
        profiles.record_compile(req.student_id, req.session_id, roots)
        profiles.record_event(req.student_id, result.errors, roots, result.engine)
    return {"ok": result.ok, "summary": result.summary(), "engine": result.engine,
            "engine_note": result.engine_note,
            "records": [r.to_dict() for r in result.errors],
            "clusters": [{"root_id": c.root.id, "symptom_ids": [s.id for s in c.symptoms]}
                         for c in result.clusters]}


@app.post("/api/explain")
def explain_endpoint(req: ExplainRequest, agent: AgentDep, profiles: ProfilesDep) -> dict:
    record = _record(_compile(req.source, req.engine), req.record_id)
    personal = None
    if req.student_id:                     # F9: the id picks the depth here and goes no further
        category = category_of(record)
        hits = profiles.hits(req.student_id, category)
        verbosity, example = choose_depth(req.verbosity, hits)
        personal = {"category": category, "hits": hits, "depth": "full" if example else "terse",
                    "override": req.verbosity is not None}
    else:
        verbosity, example = req.verbosity or "beginner", False
    args = (record, req.source, req.mode, verbosity) + ((True,) if example else ())
    exp = _call_agent(agent.explain, *args)
    out = {"text": exp.text, "rule_ref": exp.rule_ref, "cited_rule": exp.cited_rule, "mode": exp.mode,
           "verbosity": exp.verbosity, "citations": list(exp.citations)}
    if personal is not None:
        out["personalised"] = personal
    return out


@app.post("/api/fix")
def fix_endpoint(req: FixRequest, agent: AgentDep) -> dict:
    record = _record(_compile(req.source, req.engine), req.record_id)
    fix = _call_agent(lambda: verify_fix(agent, record, req.source, timeout=fix_timeout(),
                                         compile_fn=lambda s, n: compile_source(s, n, engine=req.engine)))
    if not fix.verified:                   # F8: an unverified fix is never sent as a fix
        return {"diff": "", "patched_source": req.source, "verified": False, "attempts": fix.attempts,
                "reason": fix.reason}
    return {"diff": fix.diff, "patched_source": fix.patched_source, "verified": True, "attempts": fix.attempts,
            "reason": fix.reason}


@app.post("/api/ask")
def ask_endpoint(req: AskRequest, agent: AgentDep) -> dict:
    record = _record(_compile(req.source, req.engine), req.record_id)
    history = [t.model_dump() for t in req.history]
    answer = _call_agent(agent.ask, record, req.source, req.question, history)
    return {"text": answer.text, "refused": bool(answer.refused)}


@app.get("/api/profile/{student_id}")
def profile_endpoint(student_id: str, profiles: ProfilesDep) -> dict:
    return profiles.view(_profile_id(student_id))


@app.get("/api/profile/{student_id}/analytics")
def analytics_endpoint(student_id: str, profiles: ProfilesDep, days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict:
    return profiles.analytics(_profile_id(student_id), days)


@app.delete("/api/profile/{student_id}")
def profile_reset_endpoint(student_id: str, profiles: ProfilesDep) -> dict:
    profiles.reset(_profile_id(student_id))
    return profiles.view(student_id)


@app.get("/api/health")
def health_endpoint() -> dict:
    from cea.gcc_fallback import gcc_available
    return {"status": "ok", "llm": llm_status(), "gcc": gcc_available()}
