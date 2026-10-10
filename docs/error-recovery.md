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

The parser is a recursive-descent parser over the grammar in `docs/language-spec.md` section 2. It has three recovery tools, used in this order of preference: phrase-level repair (§4.2, §4.3, §4.7: record the error, pretend the missing token was there, carry on), panic mode (§4.4: record the error, skip tokens up to a sync point), and the uncertain region (§4.5: the bookkeeping that lets later errors point back at the earlier one).

### 4.1 Expected sets

The `expected` field, and the syntax-code selection rules in the catalog, use the token or token class that the failing `expect(...)` call required at that point (for example `[";"]` after a complete declarator). They do not use the full set of tokens that could legally follow. Without this, SYN-MISSING-SEMICOLON (selection rule 2: "the expected set is exactly `;`") could never be selected after a declarator, because `,` and `=` could also follow.

The bracket stack used by selection rule 3 ("the found token is a closing bracket with no matching opener") contains only opening brackets **consumed by successful matches**. Brackets skipped during panic mode are never pushed.

### 4.2 Phrase-level repair: missing semicolon

> In `expect(";")`, if the current token is not `;`, is not EOF, and its start line is greater than the end line of the previous consumed token, then: record SYN-MISSING-SEMICOLON at the position immediately after the previous token (`line` = previous token's end line, `column` = previous token's end column + 1), with `found` = the current token's text and `expected = [";"]`. Consume nothing, return as if `;` had been matched, and do not enter panic mode or open an uncertain region.

When the found token is on the **same** line, the code is still SYN-MISSING-SEMICOLON (selection rule 2) at the same "after the previous token" location, but recovery is panic mode (§4.4). When the found token is EOF, the code is SYN-UNEXPECTED-EOF (selection rule 1 comes first) and the EOF rule of §4.4 applies.

The repair is applied at every `;` site of the grammar, including the two `;` inside a `for` header.

### 4.3 Missing `)` before `{`

Decision (missing ')' before '{'): YES — a `{` can never occur inside an expression in this subset, so the missing `)` is provable from the token alone and inserting it keeps the `if`/`while`/`for` node with its condition and body.

The case is `if (cond {`, `while (cond {` or a `for` header ending `… {`. The parser has consumed the header's `(` and a complete expression, then `expect(")")` finds `{`. The code is SYN-UNBALANCED-BRACKET (selection rule 3: the expected set is exactly `)`), reported at the found `{` by the location convention, so the insertion choice changes neither the code nor the location. Because `{` never starts or continues an expression, the insertion point is unambiguous, unlike the `;` rule, which depends on line layout. With YES, the statement node is kept with its condition and its body: a `break` in the body stays inside a loop, and reads in the condition still count as reads. With NO, panic mode would stop before `{` without consuming it, the statement would become an `ErrorStmt`, and the `{ … }` that follows would be parsed as a separate orphan block. A `break` in it would then produce SEM-BREAK-OUTSIDE-LOOP (linked by R7), and the reads in the condition would be lost (R6 would have to link any resulting WRN-UNUSED-VAR). Trace T7 in §9 shows the YES behaviour and, in its narrative, what NO would have produced.

The rule, in the same pattern as §4.2:

> In `expect(")")`, if the current token is `{` and the required `)` is the one that closes the header of an `if`, `while` or `for` statement, then: record SYN-UNBALANCED-BRACKET at the `{` (`line` and `column` of the found token), with `found = "{"` and `expected = [")"]`. The message names the `(` that opened the header and its line. Consume nothing, return as if `)` had been matched, and do not enter panic mode or open an uncertain region.

### 4.4 Panic mode and sync sets

```text
SYNC_STMT_CONSUME = { ";" }   -- skip up to and including the first ";"
SYNC_STMT_STOP    = { "}", "if", "while", "for", "return", "break", "continue", "{", "int", "float", "double", "char", "void", EOF }   -- stop BEFORE these; do not consume
SYNC_FOR_HEADER   = inside a for header: ";" is NOT a sync token; consume the ")" that closes the header; stop before SYNC_STMT_STOP
SYNC_BLOCK        = { "}" }   -- the block loop ends at "}" (consumed by the block's own expect) or EOF; panic never consumes "}"
SYNC_TOP_STOP     = a type keyword that is the first token on its line AND the depth of "{"/"}" skipped so far in this panic is 0; or EOF   -- stop before; do not consume
```

**Mechanism.** Errors other than phrase repair raise an internal `ParseError(error_id)` after the record is created. Catch points:

- (a) `statement()`: every statement, innermost first. It catches, runs statement-level panic (or for-header panic if the error occurred between `for (` and the header's `)`), and returns an `ErrorStmt`. One exception: if the statement is a `var_decl` and its first declarator's `IDENT` has already been consumed, it returns the `VarDecl` instead, marked as a broken declaration (§5).
- (b) The declarator initializer `= expression` and the `array_suffix` expression in `var_decl` and `global_decl` (CP-INIT, CP-SIZE). These catch, replace the expression with an `ErrorExpr`, run panic (statement-level for locals, top-level for globals), and return the declaration node, which still declares its name (see §5).
- (c) `top_decl()`: it catches and runs top-level panic. It returns an `ErrorStmt` at top level (`kind_hint = "top"`).

**Statement-level panic.** Look at the current token. If it is in `SYNC_STMT_STOP`, stop. If it is `;`, consume it and stop. Otherwise consume it (skip) and repeat. When panic stops without having consumed a `;`, the `ErrorStmt` records `stopped_before` = the text of the token it stopped at.

**For-header panic.** Used when the error occurred after the `(` of a `for` and before the `)` that closes its header. Keep a parenthesis depth `d` = 1 + the number of `(` opened by successful matches inside the header and not yet closed. Skip tokens; `(` adds 1 to `d`, `)` subtracts 1. When `d` reaches 0, consume that `)` and stop; the next token (normally the start of the body) is then recorded as `stopped_before`. Stop earlier, before the token and without consuming it, if the current token is in `SYNC_STMT_STOP`. A `;` is just skipped.

**Top-level panic.** Skip tokens, tracking `{` (+1) and `}` (−1) among skipped tokens; the depth never goes below 0, so a stray `}` does not block synchronisation. Stop before a `SYNC_TOP_STOP` token. "First token on its line" means no other token starts earlier on the same line. The brace-depth condition stops the sync from landing on an indented `int x;` inside a function body that is being skipped.

**EOF.** Panic always stops at EOF. A block whose loop ends at EOF calls `expect("}")`, which records SYN-UNEXPECTED-EOF (`expected = ["}"]`, at the EOF position) and then **returns the block normally** without raising. This keeps the enclosing function intact. Each still-open block records its own SYN-UNEXPECTED-EOF. The 2nd and later ones are linked by rule R2, because the first EOF error opens the uncertain region.

**Errors inside the header of a function definition** (the parameter list) are caught by `top_decl()`.

### 4.5 Uncertain region

> The parser keeps `recovering: error_id | None`. **Opened** when panic mode starts for error E (any level), or when an EOF error is recorded. If it is already open, its owner does not change. **Not opened** by phrase repair (§4.2, §4.7, and §4.3 if YES). **Closed** when (i) statement-level panic consumes a `;`, (ii) top-level panic stops at a SYNC_TOP_STOP type keyword, or (iii) any `;` or `}` is consumed by a successful match. While it is open, every new syntax error gets `caused_by = recovering` (rule R2).

Why: after panic stops before a token without consuming a terminator, the parser's position in the grammar is a guess until the next terminator is matched. So an error raised before then is known to come from parsing under that guess.

The value of `recovering` at the moment a syntax record is created is exactly what rule R2 copies into `caused_by`. Lexical and semantic records never read it.

Known limitation: a for-header panic that ends by consuming the header's `)` does not close the region by (i), (ii) or (iii), so the region stays open until the first `;` or `}` is matched in the loop body. An independent error in that first body statement is then over-linked. This is accepted for now and should be measured on the corpus (ADR 0002, "Still open").

### 4.6 Progress guarantee

1. Statement-level panic consumes at least the found token unless that token is in `SYNC_STMT_STOP`. Then: `}` ends the block loop (the block consumes it), EOF ends every loop, and every other stop token is the first token of a production that consumes it immediately.
2. Phrase repair consumes nothing. But every `expect(";")` follows at least one token already consumed by the same statement. The table lists every `;` of the syntax grammar:

| Site | Production | Token(s) consumed before the ";" |
|---|---|---|
| S1 | `function_def` (prototype) | the type, the function name, `(`, the parameters and `)`: at least the already-consumed `type_spec` and `IDENT` |
| S2 | `global_decl` | at least one declarator, so at least its `IDENT` |
| S3 | `var_decl` | the `type_spec` and at least one declarator (its `IDENT`) |
| S4 | `for_stmt` (first) | `for`, `(` and the optional `for_init` |
| S5 | `for_stmt` (second) | `for`, `(`, the optional `for_init`, the first `;` and the optional condition |
| S6 | `return_stmt` | `return` and the optional expression |
| S7 | `break_stmt` | `break` |
| S8 | `continue_stmt` | `continue` |
| S9 | `expr_stmt` | a complete expression, at least one token (an expression that cannot start raises a ParseError instead) |
| S10 | `empty_stmt` | none, and none is needed: the `;` is matched only when it is present, so it cannot fail |

3. **Loop guard (safety net).** The block's statement loop and the program's `top_decl` loop record the token index before each iteration. If an iteration consumed nothing, they skip one token. In test mode they also raise an assertion, because by points 1–2 this must never happen. None of the traces in §9 triggers it.
4. Conclusion: every loop iteration consumes at least one token or exits, so the parser terminates. At most one panic error is recorded per `statement()`/`top_decl()` call, plus phrase repairs, plus one SYN-UNEXPECTED-EOF per open block.
5. The §4.7 repair consumes nothing, but it exits every open block and returns to the top-level loop. The top-level loop then consumes the type keyword as the start of `top_decl`, so progress holds.

### 4.7 Phrase-level repair: missing `}`

> In `statement()`, before any other alternative: if the current token is a type keyword, the next token is `IDENT`, and the token after that is `(`, then record SYN-UNBALANCED-BRACKET at the type keyword, with `found` = the type keyword's text and `expected = ["}"]`. The message names the innermost open `{` and its line. Every open block of the current function is then closed without consuming anything. Each `Block` node is ended at the previous token and gets `closed_by_repair = <this error id>`. Control returns to the top-level `top_decl` loop. Only ONE record is created, however many blocks were open. No uncertain region is opened.

Why this is safe and useful: in the subset, `type IDENT (` cannot start a statement, because there are no nested functions and no local prototypes. A local declarator is `IDENT [ "[" … "]" ] [ "=" … ]`, so it can never be followed directly by `(`. The rule therefore never fires on valid code, and it detects the missing `}` at the earliest point it becomes provable. Without it, the next function header would be mis-parsed as a local declaration, producing a misleading SYN-MISSING-SEMICOLON root, and the real cause would surface only at EOF as a second root.

Limitation: a missing `}` in the **last** function is still detected only at EOF (SYN-UNEXPECTED-EOF, §4.4).

Implementation note: the repair is raised as an internal `BlockRepair(error_id)` exception that is *not* a `ParseError`, so the `statement()` catch point does not handle it. Every production between the statement and the function body lets it propagate. Each `block()` on the way catches it, ends itself at the previous token, sets `closed_by_repair`, and re-raises. `function_def` catches it after its body block and returns the function node normally. If an uncertain region is already open when the repair fires (panic stopped just before the type keyword), the new record is linked to that region by R2 and the region stays open until §4.5 closes it.


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
