# Compiler Error Assistant

An AI-assisted error layer for a course compiler. It compiles one language, a **subset of C**, and the compiler is written in **Python**. The system captures every compiler error with structured metadata and groups cascading errors under one root cause. It explains each error in plain language and proposes a fix that is **re-compiled and checked before the student sees it**.

> **Status:** built. All five milestones are complete — the compiler, the AI error layer (F1–F9) and the web UI are implemented and tested (**1529 backend + 83 web tests** passing). The own compiler covers course-level C, with a gcc fallback for anything outside that subset, so every valid C99 program still compiles and runs. The web UI adds an in-browser editor, program execution and several compiler-internals tools (see §7).

---

## 1. The problem

Compiler errors are written for compiler authors, not learners. One missing `;` can produce a dozen cascading messages, and a beginner cannot tell which one matters. Our system turns that wall of errors into **one root cause, one short explanation and one fix that we've checked actually compiles**.

## 2. What it does (9 features, 3 tiers)

| # | Feature | Tier | What it means |
|---|---|---|---|
| F1 | Phase-wise error capture | Core | Lexer, parser and semantic analyser report structured records (phase, code, line, column, found, expected, snippet) through one interceptor. No phase prints directly. |
| F2 | Error clustering | Core | Cascading errors are grouped under the first error that caused them. Example: one missing `;` that produced 10+ errors is shown as 1 root cause. |
| F3 | Compiler-scoped AI agent | Core | Explains each root error in at most two sentences, with "Expand" and "Suggest fix" actions. Refuses questions unrelated to the compiler. |
| F4 | Severity tagging | Core | Each error is *fatal* or *warning*. The compiler assigns this from a fixed catalog, never the AI. |
| F5 | Verbosity toggle | Extension | Beginner mode (plain language, analogy) or expert mode (one line plus the rule). Same facts, different depth. |
| F6 | Follow-up Q&A per error | Extension | A small chat thread attached to each error. |
| F7 | RAG grounding | Extension | Every explanation cites the actual grammar or semantic rule it is based on. |
| F8 | Self-verifying fix engine | Novelty | The AI's patch is applied to a private copy and re-compiled. It is shown only if the original error is gone and no new fatal error appears. It gets at most 3 attempts. |
| F9 | Personalised error model | Novelty | Tracks which error categories a student repeats and gives fuller explanations for those categories. |

## 3. Architecture

```
 source.c
    │
    ▼
 Lexer ──► Parser ──► Semantic analyser        (our compiler, Python)
    │         │              │
    └─────────┴──────┬───────┘
                     ▼
              Error interceptor  ──► Error store (structured records)
                     ▼
              Clustering (root_id)  ──► Severity tagger (from catalog)
                     ▼
              Context builder  ◄── student profile (F9), verbosity (F5)
                     ▼
              RAG retriever (F7): looks up rule text by rule_ref
                     ▼
              AI agent (F3/F6): explanation or candidate patch
                     ▼
              Fix verifier (F8): re-runs the lexer, parser and analyser on a copy
                     ▼
              UI: root errors · severity · explanation · verified diff · chat
```

The AI layer **only reads** the structured error records. It never sees compiler internals and never edits the student's file.

**Tech stack:**
- Compiler and backend: Python (hand-written lexer and recursive-descent parser), FastAPI.
- Front end: React with the Monaco editor and a diff viewer.
- LLM: Gemini API, with Ollama as a local fallback, through an OpenAI-compatible client.
- RAG and storage: Chroma vector store and SQLite. Diffs use Python `difflib`.
- Tests: pytest.

## 4. The language: a subset of C

We chose C because its error behaviour is exactly what the project is about. Missing semicolons, unbalanced braces, undeclared variables and type mismatches cascade badly in C, and C is the language most students meet first in systems courses.

**Design rule: every program our compiler accepts is also valid C99.** We never accept code that real C would reject. When a program uses a feature outside our own front end's subset, it is handed to a **gcc fallback** so it still compiles and runs — the own compiler is where the structured phase-wise diagnostics (F1–F9) come from.

Our own front end covers **course-level C**: the base types, global and local variables, 1-D and 2-D arrays with initialiser lists, functions / prototypes / recursion, the full control flow (`if/else`, `while`, `for`, `do-while`, `switch`, `break`, `continue`, `return`), pointers (`*`, `&`, `->`), `struct` / `union` / `enum` / `typedef`, casts, `sizeof`, the ternary and bitwise operators, and `#include`. Anything beyond that (for example `goto` or the wider preprocessor) is compiled by the gcc fallback, labelled as such in the UI.

The error catalog has **37 error codes** across the three phases: 7 lexical, 8 syntax, 17 semantic errors and 5 warnings. They are grouped into 10 categories such as *missing-semicolon*, *undeclared-identifier* and *type-mismatch*.

Only this one language is supported. Supporting several languages is a non-goal in the PRD.

## 5. How we measure success

| Metric | Target |
|---|---|
| Fewer displayed errors on cascading files (clustering) | ≥ 70% reduction |
| Root-cause accuracy | ≥ 85% |
| Fixes verified within 3 attempts | ≥ 80% |
| Explanations citing a real rule | ≥ 90%, and 0 citing a non-existent rule |
| Default explanation latency | < 5 s |
| Learner usefulness | Faster time-to-fix than raw compiler output (small user study, 5–10 classmates) |

Measured on a folder of faulty C programs with known injected faults, which doubles as the pytest suite.

## 6. Web UI features

Beyond the nine core features, the React UI makes the compiler interactive and exposes its internals — things possible only because we own the compiler:

- **In-browser editor** with multiple file tabs, open-from-disk, double-click rename, and C keyword autocomplete (Monaco).
- **Run** (`POST /api/run`) — gcc builds and executes the program and the terminal-style OUTPUT panel shows its real stdout / exit code (5 s timeout, no stdin, 64 KB output cap).
- **Correct whole program** (`POST /api/correct`) — rewrites the file so it compiles, with a list of what changed; the rewrite is re-compiled and only shown as *verified* when no fatal error remains.
- **Pipeline view** (`#/pipeline`, `POST /api/analyze`) — the token stream, parse tree and symbol table for the current program, with a **live phase animation** (tokens → tree → symbols), a **collapsible SVG AST diagram**, and **token↔source highlighting** (click a token to light up the text it came from).
- **Lab** (`#/lab`) — three AST tools: **Format** (`/api/format`, pretty-prints the program by unparsing our AST), **Constant folding** (`/api/fold`, pre-computes constant sub-expressions like `2 * 60 * 60 → 7200`), and **Structural diff** (`/api/astdiff`, diffs two parse trees so reformatting and comments don't count).
- **Practice** (`#/practice`) — buggy drills ordered by the student's most-missed error categories.
- **Predictive hint** — a pre-compile banner combining the student's top repeated category (F9) with a live brace/paren balance check.
- **Profile** (`#/profile`) — the F9 error-category model plus per-student compile analytics.

## 7. Repository layout

```
cd project prd.docx          product requirements
README.md                    this file (project overview)
VIVA.md                      viva preparation: design decisions, Q&A, limitations
docs/language-spec.md        C subset: tokens, grammar, types, semantic rules
docs/error-catalog.md        37 error codes: phase, severity, category, rule_ref
docs/decisions/              design decisions (ADRs)
tools/check_spec.py          checks that catalog and spec agree
plans/                       implementation plans and status
```

## Run the web backend (milestone 2)

The FastAPI backend (`src/cea/api.py`, plan 012) serves the compiler and the AI agent to the web UI in `web/`.

    .venv/Scripts/python -m pip install -r requirements-dev.txt
    .venv/Scripts/python -m uvicorn cea.api:app --reload --app-dir src

It listens on `http://127.0.0.1:8000`. Endpoints: `POST /api/compile`, `/api/explain`, `/api/fix`, `/api/correct`, `/api/ask`, `/api/run`, `/api/analyze`, `/api/format`, `/api/fold`, `/api/astdiff`, `GET /api/profile/{id}` (+ `/analytics`), and `GET /api/health`; interactive docs at `http://127.0.0.1:8000/docs`. Sources above 64 KB are rejected (HTTP 413). The AI endpoints need the `CEA_LLM_*` settings described in `.env.example`; without them they answer HTTP 503 and `/api/compile` still works. The Vite dev server proxies `/api` to this backend (override the target with `CEA_API_URL`).

## Run the web UI (milestone 2)

The React + Monaco UI lives in `web/` (plan 013). Start the backend first (previous section), then `cd web && npm install && npm run dev` and open `http://localhost:5173`. See `web/README.md`, "How to run the demo".
