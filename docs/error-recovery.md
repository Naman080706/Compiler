# Error Recovery Specification

This document says what the compiler does after its first error, how every later error is recorded, and how a record can point at the earlier record that caused it. It builds on `docs/language-spec.md` (grammar and semantic rules) and `docs/error-catalog.md` (the 37 error codes and the rules for choosing among syntax codes). It adds no error codes. The reasoning behind the main choices is in `docs/decisions/0002-error-recovery-and-cascade-linking.md`.

The parser does not exist yet. Milestone 1 implements this document, so the rules below are written to be coded from directly.

## 1. Goals and invariants

1. Every phase always runs. The lexer reads the whole file. The parser always produces a complete `Program` AST, possibly containing error nodes. The semantic analyser always runs on that AST, even when earlier phases recorded errors.
2. Every detected error produces exactly one record. Nothing is suppressed. Cascades are linked through `caused_by`, never dropped.
3. `caused_by` is set only by the rules in §7. Each rule names a mechanical condition the compiler can check, not a guess.
4. The parser terminates on every input (see §4, "Progress guarantee").
5. Records are deterministic. The same source always yields the same records, in the same order, with the same ids.
6. Record ids are `E-0001`, `E-0002`, … in creation order. The lexer runs to completion before parsing starts, so all lexical records come first, then syntax records, then semantic records. Display order (by line, then column) is a UI concern. It does not change ids.

## 2. Error record schema additions

The PRD error record has the fields `id`, `phase`, `code`, `severity`, `line`, `column`, `found`, `expected`, `snippet`, `root_id` and `rule_ref`. This design adds exactly four fields:

| Field | Type | Meaning |
|---|---|---|
| language | string | Always `"c"` (plan 001 / ADR 0001). Lets a future adapter add a language without changing the AI layer. |
| caused_by | string or null | Id of the record that caused this one, set only by a §7 rule; null otherwise. |
| span_end | object `{line, column}` | Inclusive end of the source text the record is about (see §8). Equal to `(line, column)` for zero-width errors (SYN-MISSING-SEMICOLON and EOF errors). |
| message | string | The catalog's message template for `code`, with placeholders filled from the record. PRD F1 lists it, but the PRD schema table omits it. |

All PRD fields are kept unchanged. `root_id` is assigned by F2 (milestone 2), not by the compiler phases. Until F2 exists, the interceptor sets `root_id = id`. The `found` field for the EOF token is the string `EOF`.

## 3. Lexer recovery

The rule: **record the error, skip the bad input, continue; never pass an error token to the parser.**

| Code | Reported at (first bad character) | Bad input skipped | Token emitted | Sets `lex_gap` on next token |
|---|---|---|---|---|
| LEX-INVALID-CHAR | the character | that one character | none | yes |
| LEX-UNTERMINATED-STRING | the opening `"` | from `"` up to (not including) the end-of-line character | none | yes |
| LEX-BAD-CHAR-LITERAL | the opening `'` | unclosed on its line: up to end of line; closed but empty or more than one character (`''`, `'ab'`): through the closing `'` | none | yes |
| LEX-UNTERMINATED-COMMENT | the `/` of `/*` | everything up to EOF | none | yes (the EOF token) |
| LEX-MALFORMED-NUMBER | the first character of the number | the maximal run of `[A-Za-z0-9_.]` that starts at the number (`12abc`, `1.2.3`, `12.`) | none | yes |
| LEX-INVALID-ESCAPE | the `\` | the two-character escape only. In a STRING_LIT the rest of the literal is lexed normally and the token is emitted with the escape removed from its value. In a CHAR_LIT the whole literal is skipped (a char literal without its one character is not a token). | STRING_LIT: the literal; CHAR_LIT: none | STRING_LIT: no; CHAR_LIT: yes |
| LEX-UNSUPPORTED-DIRECTIVE | the `#` | the rest of the line | none | no (valid directives produce no token either, so the token stream is unchanged) |

Notes on the table:

- "First bad character" means the first character of the rejected lexeme (for `12abc`, the `1`). For a single bad character, that is the character itself. This interpretation was confirmed by the advisor and agrees with plan 003.
- `lex_gap` is a field on every token: the id of the **last** lexical record whose skipped input lies between the end of the previous token and the start of this token, or `None`. It is how the parser learns, mechanically, that a token is missing in front of it (rule R1 in §7).
- Why the STRING_LIT case still emits a token: the bad input is the escape alone. Removing it leaves a well-formed literal. No later phase reads string contents (format specifiers are not checked, `sem.builtins`), so this is not an error token.
- A string with both an invalid escape and no closing quote records both errors (escape first, by position). Neither has `caused_by`. Lexical records never have `caused_by`.
- Progress: each lexer step consumes at least one character, so the lexer always terminates.

## 4. Parser recovery

TODO (plan 002 step 3)

## 5. Error AST nodes

TODO (plan 002 step 4)

## 6. Semantic analysis on a partial AST

TODO (plan 002 step 4)

## 7. caused_by rules

TODO (plan 002 step 4)

## 8. Locations

TODO (plan 002 step 4)

## 9. Traced examples

TODO (plan 002 step 5)

## 10. F2 feasibility

TODO (plan 002 step 6)

## 11. Interface for later milestones

TODO (plan 002 step 6)
