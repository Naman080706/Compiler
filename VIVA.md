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

All 37 error codes live in one catalog (`docs/error-catalog.md`). Each code fixes the error's phase, severity, category and `rule_ref`. Severity comes from the catalog and never from the AI (PRD F4). A small script (`tools/check_spec.py`) fails if any code cites a rule that isn't in the language spec. That is how we guarantee the AI can't cite a rule that doesn't exist. The spec, the catalog and the checker now exist (plan 001). We tested the checker by deliberately breaking the catalog twice (a misspelt rule name, a wrong severity), and it caught both. The AI-citation part is **(planned)** for F7.

### 1.6a Where we differ from gcc (on purpose)

- **Stricter than gcc:** `return 5;` in a `void` function and `return;` in an `int` function are errors here, where gcc only warns. Beginners should fix these, not ignore them.
- **Reported earlier than gcc:** a missing `main` is reported at the end of semantic analysis. Real C only finds it at link time, and we have no linker.
- **Extra teaching warning:** WRN-UNREACHABLE-CODE (code after `return`/`break`/`continue`) is a warning gcc doesn't give.
- **Same as gcc:** float→int narrowing (`-Wfloat-conversion`), a missing return in a non-void function (`-Wreturn-type`) and `if (x = 5)` (`-Wparentheses`) are warnings in both.
- **Evidence:** the spec's example program was compiled with `gcc -std=c99 -Wall -Wconversion`. It gave 0 errors and exactly the 1 warning our spec predicts.

### 1.7 Build order: the PRD's 5 milestones, all 9 features, no cuts

We follow the PRD's five milestones: 1 Foundation (F1, F4), 2 Intelligence (F2, F3), 3 Extensions (F5, F6, F7), 4 Novelty (F8, F9) and 5 Evaluation. All nine features are built. The PRD's fallback cut order (F9, then F6, then F5) is not used.

There is one deliberate change in order. The PRD puts the faulty-program test corpus in milestone 5, but we build it **before** milestone 1. Each milestone then has automatic pass/fail tests from day one: for example, F1's "one lexical, one syntax, one semantic error → three records" and F2's "missing semicolon → 1 root cause". Measuring the final metrics and writing the report stay in milestone 5.

### 1.8 Error recovery: record everything, link the cascades (designed in `docs/error-recovery.md`; implementation planned)

- **Missing `;` is repaired, not panicked over.** If the next token starts on a new line, the parser reports SYN-MISSING-SEMICOLON just after the statement and continues as if the `;` were there. Nothing is skipped, so no cascade arises.
- **Missing `}` is repaired too.** `int main(` inside a function body can only mean an earlier `}` is missing (C has no nested functions). We report one error there and parse the next function normally.
- **Otherwise panic mode** with explicit synchronisation points: `;` for statements, `}` for blocks, and a type keyword at the start of a line for top-level declarations. A progress proof guarantees the parser can't loop forever.
- **Semantic analysis always runs, even after syntax errors.** It works on a partial syntax tree with error nodes. That's how one file can show a lexical, a syntax and a semantic error at once (the PRD F1 acceptance test).
- **We never hide errors; we link them.** Each error may carry `caused_by` (the error that caused it), set only by 8 mechanical rules such as "this operand failed to parse". The raw count is every error; the displayed count is the root causes. This is what F2's "70% fewer displayed errors" measures.
- **The poison `<error>` type.** An expression that failed to parse has type `<error>`, which passes type checks silently. We can't type-check something we couldn't parse, so no error is hidden, because none was detected.
- **Missing `)` before `{` is repaired too** (`while (i < 10 {`). A `{` can never appear inside an expression, so the missing `)` is certain. Repairing it keeps the loop intact, so a `break` inside it isn't wrongly reported as "outside a loop".
- **Lexical errors are linked to the syntax errors they cause.** In `int x = 5 @ 2;` the lexer drops the `@`. The parser then sees `5 2` and reports a missing `;`, but that error is linked to the `@` error, so the student is shown the real cause.
- **Every rule was checked by hand on 8 example programs** (missing `;` on a new line and on the same line, missing `}`, missing `(`, an undeclared variable used 5 times, a bad character, the F1 three-error file, missing `)`), listing every error, its position and its link.
- **An honest finding about the PRD.** F2's acceptance test ("one missing semicolon that previously produced 10+ errors shows 1 root") can't be met as written. Our recovery turns a missing `;` into exactly 1 error, so there is no cascade to collapse. We refused to add a "naive mode" just to create fake cascades. Instead we proposed corrected wording, measured on a fixed set of genuinely cascading files **(PRD update pending)**.
- **The 70% target is at risk, and we say so.** On our five hand-traced cascading examples, clustering cuts 13 raw errors to 5 displayed, a 62% reduction. Good recovery leaves fewer cascades to collapse, so the PRD target may be miscalibrated. The real number will be measured on the 20 held-out programs in milestone 5.

### 1.9 The test corpus (plan 003, built)

- **Test programs (built):** 85 C programs. 53 dev programs cover every one of the 37 error codes, plus cascading and multi-fault cases; 12 are valid; and **20 are held out** for the final metrics. Each is realistic student code (bank balance, GPA calculator, power, factorial tables).
- **The cascade set was derived, not guessed.** Each program's expected errors were hand-traced through our recovery rules, and a file counts as "cascading" only if one fault gives 2 or more raw errors (15 dev, 8 held-out). Our first guesses were wrong for 17 files. For example, a missing `;` we'd assumed gave 10+ errors gives exactly 1 under our repair rule.
- **The tests found design gaps before any code was written.** Tracing showed that an unsupported pointer declaration loses the variable's name (so later uses look undeclared), and that `break` inside an unsupported `switch` isn't linked to the `switch` error. Both fixes are scheduled for milestone 1.
- **Held-out discipline:** the 20 held-out programs are never looked at while tuning the parser or clustering. Bugs they reveal are reproduced as new dev programs. This prevents overfitting our own evaluation.
- **Expected results:** each program has a JSON sidecar listing the root causes F2 should show (code + line), not raw error counts. Raw counts depend on recovery details, so we don't predict them.
- **gcc as an independent check:** `gcc -std=c99 -pedantic-errors -fsyntax-only` runs on every program. Any program we expect to accept must also be accepted by gcc ("accepted => valid C99"). Whether gcc rejects each faulty program is recorded by actually running it, never guessed. Result: gcc rejects 59 of 85 programs and accepts 26. The 26 are all valid programs, warning-only programs, or cases where our subset is deliberately stricter than C99 (a variable-length array, a missing `main`, `const`, pointers, `switch`, `<math.h>`). There are 0 mismatches.

### 1.10 Compiler structure (milestone 1 complete)

```
source.c --> lexer.py --> parser.py --> semantic.py --> list of ErrorRecord
                |             |              |
                +-------------+--------------+--> ErrorSink (diagnostics.py): the single error interceptor
                                                   ids, severity from catalog, snippet, message
```

- **One interceptor (PRD F1).** Every phase reports errors only through `ErrorSink.report()`. No module except the command-line front end is allowed to `print`, and a test enforces this by scanning the source.
- **Severity comes from the catalog, never the AI (PRD F4).** `ErrorSink` looks up each code in `docs/error-catalog.md`, so the compiler cannot report a severity that isn't in the documented table.
- **Built so far (plan 005):** the error record, the catalog loader, the `ErrorSink` interceptor and the full lexer, covered by 262 unit tests (358 in the whole suite). The lexer gives the right result on every lexical dev program and gives zero errors on all 12 valid programs, with both Unix (LF) and Windows (CRLF) line endings.
- **Lexer details an examiner may probe:** maximal munch (`a+++b` becomes `++` then `+`); `\r\n`, `\n` and a lone `\r` each count as one newline; a tab counts as one column; a malformed number like `12abc`, `0x1F` or `1e5` is one error covering the whole run, not several; `#include <stdio.h> // comment` is accepted, while any other header is LEX-UNSUPPORTED-DIRECTIVE.
- **The interceptor validates every report:** an unknown code, a 0-based position or a grammar-rule name not in the spec is rejected before an id is used. So a bug in the compiler can't produce a malformed record.
- **Error messages read naturally** because quoting depends on the phase: syntax messages quote tokens ("Expected ';'"), while semantic messages show types and counts raw ("'add' expects 2 argument(s) but got 1").
- **Parser built (plan 006):** a recursive-descent parser with one method per grammar rule, about 880 lines, plus 233 tests (591 in the whole suite). Each method is tagged with its grammar-rule name, so every syntax error automatically records *which rule* was being parsed (`rule_ref`). That is what the AI layer will later look up in the spec.
- **All three recovery layers work as designed.** The phrase repairs fix a missing `;` (next token on a new line), a missing `)` before `{` and a missing `}` (a function header inside a function). Panic mode handles everything else. Broken declarations stay in the tree, so later uses aren't falsely "undeclared". All 9 parser-level hand traces reproduce exactly, and every dev program's syntax errors match its notes.
- **Robustness evidence:** every valid test program was re-parsed with each single token deleted in turn. That is 1,146 broken programs, with 0 crashes and 0 infinite loops, and at most 2 errors per broken program. A safety-net loop guard fails the tests if it ever fires; it never has.
- **Known limitation found in review:** an *extra* `}` gets the right error code but a confusing message, because the catalog has one template for both missing and extra closers. It will be fixed in the catalog before the AI layer reads messages.
- **Milestone 1 complete (plan 007):** the semantic analyser (all 16 rules, one source-order pass, which C99's declare-before-use allows), `compile_source()` and `python -m cea file.c [--json]`. The suite is 858 tests. All 10 hand traces are reproduced exactly, and all 54 dev and 12 valid programs give their expected errors. PRD F1 is met (the T6 file gives 3 records: lexical, syntax, semantic) and so is F4 (a warnings-only file compiles, with summary "0 fatal, 1 warning"). The exit code is 1 on any fatal error and 0 otherwise.
- **The spec was corrected during this step:** a block returns on every path if *any* statement in it does, so `return 1; f();` gives only an unreachable-code warning, not a false missing-return warning too.
- **Standard library only.** The compiler has no third-party dependencies, so it runs anywhere Python 3.11+ runs.
- **A fixed interface contract** (`plans/m1-architecture.md`) defines every module, record field and syntax-tree node before any code is written. The lexer, parser and analyser were planned in parallel and must fit together. The contract is what guarantees they do.
- **Spec gaps were fixed before coding (plan 004, done).** Result: a held-out `switch` program went from 5 displayed root causes to 1. Hand-tracing the test programs found four gaps. Two were real design problems: one unsupported `switch` or pointer showed up as several unrelated "root causes". New rule R9 and an extended R7 now link those cascades. A `switch` example (trace T8) and a pointer example (trace T9) were added as exact-match tests.
- **Held-out discipline in practice.** The `switch` gap was first seen in a held-out program. We did not tune against that file. We reproduced the problem in a new dev program (`dev/052`) and designed the fix against it.

---

### 1.11 Milestone 4: verified fixes (F8) and the personalised model (F9)

- **F8 (src/cea/verifier.py):** the agent's patch is applied to a copy of the source string and fully re-compiled. Verified = the original error (matched by code and rule_ref near its location after mapping lines through the difflib diff) is gone, no new fatal error appears, and the guardrails hold (within 3 lines of the error, at most 6 changed lines, no loss of identifiers or statements, no commenting out). Up to 3 attempts, each retry sees why the last one failed, 10 s overall budget. The API, UI and CLI show a fix only when verified; otherwise: "No verified fix found; see explanation".
- **Honest metric:** tools/metrics_f8.py default (oracle FakeLLM) tests the pipeline only; 43 of 48 fixable dev roots verify. The 5 misses are guardrail rejections of non-local fixes (a prototype far away, renaming `main`) or fixes that replace a variable by a literal. Real numbers need a real LLM (`--llm env`).
- **F9 (src/cea/profile.py):** SQLite file `.cea_data/profiles.sqlite3` (git-ignored), keyed by a random browser-made id; counts per catalog category, each root once per compile, an error signature (no line number) once per session. Three or more hits: beginner explanation plus a worked example from the fix-patterns corpus; else terse (expert style). The Beginner/Expert toggle overrides; Auto defers to the profile. The id never reaches the LLM (tested).

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

**Q: Is your compiler exactly as strict as gcc?**
No, and that's deliberate (1.6a). It is stricter on bad `return` statements, reports a missing `main` without a linker, and adds an unreachable-code warning. It never accepts a program gcc rejects.

**Q: How do you know the spec and the error list agree?**
`tools/check_spec.py` checks all 37 codes against the spec (phase, severity, category, and that each rule exists). We proved it works by deliberately introducing two mistakes; it caught both.

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

**Q: What happens after a syntax error? Doesn't one mistake produce lots of errors?**
Two common mistakes, a missing `;` and a missing `}`, are repaired on the spot, so they produce one error. Other errors use panic mode: skip to the next `;`, `}` or declaration start. Any follow-on errors are kept but linked to their cause with `caused_by`, and the UI shows only the root (1.8).

**Q: Why not just suppress follow-on errors like many compilers do?**
Suppression hides information and makes the "fewer displayed errors" metric impossible to measure honestly. We record every error and link the cascades, so the raw count and the displayed count are both real numbers.

**Q: Your PRD says one missing semicolon gives 10+ errors. Does it in your compiler?**
No. Our recovery repairs it, giving exactly 1 error. We report that the PRD's test, as worded, is trivially true and so can't demonstrate clustering. We proposed measuring on genuinely cascading files instead, such as an undeclared variable used 5 times or a lexical error inside an expression (1.8).

**Q: Can your parser loop forever on bad input?**
No. The design includes a progress proof: every recovery step consumes at least one token or leaves the loop, checked for all 10 places a `;` can appear in the grammar. There is also a safety-net guard that fails loudly in tests if it ever fires.

**Q: Do you reach the PRD's 70% error-reduction target?**
Our hand traces give 62%. Better recovery leaves fewer cascades to collapse, so we report the real number and proposed measuring on a fixed set of cascading files (1.8).

**Q: How is the compiler organised, and how do you know the parts fit together?**
Lexer, then parser, then semantic analyser, all reporting through one error interceptor (1.10). The module interfaces, record fields and syntax-tree nodes were fixed in a written contract before coding, and exact-match tests on hand-traced examples check the whole chain.

**Q: What did you do when a test program exposed a flaw in your design?**
We fixed the design document first (plan 004), added a hand-traced example that reproduces the flaw as a permanent test, and only then planned the code. When the flaw came from a held-out program, we reproduced it in a new dev program instead of tuning against the held-out file.

**Q: How do you guarantee the "no phase prints to the console" requirement?**
A unit test scans every compiler source file and fails if any module except `cli.py` contains `print(` or writes to `sys.stdout`/`sys.stderr`. So the requirement is enforced automatically, not just promised.

**Q: How do you know your parser never crashes or loops forever on bad input?**
Two kinds of evidence. First, a written progress argument: every recovery step consumes a token or leaves the loop. Second, a test that deletes each token of every valid program in turn and parses the result: 1,146 broken programs, 0 crashes, 0 loop-guard trips. The guard itself is a safety net that makes tests fail if it ever fires.

**Q: Why does each syntax error carry a grammar-rule name?**
Each parser method is tagged with its EBNF rule, so an error records the innermost rule being parsed (for example `while_stmt` or `var_decl`). The AI layer uses that name to fetch the exact rule text from the spec, which is how explanations stay grounded in a real rule.

**Q: How do you avoid overfitting to your test set?**
The 20 evaluation programs are held out and never used while designing recovery or clustering (1.9).

**Q: Some of your "faulty" programs compile with gcc. Isn't that a contradiction?**
No. Our subset is deliberately stricter than C99. A variable-length array, `const`, pointers and `switch` are valid C that we choose not to support, and a missing `main` is only a link-time error in real C. The rule we enforce is one-directional: every program *we* accept must compile with gcc (1.9).

**Q: How did you decide which test files count as "cascading"?**
By hand-tracing each program through our recovery rules before the compiler existed, not by guessing. A file is cascading only if one fault produces 2 or more raw errors. This corrected 17 initial guesses (1.9).

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
- **Literal forms are limited:** hex (`0x1F`), octal-style, exponent (`1e3`) and suffixed (`1.0f`, `10L`) literals are not part of the subset. They are reported as malformed numbers.
- **No runtime errors:** division by zero or out-of-range array indexes at runtime are out of scope, as the PRD says.
- **No uninitialised-variable warning or `printf` format checking** in the first version. These were deferred.
- **Over-linking after a broken `for` header:** after such an error, the next statement in the loop body may be wrongly linked to it. This is documented and will be measured on the corpus.
- **A missing `}` in the last function** is detected only at end of file, not where the brace was forgotten.
- **Clustering is heuristic:** unusual cascades may be missed. Misses are logged and new rules added.
- **The user study is small:** 5–10 classmates, so the result is indicative, not statistically strong.

---

## 4. Changelog

| Date | Added | Source |
|---|---|---|
| 2026-10-10 | Sections 1.1–1.6, Q&A, limitations | PRD review; plan 001 (C subset, error catalog); decision to support one language only |
| 2026-10-10 | Section 1.7 (5 milestones, no cuts, corpus first) + Q&A | Owner decision: build all 9 features |
| 2026-10-10 | 1.6 updated, 1.6a (differences from gcc), 2 Q&A, literal-form limitation | Plan 001 executed and reviewed |
| 2026-10-10 | 1.8 (error recovery), 1.9 (test corpus), 4 Q&A | Plans 002 and 003 drafted and cross-reviewed |
| 2026-10-10 | 1.8 expanded (missing `)` repair, lex links, 8 traces, 62% finding), 2 limitations, 2 Q&A | Plan 002 executed and reviewed |
| 2026-10-10 | 1.9 updated (85 programs built, traced cascade set, design gaps found, gcc 59/26), 2 Q&A | Plan 003 executed, revised and reviewed |
| 2026-10-10 | 1.10 (compiler structure, interface contract, plan 004 gap fixes, held-out discipline), 2 Q&A | Milestone 1 planning started |
| 2026-10-10 | Plan 004 executed: switch cascade 5 roots -> 1 (heldout/020), traces T8/T9 exact | Plan 004 reviewed and merged |
| 2026-10-10 | 1.10 updated (foundation + lexer built, lexer details, validation, message quoting), no-print Q&A | Plan 005 executed, reviewed and merged |
| 2026-10-10 | 1.10 updated (parser built, recovery layers, robustness evidence, stray-`}` message limitation), 2 Q&A | Plan 006 executed, reviewed and merged |
| 2026-10-10 | 1.10: milestone 1 complete (analyser, pipeline, CLI, F1/F4 met, return-path fix) | Plan 007 executed, reviewed and merged |
| 2026-10-11 | 1.11 (milestone 4: F8 verifier, F9 profile) | Implemented from the PRD, no plan |
