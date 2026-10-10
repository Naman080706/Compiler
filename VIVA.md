# Viva Preparation — Compiler Error Assistant

This document collects everything useful for the viva: the design decisions and the reasons behind them, likely questions with answers, and honest limitations. For what the project *is*, see `README.md`.

> **How this file is maintained:** it is updated whenever a planning or implementation step makes a decision an examiner might ask about. Each addition is logged in the changelog at the end. Statements are marked **(planned)** until they are implemented and tested. Never claim a planned feature as done.

---

## 1. Key design decisions

### 1.1 Why a subset of C?

C's error behaviour is exactly what the project is about. Missing semicolons, unbalanced braces, undeclared variables and type mismatches cascade badly in C, and C is the language most students meet first in systems courses.

**Design rule: every program our compiler accepts is also valid C99.** We may reject valid C (features we didn't implement), but we never accept code that real C would reject. This lets us cross-check our compiler against `gcc -std=c99 -fsyntax-only` **(planned)**.

We use a *subset* because full C includes pointers, structs, the preprocessor and many type modifiers. Each one adds grammar, semantic rules and error codes. The subset covers the constructs where beginner errors actually occur. Anything outside it gets a clear "not supported in this course's C subset" message rather than a confusing syntax error.

### 1.2 Where "MiniC" came from, and why we moved to a C subset

**Why MiniC was made.** The PRD said "one course language only" but never named the language (PRD open question 1). Nothing could be designed without one: no grammar, error codes, clustering rules, RAG corpus or test programs. The PRD's own examples pointed to a small C-like language with types: a missing `;` causing 15 errors, `found }`, `expected ;, )`, type mismatches. So the first design was **MiniC**, a deliberately tiny, invented C-like teaching language. It had a handful of types, basic statements and functions, and a short grammar. The aim was to keep the grammar, error catalog and test corpus small enough for one semester.

**Why we replaced it.** MiniC was *C-like*, not C. It had a `bool` and a `string` type and a `print` statement, none of which exist in C. That causes three problems:
- Students typing real C (`printf`, `i++`, `int main(void)`) would get errors for valid code.
- An examiner could fairly ask "is this C or not?"
- We couldn't cross-check our compiler against a real one.

So we kept MiniC's idea, **a small, controlled language**, but made it a strict subset of C99.

> In short, MiniC answered "which language?" when the PRD didn't say. The C subset keeps MiniC's small size but makes the language real C. MiniC is not part of the implementation.

### 1.3 Why only one language is supported

This is a deliberate design decision, not a missing feature. The PRD lists multi-language support as a **non-goal**. There are five reasons.

1. **Clustering needs control of the parser.** F2 groups cascading errors by knowing *where the parser recovered*: statement ends, block ends. We can only know that for a parser we wrote. With gcc or javac we'd be guessing from their text output.
2. **Per-phase capture needs our own phases.** F1 tags each error as lexical, syntax or semantic. Production compilers like gcc, javac and CPython don't reliably expose which phase an error came from.
3. **RAG grounding must be small and complete.** F7 promises that every explanation cites a rule that really exists. Our whole grammar and every semantic rule fit in one specification, so each error's `rule_ref` points to a known rule. The full C, C++, Java and Python specifications would be enormous, and we couldn't guarantee correct citations.
4. **The verified-fix claim depends on our own pipeline.** F8 re-runs the patched code through our lexer, parser and analyser, so "the error is gone and no new fatal error appeared" has an exact meaning. Other compilers report and recover differently, and Python finds most mistakes only at runtime, which is out of scope.
5. **Scope.** Each extra language needs its own lexer, parser, semantic rules, error codes, test corpus and RAG corpus. Depth on one language demonstrates the idea better than shallow support for many.

**Is the design extensible?** Yes. The AI layer depends only on the error record, never on compiler internals. Each record carries a `language` field, fixed to `"c"` **(planned)**. An adapter that converts another compiler's diagnostics into the same record format could add a language without changing the AI layer. That is future work.

### 1.4 Why Python for the compiler?

The backend (FastAPI), the RAG stack (Chroma, sentence-transformers) and the LLM client are all Python. Writing the compiler in the same language means the fix verifier can re-run the compiler in-process on a copy of the code, with no separate service. Performance doesn't matter for small student programs.

### 1.5 Why a hand-written recursive-descent parser?

It gives full control over where errors are detected and how the parser recovers, and recovery is the basis of clustering. Each grammar rule is one function, so a syntax error can report exactly which rule (`rule_ref`) was being parsed. Generated parsers (Yacc, PLY, Lark) hide recovery behind generic mechanisms and give worse error locations.

### 1.6 Why a fixed error catalog?

All 37 error codes live in one catalog (`docs/error-catalog.md`). Each code fixes the error's phase, severity, category and `rule_ref`. Severity comes from the catalog and never from the AI (PRD F4). A small script (`tools/check_spec.py`) fails if any code cites a rule that isn't in the language spec. That is how we guarantee the AI can't cite a rule that doesn't exist **(planned)**.

### 1.7 Build order: the PRD's 5 milestones, all 9 features, no cuts

We follow the PRD's five milestones: 1 Foundation (F1, F4), 2 Intelligence (F2, F3), 3 Extensions (F5, F6, F7), 4 Novelty (F8, F9) and 5 Evaluation. All nine features are built. The PRD's fallback cut order (F9, then F6, then F5) is not used.

There is one deliberate change in order. The PRD puts the faulty-program test corpus in milestone 5, but we build it **before** milestone 1. Each milestone then has automatic pass/fail tests from day one: for example, F1's "one lexical, one syntax, one semantic error → three records" and F2's "missing semicolon → 1 root cause". Measuring the final metrics and writing the report stay in milestone 5.

---

## 2. Likely viva questions

**Q: Why build your own compiler instead of using gcc?**
The project's novelty needs data gcc doesn't expose: per-phase errors, parser recovery points for clustering, and a rule name for each error to ground the AI. Building the front end ourselves is also the compiler-design part of the course.

**Q: Why only a subset of C, not full C?**
See 1.1. The subset covers the constructs where beginners make mistakes. Unsupported features get a clear "not supported" message.

**Q: Why didn't you just invent your own small language?**
We did at first: MiniC (1.2). We dropped it because invented features like `bool`, `string` and `print` would reject the real C students write. A strict C99 subset is just as small but is real C, and gcc can cross-check it.

**Q: Could this support Java or Python?**
Not in this project (1.3). The AI layer is language-agnostic because it only reads error records, so a future adapter could add a language.

**Q: What are the phases of your compiler?**
Lexical analysis turns characters into tokens. Syntax analysis turns tokens into a parse tree, using a recursive-descent parser. Semantic analysis then checks scopes and types, and handles declarations, function signatures and return paths. Code generation and optimisation are out of scope. We produce diagnostics only.

**Q: Why a hand-written parser instead of Lex/Yacc?**
See 1.5. It gives control over error recovery and exact `rule_ref`s.

**Q: How does clustering work?**
It is rule-based. Errors that follow a syntax error inside the same statement or block are treated as consequences of it. Every later use of an undeclared variable is grouped under its first use. Each error record gets a `root_id`, and the UI shows the root with a collapsed count of the errors under it.

**Q: How do you stop the AI from giving wrong explanations or fixes?**
There are three safeguards. (1) Severity and error facts come from the compiler, never the AI. (2) RAG makes every explanation cite a real rule from our spec. (3) No fix is shown unless the verifier has re-compiled it successfully. After 3 failed attempts we show only an explanation.

**Q: Does "verified" mean the fix is correct?**
No. It means the fix **compiles** and removes the original error. To block trivial "fixes", such as deleting the offending line, we plan to limit patch size and require the patch to touch the error's location **(planned; being added to the PRD)**. A patch that compiles may still not be what the student intended.

**Q: What about student privacy?**
Student IDs and personal data are never sent to the LLM, only the error context. Profiles (F9) are stored locally under a pseudonymous ID, and students can view and reset them. Code snippets do go to the LLM provider. For the user study we will tell participants this, or use the local Ollama model.

**Q: Your PRD puts evaluation last. Why did you build the test programs first?**
So every milestone could be checked automatically against the PRD's acceptance tests as it was built, instead of discovering problems at the end. The same programs later serve as the evaluation set (1.7).

**Q: How will you evaluate it?**
On a folder of faulty C programs with known injected faults, which also serves as the pytest suite. Targets:
- ≥ 70% fewer displayed errors on cascading files.
- ≥ 85% root-cause accuracy.
- ≥ 80% of fixes verified within 3 attempts.
- ≥ 90% of explanations citing a real rule.
- Default explanation in under 5 s.
- A small user study comparing time-to-fix with and without the assistant.

---

## 3. Honest limitations (say these before the examiner does)

- **"Verified" means the fix compiles, not that it's correct** (see Q above).
- **Only a C subset:** no pointers, structs, `switch` or most of the preprocessor.
- **No runtime errors:** division by zero or out-of-range array indexes at runtime are out of scope, as the PRD says.
- **No uninitialised-variable warning or `printf` format checking** in the first version. These were deferred.
- **Clustering is heuristic:** unusual cascades may be missed. Misses are logged and new rules added.
- **The user study is small:** 5–10 classmates, so the result is indicative, not statistically strong.

---

## 4. Changelog

| Date | Added | Source |
|---|---|---|
| 2026-10-10 | Sections 1.1–1.6, Q&A, limitations | PRD review; plan 001 (C subset, error catalog); decision to support one language only |
| 2026-10-10 | Section 1.7 (5 milestones, no cuts, corpus first) + Q&A | Owner decision: build all 9 features |
