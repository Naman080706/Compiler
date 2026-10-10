# 0001: Single source language, a C99 subset implemented in Python

## Status

Accepted, 2026-10-10.

## Context

PRD open question 1 asked which source language the compiler should accept and which language to implement it in. The PRD's non-goals require one course language only ("No support for multiple source languages; one course language only") and exactly three phases: lexical, syntax and semantic. Optimisation, code generation quality and runtime errors are out of scope.

## Decision

- The only source language is a C99 subset, specified in `docs/language-spec.md`.
- Every program the compiler accepts is also valid C99. The subset may reject valid C, but it never accepts what real C rejects. This allows later cross-checking against `gcc -std=c99 -fsyntax-only`.
- The implementation language is Python 3.11 or newer, with a hand-written lexer and a recursive-descent parser.
- Error codes use the prefixes `LEX-`, `SYN-`, `SEM-` and `WRN-`. They are listed in `docs/error-catalog.md`, and `tools/check_spec.py` keeps the spec and the catalog consistent.

## Consequences

Reasons for supporting a single language:

- Clustering (F2) depends on controlling parser recovery, which needs our own parser.
- Per-phase capture (F1) needs our own phases, so the compiler must expose lexical, syntax and semantic stages separately.
- The RAG corpus (F7) must be small and complete to guarantee correct citations; one language keeps every `rule_ref` backed by a spec entry.
- The fix verifier (F8) re-runs our own pipeline on the proposed fix.
- The scope fits a single semester.

The error record will carry a `language` field fixed to `"c"`. A future adapter for another compiler could then add a language without changing the AI layer, but that is not planned.

Unsupported C features (pointers, structs, switch, and so on) are rejected with SYN-UNSUPPORTED-FEATURE, so students get a clear message rather than a confusing cascade.

## Still open

- PRD open questions 2–5.
- The error-recovery strategy after syntax errors (sync points, semantic analysis on a partial AST), which is planned separately.

The owner should mark PRD open question 1 as resolved and link this ADR.
