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

The sketch below is documentation, not a code file. The field names are the contract.

```python
@dataclass
class Span:            # inclusive, 1-based
    start_line: int; start_col: int; end_line: int; end_col: int

@dataclass
class ErrorExpr:       # has type <error>; stands in for an expression that failed to parse
    span: Span
    error_id: str      # the syntax record that replaced it

@dataclass
class ErrorStmt:       # a statement or top-level declaration that failed and was skipped
    span: Span         # first token of the statement .. last token consumed or skipped
    error_id: str
    kind_hint: str     # 'if' 'while' 'for' 'return' 'break' 'continue' 'decl' 'expr' 'top'
    declared_names: list[tuple[str, str]]   # (name, type) for each `type_spec IDENT` consumed inside it
    idents_in_span: set[str]                # every IDENT text inside span (consumed or skipped)
    stopped_before: str | None              # token text if panic stopped without consuming, else None
```

Further node fields:

- `VarDecl`, the global declaration node and the function declaration node gain `error_id: str | None` and `idents_in_span: set[str]`. They are set when an error occurred after the name was consumed: a "broken declaration".
- `Block` gains `orphan_of: str | None`. It is set to the current `recovering` id when the block starts at a `{` where panic stopped (`stopped_before == "{"`).
- `Block` also gains `closed_by_repair: str | None`. It is set by the §4.7 missing-`}` repair.
- Tokens carry `lex_gap: str | None` (§3).

Rules:

- **Broken declaration.** Once `type_spec IDENT` of a local or global variable has been consumed, a later error never turns the declaration into an `ErrorStmt`. The node is kept, the name is declared with its declared type, a failed initializer or array size becomes an `ErrorExpr`, and remaining declarators after the error are lost (they are in the skipped span). Example: `int x = ;` declares `x : int` with initializer `ErrorExpr`.
- A **function** whose header fails (error inside `params`) becomes a top-level `ErrorStmt` with `declared_names = [(name, "function")]`. It does **not** declare the name, because its signature is unknown. Uses are linked by R5.
- `ErrorStmt` never declares names. `declared_names` exists only for linking. A `for` statement whose header failed after `for (int i` gives `declared_names = [("i","int")]`, and `i` is not declared in the enclosing scope (correct C scoping, since `i`'s scope was the `for` statement).

## 6. Semantic analysis on a partial AST

- The analyser visits every node, depth-first and left to right in source order (for an assignment, the target before the value). Semantic records are created in that order, which fixes their ids. On `ErrorStmt` it does nothing: it does not analyse the partial contents and does not declare anything. On a broken declaration it declares the name and analyses whatever parts are not `ErrorExpr`.
- **The `<error>` type.** Every `ErrorExpr` has type `<error>` carrying `cause = its error_id`. A use of an undeclared name gets type `<error>` carrying `cause = the SEM-UNDECLARED-VAR (or SEM-UNDECLARED-FUNC) record's id`. A binary or unary operation, call or index with an `<error>` operand has result type `<error>` with the cause of its first `<error>` operand.
- **Type checks absorb `<error>`.** A per-operand type requirement is satisfied by an `<error>` operand, and a pairwise compatibility check (assignment, initialisation, argument vs parameter, return value vs return type) passes if either side is `<error>`. This applies to: SEM-TYPE-MISMATCH, WRN-IMPLICIT-NARROWING, SEM-VOID-VALUE, SEM-NOT-CALLABLE, SEM-ARG-TYPE, SEM-RETURN-TYPE, SEM-NOT-ARRAY, SEM-INDEX-NOT-INT, and the arithmetic-condition requirement of `sem.conditions`. Justification: a type check on an operand of unknown type has no answer, so not reporting it does not hide an error, because none was detected. This is the only place where an `<error>` value avoids a record.
- **Shape checks still run** on `ErrorExpr` operands, because an `ErrorExpr` is visibly not the required shape. These are SEM-BAD-ARRAY-SIZE (size must be an integer literal > 0), SEM-NONCONST-GLOBAL-INIT (a global initializer must be a literal) and SEM-PRINTF-FORMAT (the first argument must be a string literal). When one fails because its operand is an `ErrorExpr`, the record gets `caused_by` by R3.
- Repeated uses of the same undeclared name each produce their own SEM-UNDECLARED-VAR record (gcc reports only once per function; we do not hide). F2's PRD rule groups them, not `caused_by`.
- For `sem.unused_declaration`, a plain `=` assignment target is a write, not a read, so a variable that is only assigned is still unused (this is what happens to `x` in trace T3 and `b` in T1b). Reads inside an `ErrorStmt` or an `ErrorExpr` are never seen by the analyser, which is what rules R4 and R6 compensate for.

## 7. caused_by rules

| Rule | Applies to | Condition (mechanical) | caused_by = |
|---|---|---|---|
| R1 lex gap | any syntax record | the found token's `lex_gap` is set and R2 does not apply | the `lex_gap` id |
| R2 uncertain region | any syntax record | `recovering` is open when the record is created | `recovering` (the region owner) |
| R3 poison operand | SEM-BAD-ARRAY-SIZE, SEM-NONCONST-GLOBAL-INIT, SEM-PRINTF-FORMAT | the operand that fails the shape check is an `ErrorExpr` | that `ErrorExpr.error_id` |
| R4 broken declaration | WRN-UNUSED-VAR | the declaration it is about has `error_id` set | that `error_id` |
| R5 lost declaration | SEM-UNDECLARED-VAR, SEM-UNDECLARED-FUNC for name n; SEM-MISSING-MAIN (n = `main`) | an earlier node (in source order) in the current function body or at file scope is an `ErrorStmt` with n in `declared_names`, or a broken declaration named n | the `error_id` of the nearest such node |
| R6 lost read | WRN-UNUSED-VAR for variable v (when R4 does not apply) | an `ErrorStmt`, `ErrorExpr` or broken declaration in v's scope, after v's declaration, has v's name in `idents_in_span` | the `error_id` of the first such node |
| R7 orphan loop body | SEM-BREAK-OUTSIDE-LOOP | the `break`/`continue` is inside (at any depth, with no real `while` or `for` node in between) a `Block` whose `orphan_of` points to an `ErrorStmt` with `kind_hint` `while` or `for` | `orphan_of` |
| R8 incomplete body | WRN-MISSING-RETURN | the function body contains an `ErrorStmt` at any depth, or the body `Block` has `closed_by_repair` set (§4.7) | the `error_id` of the first `ErrorStmt` in source order, else `closed_by_repair` |

Notes:

- Precedence: for syntax records, R2 then R1. Semantic rules don't overlap except R4 vs R6 (R4 first). If no rule applies, `caused_by = null`.
- Lexical records never get `caused_by`. R1 and R2 are the only rules that apply to syntax records. R3 to R8 apply to semantic records only.
- `caused_by` always points to an **earlier** record (smaller id), so the links form a forest with no cycles. An error detected later than its true cause can't be linked backward. This is why §4.7 detects a missing `}` early, at the next function header, instead of at EOF.
- **Provisional F2 root rule** (used only to fill `root_id` in §9; F2's own plan decides the final algorithm). `root(r) = root(caused_by(r))` if `caused_by` is set. Otherwise, if r is SEM-UNDECLARED-VAR or SEM-UNDECLARED-FUNC and an earlier record with the same code and the same name exists in the same function body (or both at file scope), `root(r)` = that record's root (the PRD rule "an undeclared variable groups all its later uses"). Otherwise `root(r) = r.id`. Displayed count = number of distinct roots. The PRD's other rule ("errors after a syntax error within the same statement or block are children of the first") is approximated here only through R1/R2. Applying it to whole blocks would wrongly merge independent errors. F2's plan must decide this.

## 8. Locations

SYN-MISSING-SEMICOLON is reported at the line and column immediately after the last token of the unterminated statement. Every other syntax error is reported at the found token. Lexical errors are reported at the first bad character. Semantic errors are reported at the offending identifier or operator.

- `column` is 1-based. A tab counts as one column. "Immediately after the last token" means that token's end line, end column + 1.
- The EOF token's position is immediately after the last token of the file (its end line, end column + 1). For an empty file it is 1:1. `found = "EOF"`.
- SEM-MISSING-MAIN has no identifier. It is reported at the EOF position. This is confirmed by the advisor; plan 003's corpus uses the line of the file's last token.
- `span_end`: lexical = last character skipped (for LEX-INVALID-ESCAPE in a string, the escape's second character); SYN-MISSING-SEMICOLON and EOF errors = same as `(line, column)`; other syntax = last character of the found token; semantic = last character of the offending identifier or operator.

## 9. Traced examples

Eight programs are traced by hand through §3 to §7. Each is a separate compilation, so ids restart at `E-0001` in each. Source lines are numbered from 1 and use four-space indentation. Columns are 1-based. After the traces come two tables: the records, and a summary. Milestone 1 turns each trace into an exact-match test.

### T1, missing `;` mid-function (newline after)

```c
int main(void) {
    int a = 1;
    int b = 2
    a = a + b;
    return a;
}
```

1. Lexer: no lexical errors, no `lex_gap` is set.
2. Parser, line 3: `int b = 2` is a `var_decl` with one declarator; the initializer is the expression `2` (ends at 3:13). The next token is `a` at 4:5, which cannot continue the expression.
3. `expect(";")` finds `a`. It is not EOF, and its start line (4) is greater than the end line of the previous token (3). §4.2 fires: E-0001 SYN-MISSING-SEMICOLON at 3:14 (end column 13 + 1), `found = a`, `expected = [";"]`. Nothing is consumed, no panic, no region (`recovering` stays empty). R2 and R1 do not apply, so `caused_by` is null.
4. Lines 4 and 5 parse normally. Semantics: `a` and `b` are both read in `a = a + b`, `a` also in `return a`. No other record.

### T1b, missing `;` with the next statement on the same line

```c
int main(void) {
    int a = 1;
    int b = 2 a = a + b;
    return a;
}
```

1. Lexer: nothing.
2. Parser, line 3: after the initializer `2` (ends 3:13) `expect(";")` finds `a` at 3:15, on the **same** line, so §4.2 does not repair. Selection rule 2 (expected set exactly `;`) gives E-0001 SYN-MISSING-SEMICOLON, still located at 3:14 by the location convention, `found = a`. `recovering` is empty and R1 does not apply (`a` has no `lex_gap`), so `caused_by` is null.
3. The error is raised as a `ParseError` and caught by `statement()`. The statement is a `var_decl` whose first `IDENT` (`b`) was consumed, so the result is a broken declaration: `VarDecl b : int` with `error_id = E-0001` and `idents_in_span = {b, a}` (§5).
4. Statement-level panic starts for E-0001 and opens the region (owner E-0001). It skips `a`, `=`, `a`, `+`, `b`, then consumes `;`. That closes the region (§4.5 (i)). Line 4 parses normally.
5. Semantics: `b` is declared (as `int`) but never read. WRN-UNUSED-VAR at `b` (3:9). The declaration has `error_id` set, so R4 gives `caused_by = E-0001`. (The only text that mentions `b` after its declaration is the skipped `a = a + b`, which is not in the AST.) `a` is read in `return a`, so there is no warning for it.

### T2, missing `}` before the end of a function

```c
int f(int a) {
    if (a > 0) {
        a = a - 1;
    return a;
}
int main(void) {
    return f(3);
}
```

1. Lexer: nothing.
2. Parser: `f`'s body block opens at 1:14. The `if` opens a second block at 2:16. `a = a - 1;` and `return a;` are matched inside it. The `}` on line 5 closes the `if` block. The parser is still inside `f`'s body.
3. The block loop of `f`'s body calls `statement()` with the current token `int` (6:1). §4.7 is checked first: `int`, then `main` (IDENT), then `(`. It fires: E-0001 SYN-UNBALANCED-BRACKET at 6:1, `found = int`, `expected = ["}"]`. The message names the innermost open `{`, which is the `{` on line 1 (the `if` block is already closed). `f`'s body is closed with `closed_by_repair = E-0001`; nothing is consumed and no region is opened. `recovering` is empty and `lex_gap` is not set, so `caused_by` is null.
4. The top-level loop parses `int main(void) { return f(3); }` normally and reaches EOF with no open block.
5. Semantics: the last statement of `f`'s body is an `if` without `else`, so not every path returns: WRN-MISSING-RETURN at `f` (1:5). The body block has `closed_by_repair`, so R8 gives `caused_by = E-0001`. `a` is a parameter (exempt from `sem.unused_declaration`). `main` exists. Nothing else is reported.

Without §4.7, line 6 would be parsed as a local declaration `int main`, and the first record would be a misleading SYN-MISSING-SEMICOLON at `(`; the real cause would surface only at EOF as a second, unrelated root. A missing `}` in the *last* function is still reported only at EOF.

### T3, missing `(` after `if`

```c
int main(void) {
    int x = 1;
    if x > 0) {
        x = 2;
    }
    return 0;
}
```

1. Lexer: nothing.
2. Parser, line 3: `if_stmt` consumes `if`, then `expect("(")` finds `x` (3:8). Selection: not unsupported, not EOF, expected set is `(` (not `;`, not only closing brackets, not the start of an expression), so selection rule 5 gives E-0001 SYN-EXPECTED-TOKEN at 3:8, `found = x`, `expected = ["("]`. `recovering` is empty and `x` has no `lex_gap`, so `caused_by` is null.
3. `ParseError` is caught by the `statement()` of the `if`. Statement-level panic starts and opens the region (owner E-0001). It skips `x`, `>`, `0`, `)` and stops before `{`, which is in `SYNC_STMT_STOP`. The result is an `ErrorStmt` with `kind_hint = "if"`, span 3:5 to 3:13, `declared_names = []`, `idents_in_span = {x}` and `stopped_before = "{"`.
4. The block loop calls `statement()` at `{` (3:15), a block. Panic stopped before `{`, so this block gets `orphan_of = E-0001`. Inside, `x = 2;` parses; its `;` is consumed by a successful match, which closes the region (§4.5 (iii)). The `}` on line 5 ends the block. `return 0;` and the final `}` parse normally. No further syntax error.
5. Semantics: the `ErrorStmt` is skipped, so the read of `x` in `x > 0` is lost. The orphan block only writes `x` (`x = 2`). `x` is declared at 2:9 and never read: WRN-UNUSED-VAR. R4 does not apply (the declaration is not broken). R6 applies: the `ErrorStmt` is in `x`'s scope after its declaration and `x` is in its `idents_in_span`, so `caused_by = E-0001`. No other record (`main` exists and returns).

### T4, undeclared variable used 5 times

```c
int main(void) {
    int total = 0;
    count = 1;
    total = total + count;
    count = count + 1;
    total = total + count;
    return total;
}
```

1. Lexer and parser: no errors. The AST is complete and has no error nodes.
2. Semantics, in source order. `count` is never declared: five uses (3:5, 4:21, 5:5, 5:13, 6:21), each a SEM-UNDECLARED-VAR record (§6: no suppression of repeated uses). `count` gets type `<error>`, so the assignments `total = total + count` and `count = count + 1` raise no SEM-TYPE-MISMATCH (§6: type checks absorb `<error>`).
3. `caused_by`: R5 needs an `ErrorStmt` or broken declaration that declares `count`; there is none. All five records have `caused_by = null`.
4. `total` is read (`total + count`, `return total`), so there is no WRN-UNUSED-VAR.
5. Provisional F2 root rule: E-0002 to E-0005 have the same code and name as E-0001 in the same function, so their root is E-0001. Displayed count: 1.

### T5, lexical error inside an expression

```c
int main(void) {
    int x = 5 @ 2;
    return x;
}
```

1. Lexer, line 2: `@` (2:15) is in no token: E-0001 LEX-INVALID-CHAR, `found = @`. The character is skipped, no token is emitted, and the next token (`2`, 2:17) gets `lex_gap = E-0001`.
2. Parser: the initializer is the expression `5` (ends 2:13); the next token `2` cannot continue it. `expect(";")` finds `2` on the **same** line, so §4.2 does not repair. Selection rule 2 gives E-0002 SYN-MISSING-SEMICOLON at 2:14, `found = 2`. `recovering` is empty, so R2 does not apply; `2` has `lex_gap = E-0001`, so R1 applies: `caused_by = E-0001`.
3. As in T1b: a broken declaration `x : int` with `error_id = E-0002`; panic opens the region, skips `2`, consumes `;`, which closes it.
4. Semantics: `x` is read in `return x`, so there is no warning. No other record.

### T6, the F1 acceptance file (one lexical, one syntax, one semantic error)

```c
#include <stdio.h>
int main(void) {
    int count = 0;
    printf("total\q\n", count);
    count = count + 1
    result = count;
    return 0;
}
```

1. Lexer: line 1 is an accepted `#include <stdio.h>` and produces no token (it sets no `lex_gap`). On line 4, the escape `\q` at 4:18 is not in `escape`: E-0001 LEX-INVALID-ESCAPE, `found = \q`. The STRING_LIT token is still emitted with the escape removed, so no `lex_gap` is set.
2. Parser: `count = count + 1` ends at 5:21. `expect(";")` finds `result` (6:5), on a later line: §4.2 fires, E-0002 SYN-MISSING-SEMICOLON at 5:22, `found = result`. No region, no `lex_gap`: `caused_by` is null. Line 6 parses as a normal statement.
3. Semantics: `printf` is declared (the include was seen) and its first argument is a string literal. `count` is read. `result` is never declared: E-0003 SEM-UNDECLARED-VAR at 6:5. No `ErrorStmt` or broken declaration declares `result`, so R5 does not apply: `caused_by` is null.

This reaches PRD F1's acceptance test (three records, one per phase, correct positions) **only because** the semantic analyser runs on the partial AST (invariant 1).

### T7, missing `)` before `{`

```c
int main(void) {
    int i = 0;
    while (i < 10 {
        i = i + 1;
        if (i == 5) {
            break;
        }
    }
    return i;
}
```

1. Lexer: nothing.
2. Parser, line 3: `while`, `(`, then the expression `i < 10`. `expect(")")` finds `{` (3:19). The §4.3 decision is YES, so the rule applies: the required `)` closes a `while` header and the current token is `{`. E-0001 SYN-UNBALANCED-BRACKET at 3:19, `found = {`, `expected = [")"]`; the message names the `(` on line 3. Nothing is consumed, no region is opened, `caused_by` is null.
3. The `while` node is kept with its condition `i < 10`, and the body block `{ … }` is parsed as its body. The `if` and `break` inside are ordinary.
4. Semantics: `break` is inside a real `while` node, so there is no SEM-BREAK-OUTSIDE-LOOP. `i` is read in the condition and in `return i`. No other record.

What NO would have produced: the same E-0001 record, then statement-level panic, which would stop at once before `{` (it is in `SYNC_STMT_STOP`), giving an `ErrorStmt` (`kind_hint = "while"`, `stopped_before = "{"`, region owner E-0001) and an orphan block. The `break` at 6:13 would give a second record, SEM-BREAK-OUTSIDE-LOOP, linked to E-0001 by R7, and the read of `i` in the condition would be lost. YES gives one record where NO gives two.

### Record table

| Trace | Id | Code | Line:Col | Found | caused_by | root_id |
|---|---|---|---|---|---|---|
| T1 | E-0001 | SYN-MISSING-SEMICOLON | 3:14 | a | — | E-0001 |
| T1b | E-0001 | SYN-MISSING-SEMICOLON | 3:14 | a | — | E-0001 |
| T1b | E-0002 | WRN-UNUSED-VAR | 3:9 | b | E-0001 | E-0001 |
| T2 | E-0001 | SYN-UNBALANCED-BRACKET | 6:1 | int | — | E-0001 |
| T2 | E-0002 | WRN-MISSING-RETURN | 1:5 | f | E-0001 | E-0001 |
| T3 | E-0001 | SYN-EXPECTED-TOKEN | 3:8 | x | — | E-0001 |
| T3 | E-0002 | WRN-UNUSED-VAR | 2:9 | x | E-0001 | E-0001 |
| T4 | E-0001 | SEM-UNDECLARED-VAR | 3:5 | count | — | E-0001 |
| T4 | E-0002 | SEM-UNDECLARED-VAR | 4:21 | count | — | E-0001 |
| T4 | E-0003 | SEM-UNDECLARED-VAR | 5:5 | count | — | E-0001 |
| T4 | E-0004 | SEM-UNDECLARED-VAR | 5:13 | count | — | E-0001 |
| T4 | E-0005 | SEM-UNDECLARED-VAR | 6:21 | count | — | E-0001 |
| T5 | E-0001 | LEX-INVALID-CHAR | 2:15 | @ | — | E-0001 |
| T5 | E-0002 | SYN-MISSING-SEMICOLON | 2:14 | 2 | E-0001 | E-0001 |
| T6 | E-0001 | LEX-INVALID-ESCAPE | 4:18 | \q | — | E-0001 |
| T6 | E-0002 | SYN-MISSING-SEMICOLON | 5:22 | result | — | E-0002 |
| T6 | E-0003 | SEM-UNDECLARED-VAR | 6:5 | result | — | E-0003 |
| T7 | E-0001 | SYN-UNBALANCED-BRACKET | 3:19 | { | — | E-0001 |

### Summary table

| Trace | Raw | Displayed | Fatal | Warning | Reference |
|---|---|---|---|---|---|
| T1 | 1 | 1 | 1 | 0 | match |
| T1b | 2 | 1 | 1 | 1 | match |
| T2 | 2 | 1 | 1 | 1 | match |
| T3 | 2 | 1 | 1 | 1 | n/a |
| T4 | 5 | 1 | 5 | 0 | n/a |
| T5 | 2 | 1 | 2 | 0 | n/a |
| T6 | 3 | 3 | 3 | 0 | match |
| T7 | 1 | 1 | 1 | 0 | n/a |

Raw counts all records; displayed counts distinct roots under the provisional rule of §7. Across the five traces whose raw count is at least 2 (T1b, T2, T3, T4, T5), raw is 13 and displayed is 5, a reduction of 62%. T6 is deliberately three independent faults, so it stays at 3.

No trace triggered the loop guard (§4.6 point 3): in every trace each parser loop iteration consumed at least one token.

Results that surprised me:

- T5: the student's fault is the `@`, but the parser reports a SYN-MISSING-SEMICOLON, because the lexer deleted the `@` and the parser then saw `5 2`. Only the R1 link (`lex_gap`) shows that the lexical error caused it.
- T3: the only symptom of the missing `(` besides the syntax error is a WRN-UNUSED-VAR on a variable that the student does use (in the lost condition). R6 links it, but a student reading the raw list would be confused without the link.
- T4: the PRD's "undeclared variable groups all its later uses" is not a `caused_by` relation. The five records are independent in `caused_by` and are merged only by the provisional F2 rule.
- T1b: the same fault on one line gives two raw records (the second is a warning), while on separate lines it gives one (T1).
- T7: the YES decision gives a single record. The cascade described under "What NO would have produced" is real but is avoided by the phrase-level repair.

## 10. F2 feasibility

TODO (plan 002 step 6)

## 11. Interface for later milestones

TODO (plan 002 step 6)
