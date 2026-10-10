# Plan 002: Specify how the compiler recovers from errors and links cascading errors to their cause

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. **Do NOT edit `plans/README.md`**: the advisor
> maintains the index for this plan. End your final report with a
> **Viva notes** list (decisions an examiner might ask about), as described in
> "Maintenance notes".
>
> **Drift check (run first)**, from the project root in Git Bash:
> 1. `git diff --stat 85702b6..HEAD -- docs/error-recovery.md docs/decisions/0002-error-recovery-and-cascade-linking.md`
>    → must print nothing. If it prints anything, someone already wrote these files: STOP.
> 2. `test -f docs/language-spec.md && test -f docs/error-catalog.md && echo present`
>    → must print `present`. These files are created by plan 001
>    (`plans/001-define-c-subset-and-error-catalog.md`). If either is missing, STOP: plan 001 has not landed.

## Status

- **Priority**: P1 (milestone 1's parser implements this design; F2 depends on it)
- **Effort**: M
- **Risk**: MED (documents only, but the design decides whether F2's acceptance test is reachable)
- **Depends on**: `plans/001-define-c-subset-and-error-catalog.md`
- **Category**: direction / docs
- **Planned at**: commit `85702b6`, 2026-10-10

## Why this matters

The project is a "Compiler Error Assistant": a Python compiler for a strict C99 subset plus an AI layer. The AI layer captures errors per phase (F1), groups cascading errors under one root cause (F2), explains them, and proposes fixes that are re-compiled before being shown (F8). All of that depends on one thing nobody has written down yet: **what the compiler does after its first error**. If the lexer or parser stops at the first error, F1's acceptance test (3 errors → 3 records) fails. If recovery is ad hoc, F2 has no reliable signal for "this error was caused by that one", and F8 can't compare error lists before and after a patch. This plan produces a precise recovery specification (exact sync token sets, AST error nodes, a `caused_by` link with exact rules) and hand-traced examples. It also gives an honest answer on whether PRD F2's acceptance test ("one missing semicolon that previously produced 10+ errors shows 1 root cause") can be met. The parser does not exist yet. Milestone 1 implements this document, so it must be exact enough to code from without making further decisions.

## Current state

### Files

- `cd project prd.docx`: the PRD. Read-only. To extract its text (needed only if you want to re-check a quote): `python -I -c "import zipfile,re,sys;sys.stdout.reconfigure(encoding='utf-8');x=zipfile.ZipFile(sys.argv[1]).read('word/document.xml').decode();print('\n'.join(t for t in (''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>',p,re.S)) for p in re.findall(r'<w:p[ >].*?</w:p>',x,re.S)) if t.strip()))" "cd project prd.docx"`
- `plans/001-define-c-subset-and-error-catalog.md`: the source of truth for the grammar, types, the 16 `sem.*` rules, the 37 error codes and the syntax-code selection rules.
- `docs/language-spec.md`, `docs/error-catalog.md`, `docs/decisions/0001-single-language-c-subset.md`, `tools/check_spec.py`: **created by plan 001**. They did not exist at `85702b6`. The drift check confirms they exist now.
- `README.md`, `VIVA.md`, `plans/README.md`: maintained by the advisor. Do not edit them. They may show as modified in `git status` before you start. That is the advisor's uncommitted work: leave it alone and never stage it.
- No Python code, tests or `pyproject.toml` exist. Do not create any.

### PRD facts this design must honour (quoted)

- F1: "Each compiler phase (lexical, syntax, semantic) reports errors through one interceptor instead of printing strings." Acceptance: "a test file with one lexical, one syntax and one semantic error yields three records with the correct phase and position."
- F2: "Rule-based first: errors after a syntax error within the same statement or block are children of the first; an undeclared variable groups all its later uses." "The UI shows one root error with a collapsed count of related symptoms." Acceptance: "a file with one missing semicolon that previously produced 10 or more errors shows 1 root cause."
- F8: "If the original error is gone and no new fatal error appears, the fix is marked verified".
- Risks table, row 1: "Clustering heuristics miss unusual cascades | Medium | Start with panic-mode recovery points (statement and block ends); log misses and add rules".
- Success metric: "At least 70% fewer displayed errors on cascading test files", measured by "Count raw vs displayed errors on 20 faulty programs".
- Error record schema: `id` (e.g. `E-0007`), `phase` (lexical | syntax | semantic), `code`, `severity` (fatal | warning), `line`, `column`, `found`, `expected` (list), `snippet`, `root_id` (e.g. `E-0003 (parent cluster)`), `rule_ref` ("grammar rule name for RAG lookup").

### Plan 001 facts this design must use (quoted from plan 001; the docs it creates must match)

Syntax grammar (the statement part):

```ebnf
program        = { top_decl } , EOF ;
top_decl       = type_spec , ( function_def | global_decl ) ;
function_def   = IDENT , "(" , params , ")" , ( block | ";" ) ;
params         = [ "void" | param_list ] ;
param_list     = param , { "," , param } ;
param          = type_spec , IDENT ;
global_decl    = declarator , { "," , declarator } , ";" ;
type_spec      = "int" | "float" | "double" | "char" | "void" ;
declarator     = IDENT , [ array_suffix ] , [ "=" , expression ] ;
array_suffix   = "[" , expression , "]" ;
block          = "{" , { statement } , "}" ;
statement      = var_decl | if_stmt | while_stmt | for_stmt | return_stmt
               | break_stmt | continue_stmt | block | expr_stmt | empty_stmt ;
var_decl       = var_core , ";" ;
var_core       = type_spec , declarator , { "," , declarator } ;
if_stmt        = "if" , "(" , expression , ")" , statement , [ "else" , statement ] ;
while_stmt     = "while" , "(" , expression , ")" , statement ;
for_stmt       = "for" , "(" , [ for_init ] , ";" , [ expression ] , ";"
               , [ expression ] , ")" , statement ;
for_init       = var_core | expression ;
return_stmt    = "return" , [ expression ] , ";" ;
break_stmt     = "break" , ";" ;
continue_stmt  = "continue" , ";" ;
expr_stmt      = expression , ";" ;
empty_stmt     = ";" ;
```

(The expression grammar `expression … primary` follows in the spec; `primary = INT_LIT | FLOAT_LIT | CHAR_LIT | STRING_LIT | IDENT | "(" , expression , ")"`.)

Lexical facts: the keywords are `int float double char void if else while for return break continue`. Lines and columns are 1-based, and a tab counts as one column. `#include <stdio.h>` is accepted and produces no token. The lexical error cases are: a character not in any token; a string not closed before end of line; a char literal that is unclosed, empty or holds more than one character; an unclosed block comment; a number followed directly by a letter, `_` or a second `.`; an escape other than `\n \t \0 \' \" \\`.

The 15 codes this design touches (rows from the 37-code catalog; columns Code | Phase | Severity | Category | rule_ref):

| Code | Phase | Severity | Category | rule_ref |
|---|---|---|---|---|
| LEX-INVALID-CHAR | lexical | fatal | malformed-token | `token` |
| LEX-UNTERMINATED-STRING | lexical | fatal | unclosed-delimiter | `STRING_LIT` |
| LEX-BAD-CHAR-LITERAL | lexical | fatal | malformed-token | `CHAR_LIT` |
| LEX-UNTERMINATED-COMMENT | lexical | fatal | unclosed-delimiter | `BLOCK_COMMENT` |
| LEX-MALFORMED-NUMBER | lexical | fatal | malformed-token | `number` |
| LEX-INVALID-ESCAPE | lexical | fatal | malformed-token | `escape` |
| LEX-UNSUPPORTED-DIRECTIVE | lexical | fatal | syntax-structure | `directive` |
| SYN-MISSING-SEMICOLON | syntax | fatal | missing-semicolon | `<production>` |
| SYN-UNBALANCED-BRACKET | syntax | fatal | unclosed-delimiter | `<production>` |
| SYN-EXPECTED-TOKEN | syntax | fatal | syntax-structure | `<production>` |
| SYN-EXPECTED-EXPRESSION | syntax | fatal | syntax-structure | `<production>` |
| SYN-UNEXPECTED-EOF | syntax | fatal | unclosed-delimiter | `<production>` |
| SEM-UNDECLARED-VAR | semantic | fatal | undeclared-identifier | `sem.declare_before_use` |
| SEM-MISSING-MAIN | semantic | fatal | control-flow | `sem.entry_point` |
| WRN-UNUSED-VAR | semantic | warning | unused-code | `sem.unused_declaration` |

Other codes you will mention: SYN-EXPECTED-TYPE, SYN-INVALID-ASSIGN-TARGET, SYN-UNSUPPORTED-FEATURE, SEM-UNDECLARED-FUNC, SEM-BREAK-OUTSIDE-LOOP, SEM-BAD-ARRAY-SIZE, SEM-NONCONST-GLOBAL-INIT, SEM-PRINTF-FORMAT, WRN-MISSING-RETURN, plus the type-check codes listed in Step 4. **There are exactly 37 codes. This plan adds none.**

"Choosing among syntax codes" (plan 001; apply in order):
0. The found token is an UNSUPPORTED_KEYWORD or UNSUPPORTED_OP, or is `*` directly after a `type_spec` → `SYN-UNSUPPORTED-FEATURE`.
1. The found token is EOF → `SYN-UNEXPECTED-EOF`.
2. The expected set is exactly `;` → `SYN-MISSING-SEMICOLON`.
3. The expected set contains only closing brackets (`)`, `]`, `}`), or the found token is a closing bracket with no matching opener → `SYN-UNBALANCED-BRACKET`.
4. The parser expected the start of an expression → `SYN-EXPECTED-EXPRESSION`. It expected a type → `SYN-EXPECTED-TYPE`.
5. Otherwise → `SYN-EXPECTED-TOKEN`.

Semantic rules quoted from plan 001 that recovery affects:
- `sem.unused_declaration`: "A local variable that is declared but never read produces a warning. Parameters and globals are exempt."
- `sem.entry_point`: "The program must define `int main()` or `int main(void)` … this compiler reports it at the end of semantic analysis."
- `sem.return_paths`: "the body's last statement is a `return`, or an `if` with an `else` whose branches both return on every path (recursively through blocks)."
- `sem.loop_control`: "`break` and `continue` may appear only inside `while` or `for`."
- `sem.global_init`: "A global initialiser must be a numeric or char literal, optionally preceded by `-`."
- `sem.array_access`: "An array size must be an integer literal greater than 0".

### Design decisions already made by the advisor (specify them; do NOT re-decide)

1. **Lexer recovery**: record the error, skip the bad input, continue. The bad input is the bad character, or everything up to end of line for an unterminated string or char literal, or everything up to EOF for an unterminated comment. **Never pass an error token to the parser.**
2. **Phrase-level repair for a missing `;`**: when `;` is expected and the found token starts on a **later line** than the previous token, record SYN-MISSING-SEMICOLON and continue as if `;` were present. Nothing is consumed. **You decide** (Step 3) whether the same virtual insertion applies to a missing `)` directly before `{`, and justify it.
3. **Location convention** (shared with plan 003; do not change): SYN-MISSING-SEMICOLON is reported at the line and column immediately after the last token of the unterminated statement. Every other syntax error is reported at the found token. Lexical errors are reported at the first bad character. Semantic errors are reported at the offending identifier or operator.
4. **Otherwise panic mode, with explicit sync sets**. Statement level: skip to `;` and consume it, or stop without consuming before `}` or a statement-start token (`if while for return break continue {` or a type keyword). Block level: `}`. Top level: a type keyword at the start of a line. Progress is guaranteed: the parser can never loop forever.
5. **Error AST nodes**: `ErrorStmt` and `ErrorExpr` keep their source span. A declaration with a broken initializer still declares its name with its declared type. **Semantic analysis always runs on the partial AST.**
6. **Record, never hide; link instead**: cascade errors are not suppressed. A record may carry `caused_by` (the id of the error that caused it), set **only** when the compiler knows the causality. F2 (a later milestone) uses `caused_by` plus the PRD rules to assign `root_id`. Raw count = all records. Displayed count = number of roots.
7. **Record schema additions**: exactly four fields are added to the PRD schema table: `language` (always `"c"`, from plan 001), `caused_by`, `span_end`, and `message`. PRD F1 lists `message` but the PRD schema table omits it. It is the catalog's message template with its placeholders filled in.
8. **Honest feasibility**: no "naive mode" that disables recovery to manufacture cascades.
9. **Phrase-level repair for a missing `}` (advisor decision, made during plan review on 2026-10-10).** The subset has no nested functions. Therefore, when `statement()` inside a block sees a type keyword followed by `IDENT` followed by `(`, a `}` must be missing. A local declarator is `IDENT [ "[" … "]" ] [ "=" … ]` and can never be followed directly by `(`, so valid code can never trigger this. Record ONE SYN-UNBALANCED-BRACKET at the type keyword with `expected = ["}"]` and `found` = the type keyword. Its message names the innermost open `{` and that brace's line. Close **all** open blocks of the current function without consuming anything, and return to the top-level loop, which then parses the function normally. No uncertain region is opened. This agrees with plan 003's location convention ("Missing `}`").

### Detailed design the advisor has worked out for you to write down

Steps 2–5 give the exact content. Where a step says "write exactly", copy the rule. You may improve the wording but must not change the meaning.

## Commands you will need

Run every command from the project root (`C:\Users\Naman\OneDrive\Desktop\Compiler project`) in **Git Bash**. Quote paths because the folder name contains a space.

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | see top of plan | empty output; `present` |
| Plan 001 checker | `python -I tools/check_spec.py` | `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`, exit 0 |
| Heading count | `grep -c '^## ' docs/error-recovery.md` | `11` |
| Codes used ⊆ catalog | the command in the block below | no output |
| Branch diff | `git diff --name-only main..HEAD` | only the two in-scope files |

"Codes used ⊆ catalog" command (copy exactly):

```bash
comm -23 <(grep -ohE '(LEX|SYN|SEM|WRN)(-[A-Z]+)+' docs/error-recovery.md docs/decisions/0002-error-recovery-and-cascade-linking.md | sort -u) <(grep -oE '^\| (LEX|SYN|SEM|WRN)(-[A-Z]+)+' docs/error-catalog.md | sed 's/^| //' | sort -u)
```

**Always write codes in full.** Never abbreviate them as `SEM-UNDECLARED-*` or similar, or this check reports false mismatches.

There is no build, test suite or linter. Do not install anything.

## Scope

**In scope** (create only these two files):
- `docs/error-recovery.md`: the recovery specification.
- `docs/decisions/0002-error-recovery-and-cascade-linking.md`: the ADR.

**Out of scope** (do NOT touch):
- Any Python code (no lexer, parser, analyser, tests, `pyproject.toml`). The parser is built in milestone 1 from your document.
- `README.md`, `VIVA.md`, everything under `plans/`, and the PRD. The advisor maintains them. Put viva-worthy points in your final report.
- `docs/language-spec.md`, `docs/error-catalog.md`, `docs/decisions/0001-*.md`, `tools/check_spec.py`. If the design seems to need a catalog or spec change (a new code, a changed message, a grammar change), **report it in your final report and do not make it**. A new code is a STOP condition.
- No "naive mode", flag or option that turns recovery off.

## Git workflow

- Before starting: `git rev-parse --abbrev-ref HEAD` must print `main`. If it doesn't, run `git switch main`. If that refuses because of local changes, STOP. Never stash, reset or discard the advisor's uncommitted edits. Then run `git switch -c advisor/002-error-recovery`. Uncommitted edits to `VIVA.md`/`plans/README.md` simply stay in the working tree. Leave them unstaged.
- One commit per step that changes a file (Steps 2–7). Stage only the file you changed, by explicit path (`git add docs/error-recovery.md`). **Never** use `git add -A` or `git add .`, because the advisor's uncommitted edits would be swept in.
- Message format: `docs: <what> (plan 002 step N)`, then a blank line, then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use two `-m` flags (git puts a blank line between them):
  `git commit -m "docs: add error-recovery goals, schema and lexer recovery (plan 002 step 2)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`
- Do NOT push, merge or open a PR (there is no remote).

## Steps

### Step 1: Preflight. Confirm that plan 001's documents match plan 001 (no commit)

Run each check in order:

1. `python -I tools/check_spec.py` → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`.
2. `grep -cE '^\| (LEX|SYN|SEM|WRN)-' docs/error-catalog.md` → `37`.
3. `grep -c '^### sem\.' docs/language-spec.md` → `16`.
4. `grep -c 'Choosing among syntax codes' docs/error-catalog.md` → at least `1`. Then read that section and confirm it states rules 0–5 exactly as quoted in "Current state".
5. Open `docs/language-spec.md` section 2 and confirm the statement grammar matches the ebnf excerpt in "Current state" rule by rule.
6. Create the branch (see Git workflow).

If any check fails, or the docs disagree with the excerpts in this plan, STOP. Plan 001's output is the foundation, so do not work around it.

**Verify**: `git rev-parse --abbrev-ref HEAD` → `advisor/002-error-recovery`.

### Step 2: Create `docs/error-recovery.md` with all headings, and write sections 1–3

Create the file with **exactly these 11 `##` headings, in this order, with this text**. Sub-headings (`###`) may be added freely.

```text
# Error Recovery Specification
## 1. Goals and invariants
## 2. Error record schema additions
## 3. Lexer recovery
## 4. Parser recovery
## 5. Error AST nodes
## 6. Semantic analysis on a partial AST
## 7. caused_by rules
## 8. Locations
## 9. Traced examples
## 10. F2 feasibility
## 11. Interface for later milestones
```

For sections 4–11, write the single line `TODO (plan 002 step N)` for now. Fill in sections 1–3 as follows.

**§1 Goals and invariants**: list these invariants as numbered items:
1. Every phase always runs. The lexer reads the whole file. The parser always produces a complete `Program` AST, possibly containing error nodes. The semantic analyser always runs on that AST, even when earlier phases recorded errors.
2. Every detected error produces exactly one record. Nothing is suppressed. Cascades are linked through `caused_by`, never dropped.
3. `caused_by` is set only by the rules in §7. Each rule names a mechanical condition the compiler can check, not a guess.
4. The parser terminates on every input (see §4, "Progress guarantee").
5. Records are deterministic. The same source always yields the same records, in the same order, with the same ids.
6. Record ids are `E-0001`, `E-0002`, … in creation order. The lexer runs to completion before parsing starts, so all lexical records come first, then syntax records, then semantic records. Display order (by line, then column) is a UI concern. It does not change ids.

**§2 Error record schema additions**: one table with columns `| Field | Type | Meaning |`. Include exactly these four rows, each beginning with the field name in plain text (no backticks):

| Field | Type | Meaning |
|---|---|---|
| language | string | Always `"c"` (plan 001 / ADR 0001). Lets a future adapter add a language without changing the AI layer. |
| caused_by | string or null | Id of the record that caused this one, set only by a §7 rule; null otherwise. |
| span_end | object `{line, column}` | Inclusive end of the source text the record is about (see §8). Equal to `(line, column)` for zero-width errors (SYN-MISSING-SEMICOLON and EOF errors). |
| message | string | The catalog's message template for `code`, with placeholders filled from the record. PRD F1 lists it, but the PRD schema table omits it. |

Then state that all PRD fields are kept unchanged. Add that `root_id` is assigned by F2 (milestone 2), not by the compiler phases. Until F2 exists, the interceptor sets `root_id = id`. Say that `found` for the EOF token is the string `EOF`.

**§3 Lexer recovery**: state the rule: "record, skip the bad input, continue; never pass an error token to the parser". Then give this table, with exactly these 7 rows, each row beginning `| LEX-`:

| Code | Reported at (first bad character) | Bad input skipped | Token emitted | Sets `lex_gap` on next token |
|---|---|---|---|---|
| LEX-INVALID-CHAR | the character | that one character | none | yes |
| LEX-UNTERMINATED-STRING | the opening `"` | from `"` up to (not including) the end-of-line character | none | yes |
| LEX-BAD-CHAR-LITERAL | the opening `'` | unclosed on its line: up to end of line; closed but empty or more than one character (`''`, `'ab'`): through the closing `'` | none | yes |
| LEX-UNTERMINATED-COMMENT | the `/` of `/*` | everything up to EOF | none | yes (the EOF token) |
| LEX-MALFORMED-NUMBER | the first character of the number | the maximal run of `[A-Za-z0-9_.]` that starts at the number (`12abc`, `1.2.3`, `12.`) | none | yes |
| LEX-INVALID-ESCAPE | the `\` | the two-character escape only. In a STRING_LIT the rest of the literal is lexed normally and the token is emitted with the escape removed from its value. In a CHAR_LIT the whole literal is skipped (a char literal without its one character is not a token). | STRING_LIT: the literal; CHAR_LIT: none | STRING_LIT: no; CHAR_LIT: yes |
| LEX-UNSUPPORTED-DIRECTIVE | the `#` | the rest of the line | none | no (valid directives produce no token either, so the token stream is unchanged) |

Explain under the table:
- "First bad character" means the first character of the rejected lexeme (for `12abc`, the `1`). For a single bad character, that is the character itself. Write this interpretation down explicitly. The advisor has confirmed it, and plan 003 agrees.
- `lex_gap` is a field on every token: the id of the **last** lexical record whose skipped input lies between the end of the previous token and the start of this token, or `None`. It is how the parser learns, mechanically, that a token is missing in front of it (rule R1 in §7).
- Why the STRING_LIT case still emits a token: the bad input is the escape alone. Removing it leaves a well-formed literal. No later phase reads string contents (format specifiers are not checked, `sem.builtins`), so this is not an error token.
- A string with both an invalid escape and no closing quote records both errors (escape first, by position). Neither has `caused_by`. Lexical records never have `caused_by`.
- Progress: each lexer step consumes at least one character, so the lexer always terminates.

**Verify**:
- `grep -c '^## ' docs/error-recovery.md` → `11`
- `grep -cE '^\| LEX-' docs/error-recovery.md` → `7`
- `grep -cE '^\| (language|caused_by|span_end|message) \|' docs/error-recovery.md` → `4`
- Commit: `docs: add error-recovery goals, schema and lexer recovery (plan 002 step 2)`. Then `git log -1 --format=%B | tail -1` → `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Step 3: Write §4 Parser recovery

Replace the §4 TODO with these sub-sections.

**§4.1 Expected sets**: state that the `expected` field and syntax-code selection use the token or token class that the failing `expect(...)` call required at that point (for example `[";"]` after a complete declarator), not the full set of tokens that could legally follow. Without this, SYN-MISSING-SEMICOLON (rule 2: "expected set is exactly `;`") could never be selected after a declarator, because `,` and `=` could also follow. Also state that the bracket stack used by rule 3 ("closing bracket with no matching opener") contains only opening brackets **consumed by successful matches**. Brackets skipped during panic mode are never pushed.

**§4.2 Phrase-level repair: missing semicolon**: write exactly this rule:
> In `expect(";")`, if the current token is not `;`, is not EOF, and its start line is greater than the end line of the previous consumed token, then: record SYN-MISSING-SEMICOLON at the position immediately after the previous token (`line` = previous token's end line, `column` = previous token's end column + 1), with `found` = the current token's text and `expected = [";"]`. Consume nothing, return as if `;` had been matched, and do not enter panic mode or open an uncertain region.

When the found token is on the **same** line, the code is still SYN-MISSING-SEMICOLON (selection rule 2) at the same "after the previous token" location, but recovery is panic mode (§4.4). When the found token is EOF, the code is SYN-UNEXPECTED-EOF (selection rule 1 comes first) and §4.4's EOF rule applies.

**§4.3 Missing `)` before `{`**: you must decide this. Write a line in exactly this form (`YES` or `NO`, then your reason on the same line):
`Decision (missing ')' before '{'): YES — <one-sentence reason>` or `Decision (missing ')' before '{'): NO — <one-sentence reason>`

Facts to weigh, which you must discuss in 4–8 sentences:
- The case is `if (cond {`, `while (cond {` or a `for` header ending `… {`. The parser has consumed the header's `(` and a complete expression, then `expect(")")` finds `{`.
- The code is SYN-UNBALANCED-BRACKET (selection rule 3, expected exactly `)`), reported at the found `{` (location convention). The insertion choice does not change the code or location.
- In this subset `{` can never appear inside an expression, so the insertion point is unambiguous. The `;` rule, by contrast, depends on line layout.
- With YES, the `if`/`while`/`for` node is kept with its condition and body. A `break` in the body stays inside a loop, and reads in the condition still count as reads.
- With NO, panic mode stops before `{` without consuming it, the statement becomes an `ErrorStmt` and the `{ … }` that follows is parsed as a separate "orphan" block. Then `break` inside it produces SEM-BREAK-OUTSIDE-LOOP, linked by rule R7 (§7), and condition reads are lost (rule R6 links any resulting WRN-UNUSED-VAR).
- Either choice must keep the progress guarantee and must be traced (trace T7 in Step 5).
If you choose YES, add the rule to §4.2's wording pattern: the condition is "found token is `{`, the required token is the `)` that closes an `if`/`while`/`for` header". Record SYN-UNBALANCED-BRACKET at the `{`, consume nothing, and no uncertain region is opened.

**§4.4 Panic mode and sync sets**: include this fenced `text` block, keeping these 5 names at the start of their lines exactly. You may add explanatory text after each name.

```text
SYNC_STMT_CONSUME = { ";" }   -- skip up to and including the first ";"
SYNC_STMT_STOP    = { "}", "if", "while", "for", "return", "break", "continue", "{", "int", "float", "double", "char", "void", EOF }   -- stop BEFORE these; do not consume
SYNC_FOR_HEADER   = inside a for header: ";" is NOT a sync token; consume the ")" that closes the header; stop before SYNC_STMT_STOP
SYNC_BLOCK        = { "}" }   -- the block loop ends at "}" (consumed by the block's own expect) or EOF; panic never consumes "}"
SYNC_TOP_STOP     = a type keyword that is the first token on its line AND the depth of "{"/"}" skipped so far in this panic is 0; or EOF   -- stop before; do not consume
```

Then specify, in prose:
- **Mechanism.** Errors other than phrase repair raise an internal `ParseError(error_id)` after the record is created. Catch points:
  - (a) `statement()`: every statement, innermost first. It catches, runs statement-level panic (or for-header panic if the error occurred between `for (` and the header's `)`), and returns an `ErrorStmt`.
  - (b) The declarator initializer `= expression` and the `array_suffix` expression in `var_decl` and `global_decl` (CP-INIT, CP-SIZE). These catch, replace the expression with an `ErrorExpr`, run panic (statement-level for locals, top-level for globals), and return the declaration node, which still declares its name (see §5).
  - (c) `top_decl()`: it catches and runs top-level panic. It returns an `ErrorStmt` at top level (`kind_hint = "top"`).
- **Statement-level panic.** Look at the current token. If it is in SYNC_STMT_STOP, stop. If it is `;`, consume it and stop. Otherwise consume it (skip) and repeat.
- **Top-level panic.** Skip tokens, tracking `{` (+1) and `}` (−1) among skipped tokens. Stop before a SYNC_TOP_STOP token. "First token on its line" means no other token starts earlier on the same line. The brace-depth condition stops the sync from landing on an indented `int x;` inside a function body that is being skipped.
- **EOF.** Panic always stops at EOF. A block whose loop ends at EOF calls `expect("}")`, which records SYN-UNEXPECTED-EOF (`expected = ["}"]`, at the EOF position) and then **returns the block normally** without raising. This keeps the enclosing function intact. Each still-open block records its own SYN-UNEXPECTED-EOF. The 2nd and later ones are linked by rule R2 because the first EOF error opens the uncertain region.
- **Errors inside the header of a function definition** (parameter list) are caught by `top_decl()`.

**§4.5 Uncertain region**: write exactly:
> The parser keeps `recovering: error_id | None`. **Opened** when panic mode starts for error E (any level), or when an EOF error is recorded. If it is already open, its owner does not change. **Not opened** by phrase repair (§4.2, §4.7, and §4.3 if YES). **Closed** when (i) statement-level panic consumes a `;`, (ii) top-level panic stops at a SYNC_TOP_STOP type keyword, or (iii) any `;` or `}` is consumed by a successful match. While it is open, every new syntax error gets `caused_by = recovering` (rule R2).

Justify it in two sentences: after panic stops before a token without consuming a terminator, the parser's position in the grammar is a guess until the next terminator is matched. So an error raised before then is known to come from parsing under that guess.

**§4.6 Progress guarantee**: give the termination argument as numbered points:
1. Statement-level panic consumes at least the found token unless that token is in SYNC_STMT_STOP. Then: `}` ends the block loop (the block consumes it), EOF ends every loop, and every other stop token is the first token of a production that consumes it immediately.
2. Phrase repair consumes nothing. But every `expect(";")` follows at least one token already consumed by the same statement. Prove this with a table with columns `| Site | Production | Token(s) consumed before the ";" |` and **exactly 10 rows**, each beginning `| S1 |` … `| S10 |`, one per `";"` in the syntax grammar: `function_def` (prototype), `global_decl`, `var_decl`, `for_stmt` (first), `for_stmt` (second), `return_stmt`, `break_stmt`, `continue_stmt`, `expr_stmt`, `empty_stmt`. (For `empty_stmt` the `;` is matched only when present, so it can't fail.)
3. **Loop guard (safety net).** The block's statement loop and the program's `top_decl` loop record the token index before each iteration. If an iteration consumed nothing, they skip one token. In test mode they also raise an assertion, because by points 1–2 this must never happen. State that none of the traces in §9 triggers it.
4. Conclusion: every loop iteration consumes at least one token or exits, so the parser terminates. At most one panic error is recorded per `statement()`/`top_decl()` call, plus phrase repairs, plus one SYN-UNEXPECTED-EOF per open block.
5. The §4.7 repair consumes nothing, but it exits every open block and returns to the top-level loop. The top-level loop then consumes the type keyword as the start of `top_decl`, so progress holds.

**§4.7 Phrase-level repair: missing `}` (advisor decision 9)**: write exactly this rule:
> In `statement()`, before any other alternative: if the current token is a type keyword, the next token is `IDENT`, and the token after that is `(`, then record SYN-UNBALANCED-BRACKET at the type keyword, with `found` = the type keyword's text and `expected = ["}"]`. The message names the innermost open `{` and its line. Every open block of the current function is then closed without consuming anything. Each `Block` node is ended at the previous token and gets `closed_by_repair = <this error id>`. Control returns to the top-level `top_decl` loop. Only ONE record is created, however many blocks were open. No uncertain region is opened.

Then justify it in 2–3 sentences. In the subset, `type IDENT (` cannot start a statement, because there are no nested functions and no local prototypes. So the rule never fires on valid code, and it detects the missing `}` at the earliest point it becomes provable. Without it, the next function header is mis-parsed as a local declaration, producing a misleading SYN-MISSING-SEMICOLON root, and the real cause surfaces only at EOF as a second root. Also state the limitation: a missing `}` in the **last** function is still detected only at EOF (SYN-UNEXPECTED-EOF, §4.4).

**Verify**:
- `grep -c '^\*\*§4.7\|^### 4.7\|4.7 Phrase-level repair' docs/error-recovery.md` → at least `1`
- `grep -c 'closed_by_repair' docs/error-recovery.md` → at least `2`
- `grep -cE '^(SYNC_STMT_CONSUME|SYNC_STMT_STOP|SYNC_FOR_HEADER|SYNC_BLOCK|SYNC_TOP_STOP) ' docs/error-recovery.md` → `5`
- `grep -cE "^Decision \(missing '\)' before '\{'\): (YES|NO) " docs/error-recovery.md` → `1`
- `grep -cE '^\| S([1-9]|10) \|' docs/error-recovery.md` → `10`
- `grep -c 'recovering' docs/error-recovery.md` → at least `2`
- Commit: `docs: specify parser recovery and sync sets (plan 002 step 3)`

### Step 4: Write §5–§8 (error nodes, partial-AST semantics, `caused_by` rules, locations)

**§5 Error AST nodes**: give these structures as a fenced `python` sketch (this is documentation, not a code file). Keep the field names:

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

Also specify:
- `VarDecl`, the global declaration node and the function declaration node gain `error_id: str | None` and `idents_in_span: set[str]` (set when an error occurred after the name was consumed: a "broken declaration").
- `Block` gains `orphan_of: str | None`. It is set to the current `recovering` id when the block starts at a `{` where panic stopped (`stopped_before == "{"`).
- `Block` also gains `closed_by_repair: str | None`. It is set by the §4.7 missing-`}` repair.
- Tokens carry `lex_gap: str | None` (§3).

Write these rules:
- **Broken declaration (advisor decision 5).** Once `type_spec IDENT` of a local or global variable has been consumed, a later error never turns the declaration into an `ErrorStmt`. The node is kept, the name is declared with its declared type, a failed initializer or array size becomes an `ErrorExpr`, and remaining declarators after the error are lost (they are in the skipped span). Example: `int x = ;` declares `x : int` with initializer `ErrorExpr`.
- A **function** whose header fails (error inside `params`) becomes a top-level `ErrorStmt` with `declared_names = [(name, "function")]`. It does **not** declare the name, because its signature is unknown. Uses are linked by R5.
- `ErrorStmt` never declares names. `declared_names` exists only for linking. A `for` statement whose header failed after `for (int i` gives `declared_names = [("i","int")]`, and `i` is not declared in the enclosing scope (correct C scoping, since `i`'s scope was the `for` statement).

**§6 Semantic analysis on a partial AST**:
- The analyser visits every node. On `ErrorStmt` it does nothing (it does not analyse the partial contents and does not declare anything). On a broken declaration it declares the name and analyses whatever parts are not `ErrorExpr`.
- **The `<error>` type.** Every `ErrorExpr` has type `<error>` carrying `cause = its error_id`. A use of an undeclared name gets type `<error>` carrying `cause = the SEM-UNDECLARED-VAR (or SEM-UNDECLARED-FUNC) record's id`. A binary or unary operation, call or index with an `<error>` operand has result type `<error>` with the cause of its first `<error>` operand.
- **Type checks absorb `<error>`**: a per-operand type requirement is satisfied by an `<error>` operand, and a pairwise compatibility check (assignment, initialisation, argument vs parameter, return value vs return type) passes if either side is `<error>`. This applies to: SEM-TYPE-MISMATCH, WRN-IMPLICIT-NARROWING, SEM-VOID-VALUE, SEM-NOT-CALLABLE, SEM-ARG-TYPE, SEM-RETURN-TYPE, SEM-NOT-ARRAY, SEM-INDEX-NOT-INT, and the arithmetic-condition requirement of `sem.conditions`. Justification (write it): a type check on an operand of unknown type has no answer, so not reporting it does not hide an error, because none was detected. This is the only place where an `<error>` value avoids a record.
- **Shape checks still run** on `ErrorExpr` operands, because an `ErrorExpr` is visibly not the required shape. These are SEM-BAD-ARRAY-SIZE (size must be an integer literal > 0), SEM-NONCONST-GLOBAL-INIT (global initializer must be a literal) and SEM-PRINTF-FORMAT (first argument must be a string literal). When one fails because its operand is an `ErrorExpr`, the record gets `caused_by` by R3.
- Repeated uses of the same undeclared name each produce their own SEM-UNDECLARED-VAR record (gcc reports only once per function; we do not hide). F2's PRD rule groups them, not `caused_by`.

**§7 caused_by rules**: a table with columns `| Rule | Applies to | Condition (mechanical) | caused_by = |` and **exactly 8 rows** beginning `| R1 |` … `| R8 |`:

| Rule | Applies to | Condition (mechanical) | caused_by = |
|---|---|---|---|
| R1 lex gap | any syntax record | the found token's `lex_gap` is set and R2 does not apply | the `lex_gap` id |
| R2 uncertain region | any syntax record | `recovering` is open when the record is created | `recovering` (the region owner) |
| R3 poison operand | SEM-BAD-ARRAY-SIZE, SEM-NONCONST-GLOBAL-INIT, SEM-PRINTF-FORMAT | the operand that fails the shape check is an `ErrorExpr` | that `ErrorExpr.error_id` |
| R4 broken declaration | WRN-UNUSED-VAR | the declaration it is about has `error_id` set | that `error_id` |
| R5 lost declaration | SEM-UNDECLARED-VAR, SEM-UNDECLARED-FUNC for name n; SEM-MISSING-MAIN (n = `main`) | an earlier node (in source order) in the current function body or at file scope is an `ErrorStmt` with n in `declared_names`, or a broken declaration named n | the `error_id` of the nearest such node |
| R6 lost read | WRN-UNUSED-VAR for variable v (when R4 does not apply) | an `ErrorStmt`, `ErrorExpr` or broken declaration in v's scope, after v's declaration, has v's name in `idents_in_span` | the `error_id` of the first such node |
| R7 orphan loop body | SEM-BREAK-OUTSIDE-LOOP | the `break`/`continue` is inside a `Block` whose `orphan_of` points to an `ErrorStmt` with `kind_hint` `while` or `for` | `orphan_of` |
| R8 incomplete body | WRN-MISSING-RETURN | the function body contains an `ErrorStmt` at any depth, or the body `Block` has `closed_by_repair` set (§4.7) | the `error_id` of the first `ErrorStmt` in source order, else `closed_by_repair` |

Also write:
- Precedence: for syntax records, R2 then R1. Semantic rules don't overlap except R4 vs R6 (R4 first). If no rule applies, `caused_by = null`.
- `caused_by` always points to an **earlier** record (smaller id), so the links form a forest with no cycles. An error detected later than its true cause can't be linked backward. This is why §4.7 detects a missing `}` early, at the next function header, instead of at EOF.
- **Provisional F2 root rule** (used only to fill `root_id` in §9; F2's own plan decides the final algorithm). `root(r) = root(caused_by(r))` if `caused_by` is set. Otherwise, if r is SEM-UNDECLARED-VAR or SEM-UNDECLARED-FUNC and an earlier record with the same code and the same name exists in the same function body (or both at file scope), `root(r)` = that record's root (the PRD rule "an undeclared variable groups all its later uses"). Otherwise `root(r) = r.id`. Displayed count = number of distinct roots. Note that the PRD's other rule ("errors after a syntax error within the same statement or block are children of the first") is approximated here only through R1/R2. Applying it to whole blocks would wrongly merge independent errors. F2's plan must decide this.

**§8 Locations**: restate the advisor's location convention (decision 3) word for word, then add:
- `column` = 1-based. A tab counts as one column. "Immediately after the last token" = that token's end line, end column + 1.
- The EOF token's position = immediately after the last token of the file (its end line, end column + 1). For an empty file it is 1:1. `found = "EOF"`.
- SEM-MISSING-MAIN has no identifier. It is reported at the EOF position. This is confirmed by the advisor; plan 003's corpus uses the line of the file's last token.
- `span_end`: lexical = last character skipped (for LEX-INVALID-ESCAPE in a string, the escape's second character); SYN-MISSING-SEMICOLON and EOF errors = same as `(line, column)`; other syntax = last character of the found token; semantic = last character of the offending identifier or operator.

**Verify**:
- `grep -cE '^\| R[1-8] ' docs/error-recovery.md` → `8`
- `grep -cE '^class (Span|ErrorExpr|ErrorStmt):' docs/error-recovery.md` → `3`
- `grep -c '<error>' docs/error-recovery.md` → at least `3`
- `grep -c 'TODO (plan 002 step 4)' docs/error-recovery.md` → `0`
- Commit: `docs: specify error nodes, partial-AST semantics and caused_by rules (plan 002 step 4)`

### Step 5: Write §9 Traced examples

Trace **each of these 8 programs** through §3–§7 by hand. Copy each program verbatim into §9 in a ```` ```c ```` block: 4-space indentation, no tabs, no trailing spaces, line 1 is the first line shown. For each one, write a short numbered narrative (which token each phase looks at, which rule fires, what is skipped, where panic stops, whether the region opens or closes). Then fill both tables below.

**T1, missing `;` mid-function (newline after):**
```c
int main(void) {
    int a = 1;
    int b = 2
    a = a + b;
    return a;
}
```

**T1b, missing `;` with the next statement on the same line:**
```c
int main(void) {
    int a = 1;
    int b = 2 a = a + b;
    return a;
}
```

**T2, missing `}` before the end of a function:**
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

**T3, missing `(` after `if`:**
```c
int main(void) {
    int x = 1;
    if x > 0) {
        x = 2;
    }
    return 0;
}
```

**T4, undeclared variable used 5 times:**
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

**T5, lexical error inside an expression:**
```c
int main(void) {
    int x = 5 @ 2;
    return x;
}
```

**T6, the F1 acceptance file (one lexical, one syntax, one semantic error):**
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

**T7, missing `)` before `{` (exercises your §4.3 decision):**
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

**Record table** (one table for all traces). Exactly these columns, and every data row begins `| T<n> | E-<4 digits> |`:

`| Trace | Id | Code | Line:Col | Found | caused_by | root_id |`

Use `—` for a null `caused_by`. Ids restart at `E-0001` for each trace (each trace is a separate compilation).

**Summary table.** Exactly these columns, one row per trace (8 rows), every data row begins `| T<n> | <number> |`:

`| Trace | Raw | Displayed | Fatal | Warning | Reference |`

`Reference` is `match` if your trace equals the advisor's reference answer below, `differs: <reason>` if not, or `n/a` for traces without a reference.

**Advisor's reference answers.** Your trace must reproduce these exactly, or §9 must explain precisely which §-rule makes them differ. If a difference shows a flaw in the design rather than in this reference, that is a STOP condition.

*T1 reference*: the lexer records nothing. In line 3, `int b = 2` is parsed as a declarator. `expect(";")` finds `a` (4:5), which starts on a later line than `2` (ends 3:13), so phrase repair fires: SYN-MISSING-SEMICOLON at 3:14, nothing consumed, no region. Lines 4–5 parse normally. Semantics: `a` and `b` are both read. Nothing else.

| Trace | Id | Code | Line:Col | Found | caused_by | root_id |
|---|---|---|---|---|---|---|
| T1 | E-0001 | SYN-MISSING-SEMICOLON | 3:14 | a | — | E-0001 |

Summary: raw 1, displayed 1, fatal 1, warning 0.

*T1b reference*: `expect(";")` after `2` finds `a` (3:15) on the same line, so the code is SYN-MISSING-SEMICOLON at 3:14 and recovery is panic. The `VarDecl b` is kept (broken declaration, `error_id = E-0001`). Statement-level panic skips `a = a + b`, consumes `;` and closes the region. Semantics: `b` is never read → WRN-UNUSED-VAR at `b` (3:9), caused by E-0001 via R4.

| Trace | Id | Code | Line:Col | Found | caused_by | root_id |
|---|---|---|---|---|---|---|
| T1b | E-0001 | SYN-MISSING-SEMICOLON | 3:14 | a | — | E-0001 |
| T1b | E-0002 | WRN-UNUSED-VAR | 3:9 | b | E-0001 | E-0001 |

Summary: raw 2, displayed 1, fatal 1, warning 1.

*T2 reference* (uses the §4.7 missing-`}` repair, advisor decision 9). The `}` on line 5 closes the `if` block, so the parser is still inside `f`'s body when it reaches line 6.
1. `statement()` in `f`'s body sees `int` (6:1), then `main` (IDENT), then `(`. §4.7 fires: E-0001 SYN-UNBALANCED-BRACKET at 6:1, `found = int`, `expected = ["}"]`. The message names the `{` on line 1 (the innermost open block, `f`'s body). `f`'s body block is closed with `closed_by_repair = E-0001`, nothing is consumed and no region is opened.
2. The top-level loop parses `int main(void) { return f(3); }` normally. EOF is reached with no open block.
3. Semantics: `f`'s body ends with an `if` that has no `else`, so not every path returns. This gives E-0002 WRN-MISSING-RETURN at `f` (1:5), linked by R8 through `closed_by_repair` to E-0001. `main` exists and `a` is a parameter (exempt), so nothing else is reported.

| Trace | Id | Code | Line:Col | Found | caused_by | root_id |
|---|---|---|---|---|---|---|
| T2 | E-0001 | SYN-UNBALANCED-BRACKET | 6:1 | int | — | E-0001 |
| T2 | E-0002 | WRN-MISSING-RETURN | 1:5 | f | E-0001 | E-0001 |

Summary: raw 2, displayed 1, fatal 1, warning 1. One injected fault gives one root at the next function header, the earliest point where the missing `}` can be proven. Note in §9 that without §4.7 this file would give 2 roots, the first a misleading SYN-MISSING-SEMICOLON. Also note the remaining limitation: a missing `}` in the last function is reported only at EOF.

*T6 reference*:
1. The lexer records E-0001 LEX-INVALID-ESCAPE at the `\` (4:18), found `\q`. The STRING_LIT token is still emitted with the escape removed, so it does not set `lex_gap`.
2. The parser: `count = count + 1` ends at 5:21. `expect(";")` finds `result` (6:5) on a later line → E-0002 SYN-MISSING-SEMICOLON at 5:22 (phrase repair).
3. The analyser: `result` is undeclared → E-0003 SEM-UNDECLARED-VAR at 6:5. No `ErrorStmt` declares `result`, so there is no `caused_by`.

| Trace | Id | Code | Line:Col | Found | caused_by | root_id |
|---|---|---|---|---|---|---|
| T6 | E-0001 | LEX-INVALID-ESCAPE | 4:18 | \q | — | E-0001 |
| T6 | E-0002 | SYN-MISSING-SEMICOLON | 5:22 | result | — | E-0002 |
| T6 | E-0003 | SEM-UNDECLARED-VAR | 6:5 | result | — | E-0003 |

Summary: raw 3, displayed 3, fatal 3, warning 0. This satisfies PRD F1's acceptance test (three records, one per phase, correct positions) **only because** the semantic analyser runs on the partial AST (invariant 1).

T3, T4, T5 and T7 have no reference. Trace them yourself and mark them `n/a`. Every record in them must follow from a §3–§7 rule you can name in the narrative.

After the tables, add a sentence confirming that no trace triggered the loop guard (§4.6 point 3). Then list any trace whose result surprised you, with the reason.

**Verify**:
- `grep -cE '^\| T[0-9]+b? \| [0-9]+ \|' docs/error-recovery.md` → `8` (summary rows)
- `grep -cE '^\| T[0-9]+b? \| E-[0-9]{4} \|' docs/error-recovery.md` → at least `16` (8 reference rows, plus at least 1 for T3, 5 for T4, 1 for T5 and 1 for T7)
- `grep -c '^| T1 | E-0001 | SYN-MISSING-SEMICOLON | 3:14 | a | — | E-0001 |$' docs/error-recovery.md` → `1`
- `grep -c '^| T6 | E-0003 | SEM-UNDECLARED-VAR | 6:5 | result | — | E-0003 |$' docs/error-recovery.md` → `1`
- `grep -c '^| T2 | E-0001 | SYN-UNBALANCED-BRACKET | 6:1 | int | — | E-0001 |$' docs/error-recovery.md` → `1`
- `grep -c '^| T2 | E-0002 | WRN-MISSING-RETURN | 1:5 | f | E-0001 | E-0001 |$' docs/error-recovery.md` → `1`
- `grep -cE '^\| T6 \| 3 \| 3 \|' docs/error-recovery.md` → `1`
- `grep -c '^```c$' docs/error-recovery.md` → `8`
- Commit: `docs: add hand-traced recovery examples (plan 002 step 5)`

### Step 6: Write §10 F2 feasibility and §11 Interface

**§10 F2 feasibility**: begin with one line in exactly this form:
`**F2 acceptance as written is not reachable.**` (or `**F2 acceptance as written is reachable.**` if your traces prove otherwise. If so, explain which trace gives ≥ 10 raw records from one missing `;`).

Then argue from T1 and T1b, in this order:
1. With phrase repair, a missing `;` before a line break yields exactly 1 raw record (T1). On the same line it yields a handful at most (T1b: 2). No design in this document produces ≥ 10 raw records from one missing `;`, and decision 8 forbids a naive mode that would. The PRD's premise ("previously produced 10 or more errors") describes an unrecovering compiler, not this one. The conclusion "shows 1 root cause" holds trivially.
2. The success metric ("≥ 70% fewer displayed errors on cascading test files") is also at risk. A file with raw 2 and displayed 1 is only a 50% reduction. The metric depends on which files count as "cascading", so the corpus plan must fix the file list before anything is measured.
3. Propose corrected acceptance wording in a quoted block. Use this text, or improve it without weakening it:
> **F2 acceptance (proposed):** (a) A file with one missing semicolon shows exactly 1 root cause, and that root is SYN-MISSING-SEMICOLON at the position immediately after the unterminated statement. (b) For every single-fault file in the cascade set (files whose raw count is ≥ 2), the displayed count is 1 and the root is the injected fault. The cascade set is fixed before measurement and includes at least: an undeclared variable used ≥ 5 times, a lexical error inside an expression, a missing `(` after `if`/`while`, a broken `for` header whose loop variable is used in the body, and a missing `}`. (c) The clustering metric is reported as raw vs displayed counts summed over the cascade set, together with the per-file table.
4. State that with the §4.7 repair, part (b) holds for the missing-`}` file (T2: raw 2, displayed 1). A missing `}` in the *last* function is detected only at EOF, but it is still a single root.

**§11 Interface for later milestones**: bullet list:
- Milestone 1 parser: implements §3–§5 and records `caused_by` for R1/R2. The analyser implements §6 and R3–R8. Each trace in §9 becomes a pytest case in the corpus, asserting the exact record table.
- F2: reads `caused_by` and assigns `root_id` (provisional rule in §7).
- F8: the verifier compares records before and after a patch. Because records are deterministic (invariant 5), "the original error is gone" can be checked by `(code, line, column)` of the root record (adjusted for lines the patch adds or removes). This is to be specified by the F8 plan.

**Verify**:
- `grep -cE '^\*\*F2 acceptance as written is (not )?reachable\.\*\*$' docs/error-recovery.md` → `1`
- `grep -c 'F2 acceptance (proposed)' docs/error-recovery.md` → `1`
- `grep -c 'TODO (plan 002' docs/error-recovery.md` → `0`
- Commit: `docs: assess F2 feasibility and record milestone interface (plan 002 step 6)`

### Step 7: Write the ADR `docs/decisions/0002-error-recovery-and-cascade-linking.md`

Title line: `# ADR 0002: Error recovery and cascade linking`. Then exactly five `##` sections, in this order, with these exact heading texts: `## Status`, `## Context`, `## Decision`, `## Consequences`, `## Still open`.
- **Status**: `Accepted, 2026-10-10.` Depends on ADR 0001.
- **Context**: F1 needs every phase to run (3 errors → 3 records). F2 needs a mechanical cause signal. F8 needs deterministic records. Quote the PRD risk row about panic-mode recovery points. Plan 001 deferred this decision.
- **Decision**: one bullet per advisor decision 1–9 (from "Current state"), each pointing to its section in `docs/error-recovery.md`. Include your §4.3 YES/NO decision, marked as decided by the executor.
- **Consequences**: missing `;` gives few raw errors, so F2's acceptance wording must change (§10). A missing `}` is caught at the next function header by the §4.7 repair (T2: 1 root). The raw count is post-recovery and is not comparable to gcc. Undeclared names produce one record per use, unlike gcc (which reports once per function). Plan 003 must use the location convention and §8.
- **Still open** (one bullet each):
  - (1) Whether F2 should also group errors after a missing `}` in the last function (detected only at EOF).
  - (2) The PRD F2 acceptance wording and the 70% metric (§10).
  - (3) None for locations: EOF, SEM-MISSING-MAIN and "first character of the rejected lexeme" were confirmed by the advisor and agree with plan 003.
  - (4) Precision of R4 and R6 (they may link a warning that a correct parse would also have produced). Measure it on the corpus.
  - (5) Whether the `<error>` type should absorb type checks (§6) or record linked errors.
- End with: "The owner should add the corrected F2 acceptance wording to the PRD (see `docs/error-recovery.md` §10)."

**Verify**:
- `grep -cE '^## (Status|Context|Decision|Consequences|Still open)$' docs/decisions/0002-error-recovery-and-cascade-linking.md` → `5`
- `grep -c '^## ' docs/decisions/0002-error-recovery-and-cascade-linking.md` → `5`
- Commit: `docs: add ADR 0002 on error recovery and cascade linking (plan 002 step 7)`

### Step 8: Final verification (no commit)

Run every Done-criteria command and confirm each result.

**Verify**: all Done criteria hold.

## Test plan

There is no code to test, so the "tests" are the hand traces and the structural checks:
- The 8 traces in §9 are the test cases. T1, T1b, T2 and T6 have advisor reference answers and are checked by exact-row greps. Milestone 1 will turn every §9 trace into a pytest case that asserts the exact record table. That is why the tables must be exact and every row must follow from a named rule.
- Consistency check: the "codes used ⊆ catalog" command (see Commands) must print nothing, which proves no new error code was invented.
- Self-check before Step 8: for each record row in T3, T4, T5 and T7, confirm you can name the rule (§3 table row, §4.x, or R1–R8) that produced it and its `caused_by`. If you can't name one, the row is wrong or the design has a gap. Report a gap; do not paper over it.

## Done criteria

All must hold:

- [ ] `git diff --name-only main..HEAD` lists exactly `docs/decisions/0002-error-recovery-and-cascade-linking.md` and `docs/error-recovery.md`
- [ ] `git log --format=%s main..HEAD` shows 6 commits, each ending `(plan 002 step N)` for N = 2..7
- [ ] `git log --format=%B main..HEAD | grep -c '^Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>$'` → `6`
- [ ] `grep -c '^## ' docs/error-recovery.md` → `11` and `grep -c 'TODO (plan 002' docs/error-recovery.md` → `0`
- [ ] `grep -cE '^(SYNC_STMT_CONSUME|SYNC_STMT_STOP|SYNC_FOR_HEADER|SYNC_BLOCK|SYNC_TOP_STOP) ' docs/error-recovery.md` → `5`
- [ ] `grep -cE '^\| R[1-8] ' docs/error-recovery.md` → `8`; `grep -cE '^\| S([1-9]|10) \|' docs/error-recovery.md` → `10`; `grep -cE '^\| LEX-' docs/error-recovery.md` → `7`
- [ ] `grep -cE '^\| T[0-9]+b? \| [0-9]+ \|' docs/error-recovery.md` → `8`, and the three exact reference-row greps from Step 5 each → `1`
- [ ] `grep -cE "^Decision \(missing '\)' before '\{'\): (YES|NO) " docs/error-recovery.md` → `1`
- [ ] `grep -cE '^\*\*F2 acceptance as written is (not )?reachable\.\*\*$' docs/error-recovery.md` → `1`
- [ ] `grep -cE '^## (Status|Context|Decision|Consequences|Still open)$' docs/decisions/0002-error-recovery-and-cascade-linking.md` → `5`
- [ ] The "codes used ⊆ catalog" command prints nothing
- [ ] `python -I tools/check_spec.py` still prints `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`
- [ ] `git status --porcelain -- docs tools plans README.md "cd project prd.docx"` shows nothing staged or modified by you (the advisor's own uncommitted `VIVA.md`/`plans/README.md` edits, if present, are untouched and unstaged)

## STOP conditions

Stop and report back (do not improvise) if:

- The drift check fails, `docs/language-spec.md` or `docs/error-catalog.md` is missing, `tools/check_spec.py` does not print the OK line, or plan 001's docs disagree with the grammar, codes or code-selection rules quoted in "Current state".
- A trace shows a possible infinite loop: a state where a loop iteration consumes no token and the loop guard would fire, or panic could stop on the same token twice in a row. Report the program and the state. Do not add sync tokens to fix it.
- The design seems to need a **new error code** (or a change to an existing code's phase, severity or message). Report the case and the code you would want.
- Your trace of T1, T1b, T2 or T6 differs from the advisor's reference, and the difference comes from a flaw in the design (two rules contradict, or a rule is undefined for the case), not from an error in the reference.
- You find a record in any trace whose `caused_by` you can't justify by one of R1–R8, but which is clearly a cascade. Report it as a design gap. Do not invent R9.
- Completing a step seems to require editing an out-of-scope file.

## Maintenance notes

- **Milestone 1 (lexer/parser/analyser plan)** implements this document literally. The §9 tables become exact-match pytest cases. Any implementation deviation must update §9 and this ADR first.
- **F2 plan**: starts from the provisional root rule in §7 and must decide the PRD "same statement or block" rule. Watch for false merges.
- **F8 plan**: relies on determinism (invariant 5) to compare records before and after a patch.
- **Corpus plan**: the cascade set in §10's proposed wording must be fixed before the 70% metric is measured.
- **Reviewer focus**: the §4.3 YES/NO justification; R4 and R6 (the weakest "known causality" rules); the §4.7 missing-`}` repair (it must never fire on valid code); and the exact sync sets.
- **Viva notes**: end your final report with a bullet list of every decision you made (at least: §4.3, any wording interpretation, anything in §9 that surprised you). The advisor folds them into `VIVA.md`.
