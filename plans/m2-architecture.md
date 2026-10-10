# Milestone 2 architecture contract (plans 008–013)

Written by the advisor on 2026-10-10 against `main` @ `e2899bf`. This is binding for names and interfaces, the same way `plans/m1-architecture.md` is. A plan that finds it unworkable STOPs and reports.

Milestone 2 delivers PRD F2 (error clustering) and F3 (compiler-scoped AI agent), behind a FastAPI backend and a React UI. Owner decisions (2026-10-10):
- **LLM:** Gemini free tier is the primary model and a local Ollama model is the fallback. Both go through ONE OpenAI-compatible client, so switching provider is a config change.
- **Interface:** FastAPI + React in this milestone.
- **Fixes:** "Suggest fix" diffs are shown, clearly labelled **Unverified**. Milestone 4 (F8) replaces that with verified fixes.

## 1. Plans and dependencies

| Plan | Delivers | Depends on |
|---|---|---|
| 008 | Fix the stray-closer message (catalog template + parser args) | — |
| 009 | F2 clustering `cluster.py`; exact-root corpus test; F2 metrics script | 008 |
| 010 | LLM layer `cea/llm/` (OpenAI-compatible client, config, fallback, cache, fake) | — |
| 011 | F3 agent `agent.py` + spec rule lookup `rules.py` + CLI `--explain` | 009, 010 |
| 012 | FastAPI backend `api.py` | 011 |
| 013 | React UI in `web/` | 012 |

## 2. Python modules (all under `src/cea/`)

Runtime dependencies go in a NEW `requirements.txt` (plan 010 creates it; 012 adds FastAPI). `requirements-dev.txt` gains `-r requirements.txt` plus test-only packages. The compiler core (`lexer`…`pipeline`) stays standard-library only.

```python
# cluster.py (plan 009)
def assign_roots(records: list[ErrorRecord], *, program: "A.Program | None" = None) -> None: ...   # program gives function boundaries for rule 2 (amended in review of 009)
    # sets r.root_id in place, in id order:
    #   1. caused_by set          -> root_id = root_id of caused_by
    #   2. SEM-UNDECLARED-VAR/FUNC whose name matches an earlier record with the same code in the
    #      same function body (or both at file scope) -> that record's root_id  (PRD: "an undeclared
    #      variable groups all its later uses"; "name" = record.found)
    #   3. otherwise              -> root_id = id
    # This is exactly the provisional rule of docs/error-recovery.md §7. The PRD's "same statement or
    # block" rule is applied ONLY through caused_by (R1/R2/R9); do not add block-wide merging.
def roots(records) -> list[ErrorRecord]: ...          # records with root_id == id, in (line, column) order
def cluster_view(records) -> list[Cluster]: ...
@dataclass
class Cluster:
    root: ErrorRecord
    symptoms: list[ErrorRecord]                       # same root_id, excluding the root, id order
```
`pipeline.compile_source` calls `assign_roots` last (plan 009 edits `pipeline.py` for this, a one-line change). `CompileResult` gains `clusters: list[Cluster]`.

```python
# rules.py (plan 011): deterministic lookup, no embeddings (full RAG/F7 is milestone 3)
@dataclass(frozen=True)
class RuleText:
    rule_ref: str; kind: str          # "grammar" | "lexical" | "semantic"
    text: str                         # ebnf rule line(s), or the sem.* paragraph and its C example
def rule_text(rule_ref: str) -> RuleText | None: ...   # parsed from docs/language-spec.md, cached
```

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
Environment variables, documented in `.env.example`, which is committed (`.env` itself is git-ignored):
- `CEA_LLM_BASE_URL`, `CEA_LLM_API_KEY`, `CEA_LLM_MODEL` for the primary. The Gemini OpenAI-compatible endpoint is `https://generativelanguage.googleapis.com/v1beta/openai/`.
- `CEA_LLM_FALLBACK_BASE_URL` (default `http://localhost:11434/v1`), `CEA_LLM_FALLBACK_MODEL` for Ollama.

**Never commit or log a key value.** Key-handling tests use dummy strings only.

```python
# agent.py (plan 011)
@dataclass
class Explanation:   text: str; rule_ref: str; cited_rule: str | None; mode: str   # "short" | "expand"
@dataclass
class FixSuggestion: diff: str; patched_source: str; verified: bool = False         # always False in M2
@dataclass
class Answer:        text: str; refused: bool
class Agent:
    def __init__(self, llm: LLMClient, cache: ExplanationCache | None = None): ...
    def explain(self, record, source: str, mode: str = "short") -> Explanation: ...
    def suggest_fix(self, record, source: str) -> FixSuggestion: ...       # unified diff via difflib
    def ask(self, record, source: str, question: str) -> Answer: ...       # refuses off-topic (F3)
```
Agent rules (PRD F3 and the PRD privacy note):
- The prompt context is ONLY: the error record, the snippet (or the source for fixes), the `rule_text` of `rule_ref`, and the mode. The filename, paths and any student identity are never sent.
- `short` is at most two sentences, saying what is wrong and where. `expand` is the full explanation.
- The model returns JSON validated against a schema. Invalid output gets one retry, then a deterministic fallback built from the catalog message.
- Scope guard: a cheap local keyword/heuristic pre-check refuses clearly off-topic questions without calling the LLM. The system prompt also instructs refusal.
- Explanations are cached by error signature.

## 3. Backend (plan 012): `src/cea/api.py`, FastAPI

| Method/path | Body | Returns |
|---|---|---|
| `POST /api/compile` | `{source}` | `{ok, summary, records:[record.to_dict()], clusters:[{root_id, symptom_ids}]}` |
| `POST /api/explain` | `{source, record_id, mode}` | `Explanation` as JSON |
| `POST /api/fix` | `{source, record_id}` | `{diff, patched_source, verified:false}` |
| `POST /api/ask` | `{source, record_id, question}` | `{text, refused}` |
| `GET /api/health` | — | `{status:"ok", llm:"primary"|"fallback"|"none"}` |

The source is size-limited (64 KB). The server re-compiles each request; the server is stateless. CORS is allowed for the Vite dev origin only. Run with `uvicorn cea.api:app`. Tests use FastAPI's `TestClient` with `FakeLLM` injected through a dependency override.

## 4. Frontend (plan 013): `web/`

Vite + React + TypeScript, with `@monaco-editor/react` for the editor and Monaco's `DiffEditor` for fixes. Versions are pinned in `package-lock.json`, which is committed; `node_modules/` is git-ignored.

UI features:
- Inline markers in the editor.
- An error panel showing **one root per cluster**, with a collapsed "+N related" count, a fatal/warning badge and the F4 summary line.
- Per-root **Expand** and **Suggest fix** buttons. The fix opens the diff with an **"Unverified preview"** badge.

The UI talks only to `/api/*` through the Vite dev proxy. Checks are `npm run build` and `npm test` (Vitest + React Testing Library, mocking `fetch`).

## 5. Conventions (in addition to m1 §6)

- **No network in tests.** Every test uses `FakeLLM` or a mocked `fetch`. One optional live smoke script (`tools/llm_smoke.py`) runs only when a key is present. It is never part of `pytest`.
- **No secrets in the repo.** `.env`, `.cea_cache/`, `web/node_modules/` and `web/dist/` are git-ignored, added by the plan that first creates each.
- **`print` only in `cli.py`.** The no-print test from plan 005 still applies to every new module. `api.py` returns data; the `uvicorn` server logs.
- **Held-out programs** stay untouched until milestone 5.
