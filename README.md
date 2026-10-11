# Compiler Error Assistant

An AI-assisted error layer for a course compiler. It compiles one language, a **subset of C**, and the compiler is written in **Python**. The system captures every compiler error with structured metadata and groups cascading errors under one root cause. It explains each error in plain language and proposes a fix that is **re-compiled and checked before the student sees it**.

> **Status:** design stage. The PRD (`cd project prd.docx`) is complete. The language specification and error catalog are planned in `plans/001-define-c-subset-and-error-catalog.md`. No compiler code exists yet.

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

**Design rule: every program our compiler accepts is also valid C99.** We may reject valid C (features we didn't implement), but we never accept code that real C would reject.

| Supported | Not supported (clear "not supported" error) |
|---|---|
| `int`, `char`, `float`, `double`, `void` | pointers (`*`, `&`, `->`) |
| global and local variables, `int a, b = 2;` | `struct`, `union`, `enum`, `typedef` |
| 1-D arrays with literal size | array initialiser lists, array parameters |
| functions, prototypes, recursion | `switch`, `do-while`, `goto` |
| `if/else`, `while`, `for`, `break`, `continue` | `long`, `unsigned`, `const`, `static`, … |
| `+ - * / %`, comparisons, `&& \|\| !` | bitwise operators, `?:`, `sizeof` |
| `= += -= *= /= %=`, `++`, `--` | preprocessor except `#include <stdio.h>` |
| `printf` (after `#include <stdio.h>`) | `scanf` (needs pointers) |

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

## 6. Repository layout (planned)

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

It listens on `http://127.0.0.1:8000`. Endpoints: `POST /api/compile`, `/api/explain`, `/api/fix`, `/api/ask`, and `GET /api/health`; interactive docs at `http://127.0.0.1:8000/docs`. Sources above 64 KB are rejected (HTTP 413). The AI endpoints need the `CEA_LLM_*` settings described in `.env.example`; without them they answer HTTP 503 and `/api/compile` still works.

## Run the web UI (milestone 2)

The React + Monaco UI lives in `web/` (plan 013). Start the backend first (previous section), then `cd web && npm install && npm run dev` and open `http://localhost:5173`. See `web/README.md`, "How to run the demo".
