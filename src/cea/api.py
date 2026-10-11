"""FastAPI backend for the web UI (plan 012, plans/m2-architecture.md section 3).

Endpoints (all JSON):
    POST /api/compile  {source}                      -> {ok, summary, records, clusters}
    POST /api/explain  {source, record_id, mode, verbosity} -> Explanation (with citations)
    POST /api/fix      {source, record_id}           -> {diff, patched_source, verified}
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
MAX_HISTORY_TURNS = 50                # request-size bound; the agent itself keeps only the last few
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
    verbosity: Literal["beginner", "expert"] = "beginner"


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
    exp = _call_agent(agent.explain, record, req.source, req.mode, req.verbosity)
    return {"text": exp.text, "rule_ref": exp.rule_ref, "cited_rule": exp.cited_rule, "mode": exp.mode,
            "verbosity": exp.verbosity, "citations": list(exp.citations)}


@app.post("/api/fix")
def fix_endpoint(req: FixRequest, agent: AgentDep) -> dict:
    record = _record(_compile(req.source), req.record_id)
    fix = _call_agent(agent.suggest_fix, record, req.source)
    return {"diff": fix.diff, "patched_source": fix.patched_source, "verified": bool(fix.verified)}


@app.post("/api/ask")
def ask_endpoint(req: AskRequest, agent: AgentDep) -> dict:
    record = _record(_compile(req.source), req.record_id)
    history = [t.model_dump() for t in req.history]
    answer = _call_agent(agent.ask, record, req.source, req.question, history)
    return {"text": answer.text, "refused": bool(answer.refused)}


@app.get("/api/health")
def health_endpoint() -> dict:
    return {"status": "ok", "llm": llm_status()}
