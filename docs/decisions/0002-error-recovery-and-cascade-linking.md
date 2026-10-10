# ADR 0002: Error recovery and cascade linking

## Status

Accepted, 2026-10-10. Depends on ADR 0001 (single source language, a C99 subset).

## Context

The product is a compiler error assistant. Three of its features constrain what the compiler does after its first error:

- F1 needs every phase to run and to report through one interceptor. Its acceptance test is a file with one lexical, one syntax and one semantic error that yields three records. A parser that stops at the first error cannot pass it.
- F2 needs a mechanical signal for "this error was caused by that one". Guessing causes from message text would make the grouping unreliable and untestable.
- F8 compares the error list before and after a proposed patch, so the records must be deterministic.

The PRD risk table names the approach: "Start with panic-mode recovery points (statement and block ends); log misses and add rules". Plan 001 fixed the grammar, the 37 error codes and the rules for choosing among syntax codes, and deferred this decision. The full specification is `docs/error-recovery.md`.

## Decision

1. **Lexer recovery** (`docs/error-recovery.md` §3): record the error, skip the bad input, continue. The bad input is the bad character, the rest of the line for an unterminated string or char literal, or everything up to EOF for an unterminated comment. An error token is never passed to the parser. The next token carries a `lex_gap` pointer to the lexical record.
2. **Phrase-level repair for a missing `;`** (§4.2): when `;` is expected and the found token starts on a later line than the previous token, record SYN-MISSING-SEMICOLON and continue as if `;` were present, consuming nothing. Decided by the executor (not the advisor): the same virtual insertion applies to a missing `)` directly before `{` in an `if`, `while` or `for` header (§4.3, decision YES), because `{` cannot occur inside an expression in this subset, so the insertion is unambiguous and the statement keeps its condition and body.
3. **Location convention** (§8): SYN-MISSING-SEMICOLON is reported immediately after the last token of the unterminated statement. Every other syntax error is at the found token. Lexical errors are at the first bad character. Semantic errors are at the offending identifier or operator. This is shared with plan 003.
4. **Panic mode with explicit sync sets** (§4.4 to §4.6): statement level skips to `;` (consumed) or stops before `}` or a statement-start token. Block level ends at `}`. Top level stops at a type keyword at the start of a line, outside skipped braces. The parser provably terminates, and a loop guard backs the proof.
5. **Error AST nodes** (§5, §6): `ErrorStmt` and `ErrorExpr` keep their source span. A declaration with a broken initializer still declares its name with its declared type. Semantic analysis always runs on the partial AST. Operands of type `<error>` absorb type checks.
6. **Record, never hide; link instead** (§1, §7): cascade errors are never suppressed. A record may carry `caused_by`, set only by rules R1 to R8, each a mechanical condition. F2 uses `caused_by` plus the PRD rules to assign `root_id`. Raw count is all records; displayed count is the number of roots.
7. **Record schema additions** (§2): exactly four fields are added to the PRD schema: `language`, `caused_by`, `span_end` and `message`.
8. **Honest feasibility** (§10): no "naive mode" that disables recovery to manufacture cascades. The PRD's F2 acceptance test is therefore reworded rather than staged.
9. **Phrase-level repair for a missing `}`** (§4.7): the subset has no nested functions, so `type IDENT (` at the start of a statement proves that a `}` is missing. One SYN-UNBALANCED-BRACKET is recorded at the type keyword, all open blocks of the function are closed without consuming anything, and no uncertain region is opened.

## Consequences

- A missing `;` gives few raw errors (1 in T1, 2 in T1b), so the F2 acceptance wording in the PRD must change (`docs/error-recovery.md` §10).
- A missing `}` is caught at the next function header by the §4.7 repair: one root (T2). A missing `}` in the last function is still reported only at EOF.
- The raw count is post-recovery and is not comparable to gcc's count.
- Undeclared names produce one record per use, unlike gcc, which reports once per function. F2 groups them, not `caused_by`.
- The `lex_gap` pointer and the error nodes make the parser slightly larger, but every link is checkable by a test: each trace in §9 becomes an exact-match pytest case.
- Plan 003 (the test corpus) must use the location convention and §8.

## Still open

- (1) Whether F2 should also group errors after a missing `}` in the last function (detected only at EOF).
- (2) The PRD F2 acceptance wording and the 70% metric (§10).
- (3) None for locations: EOF, SEM-MISSING-MAIN and "first character of the rejected lexeme" were confirmed by the advisor and agree with plan 003.
- (4) Precision of R4 and R6: they may link a warning that a correct parse would also have produced. Measure it on the corpus. The same measurement should cover the for-header region over-linking noted in §4.5.
- (5) Whether the `<error>` type should absorb type checks (§6) or record linked errors.

The owner should add the corrected F2 acceptance wording to the PRD (see `docs/error-recovery.md` §10).
