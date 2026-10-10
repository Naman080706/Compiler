# Plan 005: Build the milestone-1 foundation: error records, catalog, error interceptor (F1/F4) and lexer

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md`, unless a reviewer dispatched you and told you they
> maintain the index. End your final report with a **Viva notes** list: the
> decisions, trade-offs or deviations an examiner might ask about (see
> `plans/README.md`, "Viva notes convention"). Do not edit `VIVA.md`; the
> advisor folds your notes into it.
>
> Every code block in this plan is the exact content to write. Copy it
> verbatim. Do not "improve" it, reformat it or add features. If a verification
> fails, the code you wrote differs from the plan, or the plan is wrong. Compare
> first, and STOP if the plan is wrong.
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat 1bbfed4..HEAD -- src tests/unit` must print **nothing**.
> 2. `test -e src && echo EXISTS || echo absent` must print `absent`.
> 3. `grep -cE '^\| (LEX|SYN|SEM|WRN)-' docs/error-catalog.md` must print `37`.
>
> If check 1 or 2 fails, someone has already started this work: STOP and
> report. If check 3 fails, the catalog has changed: STOP and report. HEAD may be
> later than `1bbfed4` because of unrelated commits (for example to `plans/`).
> That is expected; only the paths in check 1 must be unchanged.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (new code only; nothing existing is modified except the `plans/README.md` status row)
- **Depends on**: `plans/001-define-c-subset-and-error-catalog.md`, `plans/002-design-error-recovery-strategy.md`, `plans/003-build-test-corpus-and-harness.md` (all merged into `main`). Plan 004 is merged and does not affect lexing.
- **Category**: direction (milestone 1, first of three plans: 005 → 006 → 007)
- **Planned at**: commit `1bbfed4`, 2026-10-10 (revised after the advisor's review; plan 004 is already merged)

## Why this matters

The project is the "Compiler Error Assistant": a course compiler for a strict C99 subset, written in Python, that records every error as a structured record for an AI layer to explain. No compiler code exists yet. PRD F1 requires **one error interceptor** that turns every phase's errors into records ("No phase may print directly to the console"). PRD F4 requires that the **severity label come from the compiler phase and rule, never from the AI**. This plan builds the foundation the parser (plan 006) and the semantic analyser (plan 007) stand on: the record type, the catalog loader (severity, phase and message come from `docs/error-catalog.md`), the `ErrorSink` interceptor (the only way to create a record), the token types, and the complete lexical phase with the recovery rules of `docs/error-recovery.md` §3. When it lands, the seven lexical corpus programs (`tests/corpus/dev/001`–`007`) already produce their expected root records, and every valid corpus program lexes with zero records.

## Current state

- Repo: `C:\Users\Naman\OneDrive\Desktop\Compiler project`, branch `main`, HEAD `1bbfed4`, no remote. Windows 11, Git Bash, Python 3.13.1 as `python`. **There is no `src/` folder and no compiler code.**
- `pyproject.toml` already sets `pythonpath = ["src"]` and `testpaths = ["tests"]` for pytest, and `addopts = "-m 'not heldout'"`. `requirements-dev.txt` holds only `pytest>=8,<9`. **pytest is not installed globally**: it lives in `.venv/` (git-ignored), which may not exist yet (step 0 creates it).
- `git config core.autocrlf` is `true`. **The corpus `.c` files are checked out with CRLF line endings** (`file tests/corpus/dev/001-stray-at-sign.c` → `C source, ASCII text, with CRLF line terminators`). The lexer must treat `\r\n` as one newline. This plan's corpus tests read the files as raw bytes so they exercise CRLF.
- Existing tests (do not modify them): `tests/test_corpus_schema.py` (runs now), `tests/test_corpus_compile.py` (begins with `pipeline = pytest.importorskip("cea.pipeline")`, so it is **skipped until `src/cea/pipeline.py` exists**; plan 007 creates that file; this plan must not), `tests/test_gcc_crosscheck.py` (marker `gcc`, runs gcc over the whole corpus; it runs in the default suite and skips itself if gcc is not on PATH), `tests/corpus_lib.py` (helpers). There is no `tests/__init__.py`; test modules are imported by basename, so this plan does **not** create `tests/unit/__init__.py`.

### The binding contract: `plans/m1-architecture.md`

This plan implements §1–§3 and §6 of that file. Names, fields, signatures and types below are fixed by it. The advisor amended §2 and §3 during review of this plan (phase-dependent quoting, zero-width default `span_end`, `load_grammar_rules()`, newline and directive rules); the excerpts below are the amended text. Excerpts:

> | `src/cea/__init__.py` | 005 | Package docstring only. |
> | `src/cea/catalog.py` | 005 | Parse `docs/error-catalog.md` into `CatalogEntry` objects. |
> | `src/cea/records.py` | 005 | `Position`, `ErrorRecord`. |
> | `src/cea/diagnostics.py` | 005 | `ErrorSink`, the **error interceptor** (PRD F1). It is the only way to create a record. |
> | `src/cea/tokens.py` | 005 | `TokenKind`, `Token`, keyword and operator tables. |
> | `src/cea/lexer.py` | 005 | `lex()`: the lexical phase and recovery (`docs/error-recovery.md` §3). |
> | `src/cea/pipeline.py` | 007 | `compile_source()`, `CompileResult`. **Created last**: its existence switches on `tests/test_corpus_compile.py`. |
>
> **Rule (PRD F1: "No phase may print directly to the console").** No module except `cli.py` may call `print(` or write to `sys.stdout`/`sys.stderr`. Plan 005 adds a test that greps `src/cea/*.py` for `print(` and allows it only in `cli.py`.

Contract §2 signatures added in review (quoted):

> `def load_grammar_rules(path: Path | None = None) -> frozenset[str]: ...   # the 36 rule names of language-spec §2 ebnf block; used to validate syntax rule_refs`
>
> `span_end: Position | None = None,     # default: zero-width Position(line, column) if found == "EOF" or code == "SYN-MISSING-SEMICOLON"; otherwise Position(line, column + max(len(found),1) - 1)`

`report()` rules (contract §2, quoted):

> - `phase`, `severity` and the default `rule_ref` come from the catalog. If the catalog's `rule_ref` is `<production>`, a `rule_ref` argument is required, and it must be a grammar rule name.
> - `id` is `f"E-{n:04d}"` in creation order. `root_id` is set to `id`. `language` is set to `"c"`.
> - `snippet` is the source lines `max(1, line-1) .. min(last, line+1)`, joined with `"\n"` and otherwise unmodified.
> - `message` is the template formatted with `found`, `expected` and the `message_args`. `{expected}` renders as the items joined by `" or "`. **Only for codes whose catalog phase is `syntax`**, each item is wrapped in single quotes, unless the template already writes `'{expected}'`. For lexical and semantic codes the items are inserted raw (they are type names, counts or names: "expects 2 argument(s)", not "expects '2' argument(s)"). `{found}` is always inserted raw (the templates already quote it where needed). Formatting is **strict**: a missing placeholder raises `KeyError`.
> - An unknown code raises `KeyError`.

Contract §3 (quoted): "The EOF token's position is immediately after the last token (end line, end column + 1), or 1:1 for an empty file (error-recovery §8). Columns count characters, and a tab counts as one column." `LexResult.tokens` "always ends with exactly one EOF token"; `stdio_include` is the "position of the '#' of the first accepted '#include <stdio.h>', else None". `Token.value`: "INT_LIT -> int, FLOAT_LIT -> float, CHAR_LIT -> str (1 char), STRING_LIT -> str (escapes decoded)". Newlines: CRLF, LF and a lone CR each count as one newline, and CR never occupies a column.

Contract §3, directives (quoted): "`#include <stdio.h>` is accepted when `#` is the first non-blank character of the line, with spaces or tabs allowed around the parts. It may be followed on the same line by whitespace and/or a comment (`// …`, or `/* … */` closed on that line), because comments are whitespace (language-spec §1). Anything else after it makes the line LEX-UNSUPPORTED-DIRECTIVE."

Contract §6 conventions: type hints everywhere; `@dataclass` for data; a module docstring on every file; stdlib only; no global mutable state except the `lru_cache`d catalog; unit tests in `tests/unit/test_<module>.py` using plain `assert` and `pytest.mark.parametrize` tables, modelled on `tests/test_corpus_schema.py`; no changes to `docs/` or `tests/corpus/`.

### The catalog (`docs/error-catalog.md`)

One markdown table with 7 columns, `Code | Phase | Severity | Category | rule_ref | Message template | Example trigger`. 37 rows start with `| LEX-`, `| SYN-`, `| SEM-` or `| WRN-`: 7 lexical, 8 syntax, 22 semantic (17 `SEM-` fatal and 5 `WRN-` warnings). Seven `SYN-` rows have rule_ref `<production>`. The seven lexical rows, verbatim:

```
| LEX-INVALID-CHAR | lexical | fatal | malformed-token | `token` | Unexpected character '{found}' | `int x = 5 @ 2;` |
| LEX-UNTERMINATED-STRING | lexical | fatal | unclosed-delimiter | `STRING_LIT` | String literal is not closed before end of line | `printf("hi);` |
| LEX-BAD-CHAR-LITERAL | lexical | fatal | malformed-token | `CHAR_LIT` | A char literal must hold exactly one character, e.g. 'a' | `char c = 'ab';` |
| LEX-UNTERMINATED-COMMENT | lexical | fatal | unclosed-delimiter | `BLOCK_COMMENT` | Block comment starting here is never closed with '*/' | `/* note` at end of file |
| LEX-MALFORMED-NUMBER | lexical | fatal | malformed-token | `number` | '{found}' is not a valid number | `int x = 12abc;` |
| LEX-INVALID-ESCAPE | lexical | fatal | malformed-token | `escape` | Unknown escape sequence '{found}' | `printf("a\q");` |
| LEX-UNSUPPORTED-DIRECTIVE | lexical | fatal | syntax-structure | `directive` | Only '#include <stdio.h>' is supported; '{found}' is not | `#define N 10` |
```

### The lexical grammar (`docs/language-spec.md` §1, excerpt)

```ebnf
IDENT               = letter , { letter | digit } ;   (* not a keyword *)
letter              = "A".."Z" | "a".."z" | "_" ;
INT_LIT             = digit , { digit } ;
FLOAT_LIT           = digit , { digit } , "." , digit , { digit } ;
CHAR_LIT            = "'" , ( char_char | escape ) , "'" ;   (* exactly one character *)
STRING_LIT          = '"' , { string_char | escape } , '"' ;  (* may not span lines *)
escape              = "\" , ( "n" | "t" | "0" | "'" | '"' | "\" ) ;
UNSUPPORTED_OP      = "&" | "|" | "^" | "~" | "<<" | ">>" | "->" | "." | "?" | ":" ;
directive           = "#" , { any char except newline } ;
BLOCK_COMMENT       = "/*" , { any char } , "*/" ;   (* does not nest *)
```

> A `directive` must start a line. The only accepted directive is `#include <stdio.h>` (spaces allowed). The lexer records that it was seen and does not pass it to the parser. Any other directive is the error LEX-UNSUPPORTED-DIRECTIVE.
>
> Unsupported keywords and operators are tokenised normally so the parser can report SYN-UNSUPPORTED-FEATURE with a clear message.

The 12 keywords, 20 unsupported keywords, 22 operators, 10 unsupported operators and 8 punctuators are copied into `tokens.py` in step 3, and a test checks them against the spec file.

### Lexer recovery (`docs/error-recovery.md` §3, verbatim)

> The rule: **record the error, skip the bad input, continue; never pass an error token to the parser.**

| Code | Reported at (first bad character) | Bad input skipped | Token emitted | Sets `lex_gap` on next token |
|---|---|---|---|---|
| LEX-INVALID-CHAR | the character | that one character | none | yes |
| LEX-UNTERMINATED-STRING | the opening `"` | from `"` up to (not including) the end-of-line character | none | yes |
| LEX-BAD-CHAR-LITERAL | the opening `'` | unclosed on its line: up to end of line; closed but empty or more than one character (`''`, `'ab'`): through the closing `'` | none | yes |
| LEX-UNTERMINATED-COMMENT | the `/` of `/*` | everything up to EOF | none | yes (the EOF token) |
| LEX-MALFORMED-NUMBER | the first character of the number | the maximal run of `[A-Za-z0-9_.]` that starts at the number (`12abc`, `1.2.3`, `12.`) | none | yes |
| LEX-INVALID-ESCAPE | the `\` | the two-character escape only. In a STRING_LIT the rest of the literal is lexed normally and the token is emitted with the escape removed from its value. In a CHAR_LIT the whole literal is skipped (a char literal without its one character is not a token). | STRING_LIT: the literal; CHAR_LIT: none | STRING_LIT: no; CHAR_LIT: yes |
| LEX-UNSUPPORTED-DIRECTIVE | the `#` | the rest of the line | none | no (valid directives produce no token either, so the token stream is unchanged) |

> - `lex_gap` is a field on every token: the id of the **last** lexical record whose skipped input lies between the end of the previous token and the start of this token, or `None`.
> - A string with both an invalid escape and no closing quote records both errors (escape first, by position). Neither has `caused_by`. Lexical records never have `caused_by`.
> - Progress: each lexer step consumes at least one character, so the lexer always terminates.

§8 (excerpts): "Lexical errors are reported at the first bad character." "The EOF token's position is immediately after the last token of the file (its end line, end column + 1). For an empty file it is 1:1. `found = "EOF"`." "`span_end`: lexical = last character skipped (for LEX-INVALID-ESCAPE in a string, the escape's second character)".

§9 traces with lexical records (this plan tests their lexical part; plan 007 tests the full traces):

```c
/* T5 */
int main(void) {
    int x = 5 @ 2;
    return x;
}
```
> Lexer, line 2: `@` (2:15) is in no token: E-0001 LEX-INVALID-CHAR, `found = @`. The character is skipped, no token is emitted, and the next token (`2`, 2:17) gets `lex_gap = E-0001`.

```c
/* T6 */
#include <stdio.h>
int main(void) {
    int count = 0;
    printf("total\q\n", count);
    count = count + 1
    result = count;
    return 0;
}
```
> Lexer: line 1 is an accepted `#include <stdio.h>` and produces no token (it sets no `lex_gap`). On line 4, the escape `\q` at 4:18 is not in `escape`: E-0001 LEX-INVALID-ESCAPE, `found = \q`. The STRING_LIT token is still emitted with the escape removed, so no `lex_gap` is set.

### Corpus facts the tests rely on

`tests/corpus/README.md` §4: "**Lexical errors** are at the first bad character. For an unterminated string, char literal or block comment, that is the opening `"`, `'` or `/*`." Sidecar `roots` of the seven lexical dev programs (each has exactly one root, and plan 002's traced raw lexical count is 1 for each):

| File | roots |
|---|---|
| `dev/001-stray-at-sign.c` | `LEX-INVALID-CHAR` line 12 |
| `dev/002-unclosed-printf-string.c` | `LEX-UNTERMINATED-STRING` line 11 |
| `dev/003-two-char-literal.c` | `LEX-BAD-CHAR-LITERAL` line 5 |
| `dev/004-unclosed-todo-comment.c` | `LEX-UNTERMINATED-COMMENT` line 11 |
| `dev/005-number-with-letters.c` | `LEX-MALFORMED-NUMBER` line 4 |
| `dev/006-windows-path-escape.c` | `LEX-INVALID-ESCAPE` line 10 |
| `dev/007-unsupported-include.c` | `LEX-UNSUPPORTED-DIRECTIVE` line 2 |

`tests/corpus/valid/` holds 12 programs. Each starts with `#include <stdio.h>` on line 1 and must lex with zero records. **Never open, read or run anything in `tests/corpus/heldout/`** (corpus README §5); the unit tests in this plan glob only `dev/00[1-7]-*.c` and `valid/*.c`.

### Decisions this plan makes where the docs are silent

These are deliberate. Each is pinned by a test. Report them in your Viva notes.

1. **Newlines.** `\r\n`, `\n` and a lone `\r` are each one newline. A `\r` never occupies a column. `ErrorSink` splits snippet lines by the same rule (`split_lines`), so snippets never contain `\r`. Whitespace is space, tab, `\f`, `\v` and the newline characters; a tab, `\f` and `\v` each count as one column.
2. **Directives** (contract §3, as amended). A `#` starts a directive only if nothing but spaces and tabs precede it on its line. The directive runs to the end of the line. It is accepted only if that text fully matches `#[ \t]*include[ \t]*<stdio\.h>(?:[ \t]|/\*.*?\*/)*(?://.*)?`: after the header name come only blanks, `/* … */` comments **closed on the same line**, and finally an optional `// …` comment. So `#include <stdio.h> // io` and `#include <stdio.h> /* io */` are accepted, while `#include <stdio.h> x` is LEX-UNSUPPORTED-DIRECTIVE. **A `/*` opened after the include and not closed on that line makes the whole line LEX-UNSUPPORTED-DIRECTIVE.** Because the directive owns the rest of its line, that `/*` does not open a comment, and the next line is lexed normally. A `#` after other text on its line is LEX-INVALID-CHAR. A repeated accepted include is not an error; `stdio_include` keeps the first. `found` for a rejected directive is its text with trailing spaces and tabs removed.
3. **Escape at end of line.** In a string, a `\` directly before the end of the line is an ordinary character, so only LEX-UNTERMINATED-STRING is recorded. In a char literal, `\` hides the next character when looking for the closing `'` (`'\''` is valid; `'\';` followed by a newline is unclosed).
4. **Order of the two string records** (confirmed by the advisor). For `"a\q` and a newline, LEX-INVALID-ESCAPE is E-0001 and LEX-UNTERMINATED-STRING is E-0002 (the escape is found while scanning; the doc says "escape first"). The next token's `lex_gap` is E-0002, the last record.
5. **`span_end` of lexical records** is the last skipped character. For an unterminated comment it is the last non-newline character of the file. For LEX-INVALID-ESCAPE in a char literal it is the closing `'`, because the whole literal is skipped.
6. **`found`** is the skipped text, except LEX-UNTERMINATED-COMMENT, where `found = "/*"` (the rest of the file would be useless in a message).
7. **Malformed numbers.** After the longest valid number (`digits` or `digits.digits`), if the next character is a letter, digit, `_` or `.`, the whole maximal run of `[A-Za-z0-9_.]` from the number's start is LEX-MALFORMED-NUMBER. This covers `12abc`, `1.2.3`, `12.`, `1e5`, `0x1F`, `3_000`, `1..2` and `2.5x`. `.5` is the unsupported operator `.` followed by `5`. `007` is INT_LIT with value 7 (C would read it as octal; the compiler never runs code, so the value is informational).
8. **`rule_ref` validation** (accepted by the advisor; `load_grammar_rules()` is now in the contract). `catalog.load_grammar_rules()` reads the 36 rule names from the `ebnf` block of `docs/language-spec.md` §2, and `report()` raises `ValueError` for any `rule_ref` argument outside that set, including an override passed for a code whose catalog `rule_ref` is not `<production>`.
9. **Extra strictness in `report()`.** `expected` given as a bare `str` raises `TypeError` (it would otherwise split into characters). A line or column below 1 raises `ValueError`. A failed `report()` creates no record and uses no id.
10. **`ErrorSink.records`** returns a copy of the list, and `load_catalog()` returns a copy of the cached dict (the entries are shared frozen objects), so no caller can corrupt shared state.

## Commands you will need

All from the project root in Git Bash.

| Purpose | Command | Expected on success |
|---|---|---|
| Create venv (once, only if `.venv/` is missing) | `python -m venv .venv && .venv/Scripts/python -m pip install -q -r requirements-dev.txt` | exit 0 |
| pytest version | `.venv/Scripts/python -m pytest --version` | `pytest 8.x.y` |
| Unit tests | `.venv/Scripts/python -m pytest -q tests/unit` | last line `N passed in …s` (N per step below) |
| Full suite | `.venv/Scripts/python -m pytest -q` | `96 passed, 1 skipped` before this plan (B = 96); `358 passed, 1 skipped` after it |
| One test file | `.venv/Scripts/python -m pytest -q tests/unit/test_lexer.py` | `N passed` |

The full suite deselects the held-out tests through `addopts = "-m 'not heldout'"` in `pyproject.toml` and runs the gcc cross-check (`tests/test_gcc_crosscheck.py`, which takes a while). Do not add `-m "not gcc"`. If gcc is not on PATH, that test skips itself and the counts read `95 passed, 2 skipped` before and `357 passed, 2 skipped` after. The `1 skipped` is `tests/test_corpus_compile.py`, which must stay skipped.

## Scope

**In scope** (create only these, plus the status row in `plans/README.md`):
- `src/cea/__init__.py`
- `src/cea/catalog.py`
- `src/cea/records.py`
- `src/cea/diagnostics.py`
- `src/cea/tokens.py`
- `src/cea/lexer.py`
- `tests/unit/test_catalog.py`
- `tests/unit/test_records.py`
- `tests/unit/test_diagnostics.py`
- `tests/unit/test_tokens.py`
- `tests/unit/test_lexer.py`
- `tests/unit/test_no_print.py`

**Out of scope** (do NOT touch):
- `src/cea/pipeline.py`: **do not create it, not even as a stub.** Its existence switches on `tests/test_corpus_compile.py`, which must stay skipped until plan 007.
- `src/cea/ast.py`, `parser.py`, `semantic.py`, `cli.py`, `__main__.py`: plans 006 and 007.
- `tests/__init__.py`, `tests/unit/__init__.py`, `conftest.py`: not needed (pytest imports test modules by basename, as the existing tests do).
- Anything in `docs/`, `tests/corpus/`, `tools/`, `pyproject.toml`, `requirements-dev.txt`, `VIVA.md`, or the existing `tests/*.py`. A needed spec change is reported, not made (contract §6).
- `tests/corpus/heldout/`: never open it.
- `plans/m1-architecture.md`: if the contract seems wrong, STOP and report.

## Git workflow

- Create the branch from `main`: `git checkout -b advisor/005-m1-foundation`.
- One commit per step (steps 1–7). Stage **by explicit path**, never `git add -A` or `git add .` (the repo has untracked Office lock files such as `~$ project prd.docx`).
- Message style follows the repo's `git log` (lowercase area prefix, e.g. `plans: add milestone-1 architecture contract and plan 004`, `test: add 20 held-out evaluation programs (plan 003 step 7)`). Every message ends with a blank line and then the co-author trailer. Use two `-m` flags, which git joins with a blank line:
  ```bash
  git commit -m "cea: add catalog loader and error records (plan 005 step 1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
- Do NOT push (there is no remote) and do NOT merge into `main`; the reviewer merges.

## Steps

### Step 0: Branch, environment and baseline

1. Run the drift check at the top of this plan.
2. `git checkout -b advisor/005-m1-foundation`
3. If `.venv/Scripts/python` does not exist: `python -m venv .venv && .venv/Scripts/python -m pip install -q -r requirements-dev.txt`
4. Record the baseline: `.venv/Scripts/python -m pytest -q 2>&1 | tail -1`. The advisor measured it at `main` `1bbfed4`: **B = `96 passed, 1 skipped`**.

**Verify**: `git branch --show-current` → `advisor/005-m1-foundation`; `.venv/Scripts/python -m pytest --version` → `pytest 8.…`; the baseline line reads `96 passed, 1 skipped in …s` (or `95 passed, 2 skipped` if gcc is missing). If it has any failure or different numbers, STOP and report.

### Step 1: Package, catalog loader and error records

Create the three source files and two test files below, exactly.

`src/cea/__init__.py`:

````python
"""Compiler Error Assistant (cea): a course compiler for a strict C99 subset.

Every diagnostic is a structured ErrorRecord created through
cea.diagnostics.ErrorSink (PRD F1). The milestone-1 interface contract is
plans/m1-architecture.md.
"""
````

`src/cea/catalog.py`:

````python
"""Load the error catalog (docs/error-catalog.md) and the grammar rule names.

The catalog table is the single source of truth for every code's phase,
severity (PRD F4), category, rule_ref and message template. No code is
hard-coded here: the table is parsed at run time and cached.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = REPO_ROOT / "docs" / "error-catalog.md"
DEFAULT_SPEC_PATH = REPO_ROOT / "docs" / "language-spec.md"
PRODUCTION = "<production>"

_ROW = re.compile(r"^\|\s*(LEX|SYN|SEM|WRN)-")
_RULE_DEF = re.compile(r"^([a-z_]+)\s*=")


@dataclass(frozen=True)
class CatalogEntry:
    code: str
    phase: str
    severity: str
    category: str
    rule_ref: str          # without backticks; "<production>" for dynamic syntax refs
    message_template: str


@functools.lru_cache(maxsize=None)
def _parse_catalog(path: Path) -> dict[str, CatalogEntry]:
    entries: dict[str, CatalogEntry] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not _ROW.match(line):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            raise ValueError(f"{path}:{n}: expected 7 cells, got {len(cells)}")
        code, phase, severity, category, rule_ref, template, _example = cells
        if code in entries:
            raise ValueError(f"{path}:{n}: duplicate code {code}")
        entries[code] = CatalogEntry(code, phase, severity, category, rule_ref, template)
    return entries


def load_catalog(path: Path | None = None) -> dict[str, CatalogEntry]:
    """Return {code: CatalogEntry} in table order. Each path is parsed once (lru_cache)."""
    resolved = Path(path).resolve() if path is not None else DEFAULT_CATALOG_PATH
    return dict(_parse_catalog(resolved))


@functools.lru_cache(maxsize=None)
def _parse_grammar_rules(path: Path) -> frozenset[str]:
    text = path.read_text(encoding="utf-8")
    section = text.index("## 2. Syntax grammar")
    block_start = text.index("```ebnf", section)
    block_end = text.index("```", block_start + len("```ebnf"))
    names = set()
    for line in text[block_start:block_end].splitlines()[1:]:
        m = _RULE_DEF.match(line)
        if m:
            names.add(m.group(1))
    return frozenset(names)


def load_grammar_rules(path: Path | None = None) -> frozenset[str]:
    """Rule names defined in docs/language-spec.md section 2: the valid runtime rule_refs."""
    resolved = Path(path).resolve() if path is not None else DEFAULT_SPEC_PATH
    return _parse_grammar_rules(resolved)
````

`src/cea/records.py`:

````python
"""The structured error record: PRD F1 schema plus docs/error-recovery.md section 2."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    line: int
    column: int


@dataclass
class ErrorRecord:
    # PRD schema fields, in PRD order
    id: str                 # "E-0001", "E-0002", ... in creation order
    phase: str              # "lexical" | "syntax" | "semantic"
    code: str               # a catalog code
    severity: str           # "fatal" | "warning", always from the catalog (PRD F4)
    line: int               # 1-based
    column: int             # 1-based
    found: str              # offending text; "EOF" for the EOF token
    expected: list[str]     # what the failing expect() required; [] if not applicable
    snippet: str            # up to 3 source lines around `line`
    root_id: str            # == id until F2 (milestone 2) assigns clusters
    rule_ref: str           # catalog rule_ref, or the grammar rule for "<production>" rows
    # additions (docs/error-recovery.md section 2)
    language: str           # always "c"
    caused_by: str | None   # set only by rules R1..R8
    span_end: Position      # inclusive end
    message: str            # catalog template with placeholders filled

    def to_dict(self) -> dict:
        """JSON-ready dict in field order; span_end becomes {"line": ..., "column": ...}."""
        return dataclasses.asdict(self)
````

`tests/unit/test_catalog.py`:

````python
"""Unit tests for cea.catalog: parsing docs/error-catalog.md (plan 005, step 1)."""
from collections import Counter

import pytest

from cea.catalog import PRODUCTION, CatalogEntry, load_catalog, load_grammar_rules

PRODUCTION_CODES = {
    "SYN-MISSING-SEMICOLON", "SYN-UNBALANCED-BRACKET", "SYN-EXPECTED-TOKEN",
    "SYN-EXPECTED-EXPRESSION", "SYN-EXPECTED-TYPE", "SYN-UNEXPECTED-EOF",
    "SYN-UNSUPPORTED-FEATURE",
}
WARNING_CODES = {
    "WRN-UNUSED-VAR", "WRN-UNREACHABLE-CODE", "WRN-IMPLICIT-NARROWING",
    "WRN-MISSING-RETURN", "WRN-ASSIGN-IN-CONDITION",
}


def test_catalog_has_37_codes():
    assert len(load_catalog()) == 37


def test_codes_per_phase():
    phases = Counter(e.phase for e in load_catalog().values())
    assert phases == {"lexical": 7, "syntax": 8, "semantic": 22}


def test_severity_comes_from_the_table():
    cat = load_catalog()
    assert {c for c, e in cat.items() if e.severity == "warning"} == WARNING_CODES
    assert {e.severity for e in cat.values()} == {"fatal", "warning"}


def test_code_prefix_matches_phase():
    prefix_phase = {"LEX": "lexical", "SYN": "syntax", "SEM": "semantic", "WRN": "semantic"}
    for code, e in load_catalog().items():
        assert e.code == code
        assert e.phase == prefix_phase[code[:3]], code


def test_backticks_are_stripped():
    cat = load_catalog()
    assert cat["LEX-INVALID-CHAR"].rule_ref == "token"
    assert cat["SEM-UNDECLARED-VAR"].rule_ref == "sem.declare_before_use"
    assert all("`" not in e.rule_ref for e in cat.values())


def test_production_rows():
    cat = load_catalog()
    assert {c for c, e in cat.items() if e.rule_ref == PRODUCTION} == PRODUCTION_CODES
    assert cat["SYN-INVALID-ASSIGN-TARGET"].rule_ref == "assignment"


@pytest.mark.parametrize("code,template", [
    ("LEX-INVALID-CHAR", "Unexpected character '{found}'"),
    ("LEX-UNSUPPORTED-DIRECTIVE", "Only '#include <stdio.h>' is supported; '{found}' is not"),
    ("SYN-UNBALANCED-BRACKET",
     "Expected '{expected}' to close '{opener}' from line {open_line} but found '{found}'"),
    ("SYN-EXPECTED-TOKEN", "Expected {expected} but found '{found}'"),
    ("WRN-ASSIGN-IN-CONDITION", "Assignment used as a condition; did you mean '=='?"),
])
def test_message_templates(code, template):
    assert load_catalog()[code].message_template == template


def test_category_column():
    cat = load_catalog()
    assert cat["LEX-UNTERMINATED-COMMENT"].category == "unclosed-delimiter"
    assert cat["SEM-REDECLARED"].category == "redeclaration"


def test_table_order_is_kept():
    codes = list(load_catalog())
    assert codes[0] == "LEX-INVALID-CHAR" and codes[-1] == "WRN-ASSIGN-IN-CONDITION"


def test_cached_entries_are_shared_but_dict_is_a_copy():
    a, b = load_catalog(), load_catalog()
    assert a is not b
    assert a["LEX-INVALID-CHAR"] is b["LEX-INVALID-CHAR"]


def test_explicit_path(tmp_path):
    p = tmp_path / "cat.md"
    p.write_text(
        "| Code | Phase | Severity | Category | rule_ref | Message template | Example trigger |\n"
        "|---|---|---|---|---|---|---|\n"
        "| LEX-X | lexical | fatal | malformed-token | `token` | Bad '{found}' | `@` |\n",
        encoding="utf-8",
    )
    assert load_catalog(p) == {
        "LEX-X": CatalogEntry("LEX-X", "lexical", "fatal", "malformed-token", "token", "Bad '{found}'"),
    }


def test_row_with_wrong_cell_count_raises(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text("| LEX-X | lexical | fatal | token | Bad |\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_catalog(p)


def test_grammar_rule_names():
    rules = load_grammar_rules()
    assert len(rules) == 36
    assert {"program", "statement", "var_decl", "assignment", "primary"} <= rules
    assert "token" not in rules          # lexical rules (section 1) are not syntax rule_refs
````

`tests/unit/test_records.py`:

````python
"""Unit tests for cea.records (plan 005, step 1)."""
import dataclasses
import json

import pytest

from cea.records import ErrorRecord, Position

FIELD_ORDER = [
    "id", "phase", "code", "severity", "line", "column", "found", "expected", "snippet",
    "root_id", "rule_ref", "language", "caused_by", "span_end", "message",
]


def _record(**over):
    base = dict(
        id="E-0001", phase="lexical", code="LEX-INVALID-CHAR", severity="fatal", line=2,
        column=15, found="@", expected=[], snippet="a\nb\nc", root_id="E-0001", rule_ref="token",
        language="c", caused_by=None, span_end=Position(2, 15), message="Unexpected character '@'",
    )
    base.update(over)
    return ErrorRecord(**base)


def test_field_names_and_order_follow_the_contract():
    assert [f.name for f in dataclasses.fields(ErrorRecord)] == FIELD_ORDER


def test_position_is_frozen_and_hashable():
    p = Position(3, 4)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.line = 5
    assert {p, Position(3, 4)} == {p}


def test_to_dict_is_json_ready():
    d = _record(expected=[";"], caused_by="E-0000").to_dict()
    assert list(d) == FIELD_ORDER
    assert d["span_end"] == {"line": 2, "column": 15}
    assert d["expected"] == [";"]
    assert json.loads(json.dumps(d)) == d
````

**Verify**:
- `.venv/Scripts/python -c "import sys; sys.path.insert(0, 'src'); from cea.catalog import load_catalog, load_grammar_rules; print(len(load_catalog()), len(load_grammar_rules()))"` → `37 36`. If the first number is not 37, STOP (STOP condition 2).
- `.venv/Scripts/python -m pytest -q tests/unit` → `20 passed`
- Commit: `git add src/cea/__init__.py src/cea/catalog.py src/cea/records.py tests/unit/test_catalog.py tests/unit/test_records.py` then `git commit -m "cea: add catalog loader and error records (plan 005 step 1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`

### Step 2: The error interceptor `ErrorSink`

`ErrorSink.report()` is the only way to create an `ErrorRecord`. It looks the code up in the catalog (unknown code → `KeyError`), takes phase, severity and the default `rule_ref` from the catalog (PRD F4), numbers the record `E-0001`, `E-0002`, … in creation order, sets `root_id = id` and `language = "c"`, cuts the 3-line snippet, and formats the message strictly. The `{expected}` quoting rule lives in `render_expected(template, expected, phase)`: items are quoted only when the phase is `syntax` and the template does not literally contain `'{expected}'`; otherwise they are joined raw (so SEM-ARG-COUNT reads `'add' expects 2 argument(s) but got 1`). `{found}` is always raw. When `span_end` is not given, it is zero-width (`Position(line, column)`) for `found == "EOF"` or code SYN-MISSING-SEMICOLON (error-recovery §8), and otherwise ends at the last character of `found`. All validation happens before the id is assigned, so a failed call leaves no record.

`src/cea/diagnostics.py`:

````python
"""ErrorSink: the error interceptor (PRD F1).

It is the only way to create an ErrorRecord. Phase, severity (PRD F4) and the
default rule_ref come from the catalog, never from the caller. Nothing in this
module writes to the console.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from cea.catalog import PRODUCTION, CatalogEntry, load_catalog, load_grammar_rules
from cea.records import ErrorRecord, Position

_NEWLINE = re.compile(r"\r\n|\r|\n")
ZERO_WIDTH_CODE = "SYN-MISSING-SEMICOLON"   # reported just after the last token, so zero-width


def split_lines(source: str) -> list[str]:
    """Split on CRLF, CR or LF (the lexer's newline rule). A final newline adds no line."""
    lines = _NEWLINE.split(source)
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return lines


def render_expected(template: str, expected: Sequence[str], phase: str) -> str:
    """Join items with " or ".

    Only syntax codes quote each item, and only when the template does not
    already write '{expected}'. Lexical and semantic items (type names, counts)
    are inserted raw: "expects 2 argument(s)", not "expects '2' argument(s)".
    """
    if phase != "syntax" or "'{expected}'" in template:
        return " or ".join(expected)
    return " or ".join(f"'{item}'" for item in expected)


class ErrorSink:
    """Collects ErrorRecords in creation order. Ids are E-0001, E-0002, ..."""

    def __init__(self, source: str, catalog: dict[str, CatalogEntry] | None = None):
        self._lines = split_lines(source)
        self._catalog = catalog if catalog is not None else load_catalog()
        self._records: list[ErrorRecord] = []

    def report(self, code: str, line: int, column: int, *,
               found: str,
               expected: Sequence[str] = (),
               span_end: Position | None = None,
               caused_by: str | None = None,
               rule_ref: str | None = None,
               **message_args: object) -> ErrorRecord:
        entry = self._catalog[code]                      # unknown code -> KeyError
        if isinstance(expected, str):
            raise TypeError("expected must be a sequence of strings, not one str")
        if line < 1 or column < 1:
            raise ValueError(f"positions are 1-based, got {line}:{column}")
        if rule_ref is None:
            if entry.rule_ref == PRODUCTION:
                raise ValueError(f"{code} needs a rule_ref argument (catalog rule_ref is {PRODUCTION})")
            rule_ref = entry.rule_ref
        elif rule_ref not in load_grammar_rules():
            raise ValueError(f"rule_ref {rule_ref!r} is not a rule of docs/language-spec.md section 2")
        expected_list = list(expected)
        # Strict formatting: a placeholder with no value raises KeyError (a programming error).
        message = entry.message_template.format(
            found=found,
            expected=render_expected(entry.message_template, expected_list, entry.phase),
            **message_args,
        )
        if span_end is None:
            if found == "EOF" or code == ZERO_WIDTH_CODE:
                span_end = Position(line, column)          # zero-width (error-recovery section 8)
            else:
                span_end = Position(line, column + max(len(found), 1) - 1)
        rec_id = f"E-{len(self._records) + 1:04d}"
        record = ErrorRecord(
            id=rec_id, phase=entry.phase, code=code, severity=entry.severity,
            line=line, column=column, found=found, expected=expected_list,
            snippet=self._snippet(line), root_id=rec_id, rule_ref=rule_ref,
            language="c", caused_by=caused_by, span_end=span_end, message=message,
        )
        self._records.append(record)
        return record

    def _snippet(self, line: int) -> str:
        lo = max(1, line - 1)
        hi = min(len(self._lines), line + 1)
        return "\n".join(self._lines[lo - 1:hi])

    @property
    def records(self) -> list[ErrorRecord]:
        """A copy of the records, in creation order."""
        return list(self._records)

    def summary(self) -> str:
        """PRD F4 count line, e.g. "2 fatal, 3 warnings" / "1 fatal, 1 warning"."""
        fatal = sum(1 for r in self._records if r.severity == "fatal")
        warnings = sum(1 for r in self._records if r.severity == "warning")
        return f"{fatal} fatal, {warnings} warning{'' if warnings == 1 else 's'}"
````

`tests/unit/test_diagnostics.py`:

````python
"""Unit tests for cea.diagnostics.ErrorSink, the error interceptor (plan 005, step 2)."""
import json

import pytest

from cea.catalog import CatalogEntry
from cea.diagnostics import ErrorSink, render_expected, split_lines
from cea.records import Position

FIVE_LINES = "l1\nl2\nl3\nl4\nl5\n"


def test_ids_root_id_language_in_creation_order():
    sink = ErrorSink("x\n")
    a = sink.report("LEX-INVALID-CHAR", 1, 1, found="@")
    b = sink.report("SEM-UNDECLARED-VAR", 1, 1, found="x", name="x", caused_by="E-0001")
    assert [r.id for r in sink.records] == ["E-0001", "E-0002"]
    assert (a.root_id, b.root_id) == ("E-0001", "E-0002")
    assert (a.language, b.language) == ("c", "c")
    assert (a.caused_by, b.caused_by) == (None, "E-0001")


def test_ids_have_four_digits_past_nine():
    sink = ErrorSink("x")
    for _ in range(10):
        sink.report("LEX-INVALID-CHAR", 1, 1, found="@")
    assert sink.records[-1].id == "E-0010"


@pytest.mark.parametrize("code,phase,severity,rule_ref", [
    ("LEX-MALFORMED-NUMBER", "lexical", "fatal", "number"),
    ("SYN-INVALID-ASSIGN-TARGET", "syntax", "fatal", "assignment"),
    ("SEM-UNDECLARED-VAR", "semantic", "fatal", "sem.declare_before_use"),
    ("WRN-UNUSED-VAR", "semantic", "warning", "sem.unused_declaration"),
])
def test_phase_severity_rule_ref_come_from_the_catalog(code, phase, severity, rule_ref):
    rec = ErrorSink("x").report(code, 1, 1, found="x", name="x")
    assert (rec.phase, rec.severity, rec.rule_ref) == (phase, severity, rule_ref)


@pytest.mark.parametrize("source,line,snippet", [
    (FIVE_LINES, 1, "l1\nl2"),
    (FIVE_LINES, 3, "l2\nl3\nl4"),
    (FIVE_LINES, 5, "l4\nl5"),
    (FIVE_LINES.replace("\n", "\r\n"), 3, "l2\nl3\nl4"),
    ("only", 1, "only"),
    ("", 1, ""),
    ("a\n\tb  \nc", 2, "a\n\tb  \nc"),
])
def test_snippet_is_up_to_three_unmodified_lines(source, line, snippet):
    assert ErrorSink(source).report("LEX-INVALID-CHAR", line, 1, found="@").snippet == snippet


@pytest.mark.parametrize("source,lines", [
    ("", [""]),
    ("a", ["a"]),
    ("a\n", ["a"]),
    ("a\r\nb\r\n", ["a", "b"]),
    ("a\rb", ["a", "b"]),
    ("a\n\n", ["a", ""]),
])
def test_split_lines(source, lines):
    assert split_lines(source) == lines


@pytest.mark.parametrize("template,expected,phase,rendered", [
    ("Expected {expected} but found '{found}'", [";"], "syntax", "';'"),
    ("Expected {expected} but found '{found}'", [")", ";"], "syntax", "')' or ';'"),
    ("Expected '{expected}' to close", [")"], "syntax", ")"),
    ("Expected '{expected}' to close", [")", "]"], "syntax", ") or ]"),
    ("Expected {expected}", [], "syntax", ""),
    ("expects {expected} argument(s)", ["2"], "semantic", "2"),
    ("where {expected} is required", ["int", "double"], "semantic", "int or double"),
    ("got {expected}", ["x"], "lexical", "x"),
])
def test_render_expected_quoting_rule(template, expected, phase, rendered):
    assert render_expected(template, expected, phase) == rendered


@pytest.mark.parametrize("code,kwargs,message", [
    ("LEX-INVALID-CHAR", dict(found="@"), "Unexpected character '@'"),
    ("LEX-INVALID-ESCAPE", dict(found="\\q"), "Unknown escape sequence '\\q'"),
    ("SYN-EXPECTED-TOKEN", dict(found="x", expected=["("], rule_ref="if_stmt"),
     "Expected '(' but found 'x'"),
    ("SYN-UNBALANCED-BRACKET",
     dict(found="{", expected=[")"], rule_ref="while_stmt", opener="(", open_line=3),
     "Expected ')' to close '(' from line 3 but found '{'"),
    ("SYN-MISSING-SEMICOLON", dict(found="result", expected=[";"], rule_ref="expr_stmt",
                                   context="the expression statement"),
     "Expected ';' after the expression statement but found 'result'"),
    ("SYN-UNEXPECTED-EOF", dict(found="EOF", expected=["}"], rule_ref="block", context="a block"),
     "File ended inside a block; expected '}'"),
    ("SEM-UNDECLARED-VAR", dict(found="result", name="result"),
     "Variable 'result' is used before it is declared"),
    ("WRN-UNREACHABLE-CODE", dict(found="printf"), "This statement can never run"),
    # semantic templates: {expected} and {found} are inserted raw (no quotes added)
    ("SEM-ARG-COUNT", dict(found="1", expected=["2"], name="add"),
     "'add' expects 2 argument(s) but got 1"),
    ("SEM-TYPE-MISMATCH", dict(found="double", expected=["int"]),
     "Cannot use double where int is required"),
    ("SEM-ARG-TYPE", dict(found="char", expected=["double"], index=2, name="area"),
     "Argument 2 of 'area' must be double but is char"),
    ("SEM-RETURN-TYPE", dict(found="int", expected=["void"], name="log_it"),
     "Function 'log_it' returns void but this returns int"),
    ("WRN-IMPLICIT-NARROWING", dict(found="double", expected=["int"]),
     "double value converted to int; the fractional part is lost"),
])
def test_message_is_the_filled_template(code, kwargs, message):
    assert ErrorSink("x").report(code, 1, 1, **kwargs).message == message


def test_missing_placeholder_raises_key_error():
    with pytest.raises(KeyError):
        ErrorSink("x").report("SEM-UNDECLARED-VAR", 1, 1, found="y")        # no name=


def test_unknown_code_raises_key_error():
    with pytest.raises(KeyError):
        ErrorSink("x").report("LEX-NOPE", 1, 1, found="@")


def test_production_code_requires_rule_ref():
    with pytest.raises(ValueError):
        ErrorSink("x").report("SYN-EXPECTED-EXPRESSION", 1, 1, found=";")


def test_rule_ref_must_be_a_grammar_rule():
    with pytest.raises(ValueError):
        ErrorSink("x").report("SYN-EXPECTED-EXPRESSION", 1, 1, found=";", rule_ref="not_a_rule")
    rec = ErrorSink("x").report("SYN-EXPECTED-EXPRESSION", 1, 1, found=";", rule_ref="var_decl")
    assert rec.rule_ref == "var_decl"


def test_expected_must_not_be_a_bare_string():
    with pytest.raises(TypeError):
        ErrorSink("x").report("SYN-EXPECTED-TOKEN", 1, 1, found="x", expected="(", rule_ref="if_stmt")


def test_positions_are_one_based():
    with pytest.raises(ValueError):
        ErrorSink("x").report("LEX-INVALID-CHAR", 0, 1, found="@")


def test_failed_report_creates_no_record_and_uses_no_id():
    sink = ErrorSink("x")
    with pytest.raises(KeyError):
        sink.report("SEM-UNDECLARED-VAR", 1, 1, found="y")
    assert sink.records == []
    assert sink.report("LEX-INVALID-CHAR", 1, 1, found="@").id == "E-0001"


@pytest.mark.parametrize("found,span_end", [
    ("count", Position(3, 9)),
    ("@", Position(3, 5)),
    ("", Position(3, 5)),
])
def test_default_span_end(found, span_end):
    assert ErrorSink(FIVE_LINES).report("LEX-INVALID-CHAR", 3, 5, found=found).span_end == span_end


@pytest.mark.parametrize("code,found,kwargs", [
    ("SYN-UNEXPECTED-EOF", "EOF", dict(expected=["}"], rule_ref="block", context="a block")),
    ("SYN-EXPECTED-EXPRESSION", "EOF", dict(rule_ref="assignment")),
    ("SYN-MISSING-SEMICOLON", "result", dict(expected=[";"], rule_ref="expr_stmt", context="x")),
    ("SEM-MISSING-MAIN", "EOF", {}),
])
def test_default_span_end_is_zero_width_for_eof_and_missing_semicolon(code, found, kwargs):
    rec = ErrorSink(FIVE_LINES).report(code, 5, 3, found=found, **kwargs)
    assert rec.span_end == Position(5, 3)


def test_explicit_span_end_and_expected_list():
    rec = ErrorSink(FIVE_LINES).report("SYN-EXPECTED-TOKEN", 2, 1, found="x", expected=("(", ")"),
                                       rule_ref="if_stmt", span_end=Position(4, 2))
    assert rec.span_end == Position(4, 2)
    assert rec.expected == ["(", ")"]


@pytest.mark.parametrize("fatal,warnings,text", [
    (0, 0, "0 fatal, 0 warnings"),
    (1, 0, "1 fatal, 0 warnings"),
    (0, 1, "0 fatal, 1 warning"),
    (1, 1, "1 fatal, 1 warning"),
    (2, 3, "2 fatal, 3 warnings"),
])
def test_summary(fatal, warnings, text):
    sink = ErrorSink("x")
    for _ in range(fatal):
        sink.report("LEX-INVALID-CHAR", 1, 1, found="@")
    for _ in range(warnings):
        sink.report("WRN-UNUSED-VAR", 1, 1, found="t", name="t")
    assert sink.summary() == text


def test_records_property_is_a_copy():
    sink = ErrorSink("x")
    sink.report("LEX-INVALID-CHAR", 1, 1, found="@")
    sink.records.clear()
    assert len(sink.records) == 1


def test_custom_catalog_is_used():
    cat = {"LEX-X": CatalogEntry("LEX-X", "lexical", "warning", "malformed-token", "token", "Bad {found}")}
    rec = ErrorSink("x", catalog=cat).report("LEX-X", 1, 1, found="@")
    assert (rec.severity, rec.message) == ("warning", "Bad @")


def test_record_serialises_to_json():
    rec = ErrorSink(FIVE_LINES).report("LEX-INVALID-CHAR", 2, 1, found="@")
    assert json.loads(json.dumps(rec.to_dict()))["span_end"] == {"line": 2, "column": 1}
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_diagnostics.py` → `63 passed`
- `.venv/Scripts/python -m pytest -q tests/unit` → `83 passed`
- Commit `src/cea/diagnostics.py tests/unit/test_diagnostics.py` with message `cea: add ErrorSink error interceptor (plan 005 step 2)` plus the trailer.

### Step 3: Tokens and lexical tables

`src/cea/tokens.py`:

````python
"""Token kinds, the Token dataclass and the lexical tables of docs/language-spec.md section 1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    IDENT = auto()
    KEYWORD = auto()
    UNSUPPORTED_KEYWORD = auto()
    INT_LIT = auto()
    FLOAT_LIT = auto()
    CHAR_LIT = auto()
    STRING_LIT = auto()
    OP = auto()
    UNSUPPORTED_OP = auto()
    PUNCT = auto()
    EOF = auto()


TYPE_KEYWORDS = frozenset({"int", "float", "double", "char", "void"})
KEYWORDS = TYPE_KEYWORDS | frozenset({"if", "else", "while", "for", "return", "break", "continue"})
UNSUPPORTED_KEYWORDS = frozenset({
    "struct", "union", "enum", "typedef", "switch", "case", "default", "do", "goto",
    "sizeof", "long", "short", "unsigned", "signed", "const", "static", "extern",
    "auto", "register", "volatile",
})
OPERATORS = frozenset({
    "+", "-", "*", "/", "%", "=", "+=", "-=", "*=", "/=", "%=", "++", "--",
    "==", "!=", "<", "<=", ">", ">=", "&&", "||", "!",
})
UNSUPPORTED_OPS = frozenset({"&", "|", "^", "~", "<<", ">>", "->", ".", "?", ":"})
PUNCTUATORS = frozenset({";", ",", "(", ")", "{", "}", "[", "]"})
# escape = "\" , ( "n" | "t" | "0" | "'" | '"' | "\" ) ; key = the character after the backslash
ESCAPES = {"n": "\n", "t": "\t", "0": "\0", "'": "'", '"': '"', "\\": "\\"}


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str               # exact source text ("EOF" for EOF)
    line: int               # start, 1-based
    col: int
    end_line: int           # inclusive end; for EOF: the EOF position itself
    end_col: int
    lex_gap: str | None = None   # docs/error-recovery.md section 3
    value: object = None    # INT_LIT int, FLOAT_LIT float, CHAR_LIT str (1 char), STRING_LIT str (decoded)
````

`tests/unit/test_tokens.py`:

````python
"""Unit tests for cea.tokens: the tables must equal docs/language-spec.md section 1 (plan 005, step 3)."""
import dataclasses
import re
from pathlib import Path

import pytest

from cea.tokens import (
    ESCAPES, KEYWORDS, OPERATORS, PUNCTUATORS, TYPE_KEYWORDS, UNSUPPORTED_KEYWORDS,
    UNSUPPORTED_OPS, Token, TokenKind,
)

SPEC = Path(__file__).resolve().parents[2] / "docs" / "language-spec.md"


def _spec_strings(rule):
    """The double-quoted strings in one rule of the lexical ebnf block of language-spec.md."""
    text = SPEC.read_text(encoding="utf-8")
    start = text.index("```ebnf")
    block = text[start:text.index("```", start + 7)]
    m = re.search(rf"^{rule}\s*=(.*?);\s*$", block, re.M | re.S)
    assert m, f"rule {rule} not found in the lexical grammar"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def test_token_kinds_in_contract_order():
    assert [k.name for k in TokenKind] == [
        "IDENT", "KEYWORD", "UNSUPPORTED_KEYWORD", "INT_LIT", "FLOAT_LIT", "CHAR_LIT",
        "STRING_LIT", "OP", "UNSUPPORTED_OP", "PUNCT", "EOF",
    ]


@pytest.mark.parametrize("table,rule,size", [
    (KEYWORDS, "KEYWORD", 12),
    (UNSUPPORTED_KEYWORDS, "UNSUPPORTED_KEYWORD", 20),
    (OPERATORS, "OPERATOR", 22),
    (UNSUPPORTED_OPS, "UNSUPPORTED_OP", 10),
    (PUNCTUATORS, "PUNCT", 8),
])
def test_tables_match_the_spec(table, rule, size):
    assert table == _spec_strings(rule)
    assert len(table) == size


def test_type_keywords():
    assert TYPE_KEYWORDS == {"int", "float", "double", "char", "void"}
    assert TYPE_KEYWORDS <= KEYWORDS


def test_tables_are_disjoint():
    assert not KEYWORDS & UNSUPPORTED_KEYWORDS
    assert not OPERATORS & UNSUPPORTED_OPS
    assert not (OPERATORS | UNSUPPORTED_OPS) & PUNCTUATORS


def test_escapes():
    assert ESCAPES == {"n": "\n", "t": "\t", "0": "\0", "'": "'", '"': '"', "\\": "\\"}


def test_token_defaults_and_frozen():
    t = Token(TokenKind.IDENT, "x", 1, 1, 1, 1)
    assert (t.lex_gap, t.value) == (None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.text = "y"
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_tokens.py` → `10 passed`. If `test_tables_match_the_spec` fails, a table differs from `docs/language-spec.md` §1. Fix the table, never the spec.
- `.venv/Scripts/python -m pytest -q tests/unit` → `93 passed`
- Commit `src/cea/tokens.py tests/unit/test_tokens.py` with message `cea: add token kinds and lexical tables (plan 005 step 3)` plus the trailer.

### Step 4: Lexer, part 1: tokens, literals and positions

The algorithm (`_Lexer.run`): a single left-to-right scan by character index `i`. Each loop iteration consumes at least one character, so the lexer terminates.

1. `_positions()` precomputes `(line, column)` for every index, plus one extra entry for the end of the text. A CRLF pair shares one position and the next character is column 1 of the next line. This is the only place newlines and columns are counted.
2. Dispatch on the current character: whitespace is skipped; a letter or `_` starts an identifier or keyword (`_ident`); a digit starts a number (`_number`); `"` a string (`_string`); `'` a char literal (`_char`); anything else is tried as a symbol (`_symbol`). Step 5 adds comments and directives in front of the letter branch.
3. `_symbol` does **maximal munch**: `_SYMBOLS` holds every operator, unsupported operator and punctuator, longest first, so `<<=` gives `<<` (UNSUPPORTED_OP) then `=`, `->` gives one UNSUPPORTED_OP, `a+++b` gives `++` then `+`, and `.` is UNSUPPORTED_OP. A character that starts no symbol is LEX-INVALID-CHAR and is skipped.
4. `_number`: digits, then `.` plus at least one digit makes a FLOAT_LIT. If the next character is in `[A-Za-z0-9_.]`, the maximal run of that set from the number's start is LEX-MALFORMED-NUMBER and no token is emitted.
5. `_string`: scans to the closing `"` on the same line, decoding the six escapes of `ESCAPES`. An unknown escape `\x` is recorded as LEX-INVALID-ESCAPE (at the `\`, `found` = the two characters, no `lex_gap`) and dropped from the value; the literal is still emitted with its exact source text. Reaching a newline or the end of the file first is LEX-UNTERMINATED-STRING at the opening `"`, with the text up to the end of the line skipped.
6. `_char`: finds the closing `'` on the same line, where `\` hides the next character. No closing quote → LEX-BAD-CHAR-LITERAL, skipping to the end of the line. Exactly one character (not `\`) → CHAR_LIT. `\` plus a known escape → CHAR_LIT with the decoded value. `\` plus an unknown escape → LEX-INVALID-ESCAPE at the `\`, whole literal skipped. Anything else (`''`, `'ab'`, `'\n\n'`) → LEX-BAD-CHAR-LITERAL, skipped through the closing `'`.
7. **`lex_gap` bookkeeping**: `_error(..., sets_gap=True)` stores the new record's id in `pending_gap` (so after several errors it holds the **last** one). `_emit` copies `pending_gap` into the token it creates and clears it. `_emit_eof` does the same for the EOF token. Errors with `sets_gap=False` (an invalid escape inside a string, an unsupported directive) leave `pending_gap` unchanged.
8. **EOF**: after the scan, one EOF token is appended at (last token's `end_line`, `end_col + 1`), or 1:1 if no token was emitted, with `text = "EOF"` and its end equal to its start.

Create `src/cea/lexer.py` with exactly this content (step 5 extends it):

````python
"""The lexical phase: source text -> tokens, with recovery (docs/error-recovery.md section 3).

Rule: record the error, skip the bad input, continue; never pass an error token
to the parser. A skipped lexeme sets `lex_gap` on the next token so the parser
can link a cascade to it (rule R1). Newlines are CRLF, LF or a lone CR; a CR is
never a column. A tab counts as one column.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from cea.diagnostics import ErrorSink
from cea.records import Position
from cea.tokens import (
    ESCAPES, KEYWORDS, OPERATORS, PUNCTUATORS, UNSUPPORTED_KEYWORDS, Token, TokenKind,
    UNSUPPORTED_OPS,
)

_WHITESPACE = frozenset(" \t\f\v\r\n")
_NEWLINES = frozenset("\r\n")
_LETTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")
_DIGITS = frozenset("0123456789")
_IDENT_CHARS = _LETTERS | _DIGITS
_NUMBER_RUN = _IDENT_CHARS | {"."}          # the maximal run skipped for LEX-MALFORMED-NUMBER
# Maximal munch: longest symbols first; ties broken alphabetically for determinism.
_SYMBOLS = sorted(OPERATORS | UNSUPPORTED_OPS | PUNCTUATORS, key=lambda s: (-len(s), s))
# After the header name only blanks and comments may follow (comments are whitespace,
# language-spec section 1). A /* comment must be closed on the same line.
_STDIO_INCLUDE = re.compile(r"#[ \t]*include[ \t]*<stdio\.h>(?:[ \t]|/\*.*?\*/)*(?://.*)?")


@dataclass
class LexResult:
    tokens: list[Token]                 # always ends with exactly one EOF token
    stdio_include: Position | None      # the '#' of the first accepted '#include <stdio.h>', else None


def lex(source: str, sink: ErrorSink) -> LexResult:
    """Tokenise the whole of `source`, reporting lexical errors to `sink`. Never raises on bad input."""
    return _Lexer(source, sink).run()


def _positions(source: str) -> list[tuple[int, int]]:
    """(line, column) of every index of `source`, plus one entry for the end of the text.

    The CR and LF of a CRLF pair share one position; the character after any
    newline is at column 1 of the next line.
    """
    pos: list[tuple[int, int]] = []
    line, col, i, n = 1, 1, 0, len(source)
    while i < n:
        ch = source[i]
        pos.append((line, col))
        if ch == "\r" and i + 1 < n and source[i + 1] == "\n":
            pos.append((line, col))
            i += 2
            line, col = line + 1, 1
            continue
        if ch in _NEWLINES:
            line, col = line + 1, 1
        else:
            col += 1
        i += 1
    pos.append((line, col))
    return pos


class _Lexer:
    def __init__(self, source: str, sink: ErrorSink):
        self.src = source
        self.n = len(source)
        self.sink = sink
        self.pos = _positions(source)
        self.i = 0
        self.tokens: list[Token] = []
        self.pending_gap: str | None = None
        self.stdio_include: Position | None = None

    # ---- driver
    def run(self) -> LexResult:
        src = self.src
        while self.i < self.n:
            ch = src[self.i]
            if ch in _WHITESPACE:
                self.i += 1
            elif ch in _LETTERS:
                self._ident()
            elif ch in _DIGITS:
                self._number()
            elif ch == '"':
                self._string()
            elif ch == "'":
                self._char()
            else:
                self._symbol()
        self._emit_eof()
        return LexResult(self.tokens, self.stdio_include)

    # ---- helpers
    def _eol(self, i: int) -> int:
        """Index of the first newline character at or after i, or len(source)."""
        while i < self.n and self.src[i] not in _NEWLINES:
            i += 1
        return i

    def _emit(self, kind: TokenKind, start: int, end: int, value: object = None) -> None:
        """Emit src[start:end] (end exclusive) as a token; it takes and clears the pending lex_gap."""
        line, col = self.pos[start]
        end_line, end_col = self.pos[end - 1]
        self.tokens.append(Token(kind, self.src[start:end], line, col, end_line, end_col,
                                 self.pending_gap, value))
        self.pending_gap = None

    def _error(self, code: str, at: int, last: int, found: str, sets_gap: bool = True) -> None:
        """Report `code` at index `at`; `last` is the index of the last skipped character (span_end)."""
        line, col = self.pos[at]
        end_line, end_col = self.pos[last]
        record = self.sink.report(code, line, col, found=found, span_end=Position(end_line, end_col))
        if sets_gap:
            self.pending_gap = record.id

    def _emit_eof(self) -> None:
        if self.tokens:
            last = self.tokens[-1]
            line, col = last.end_line, last.end_col + 1
        else:
            line, col = 1, 1
        self.tokens.append(Token(TokenKind.EOF, "EOF", line, col, line, col, self.pending_gap))
        self.pending_gap = None

    # ---- tokens
    def _ident(self) -> None:
        start = j = self.i
        while j < self.n and self.src[j] in _IDENT_CHARS:
            j += 1
        text = self.src[start:j]
        if text in KEYWORDS:
            kind = TokenKind.KEYWORD
        elif text in UNSUPPORTED_KEYWORDS:
            kind = TokenKind.UNSUPPORTED_KEYWORD
        else:
            kind = TokenKind.IDENT
        self._emit(kind, start, j)
        self.i = j

    def _number(self) -> None:
        src, n = self.src, self.n
        start = j = self.i
        while j < n and src[j] in _DIGITS:
            j += 1
        kind = TokenKind.INT_LIT
        if j + 1 < n and src[j] == "." and src[j + 1] in _DIGITS:
            j += 2
            while j < n and src[j] in _DIGITS:
                j += 1
            kind = TokenKind.FLOAT_LIT
        if j < n and src[j] in _NUMBER_RUN:
            # A letter, '_' or a second '.' directly after the number: 12abc, 1.2.3, 12.
            while j < n and src[j] in _NUMBER_RUN:
                j += 1
            self._error("LEX-MALFORMED-NUMBER", start, j - 1, found=src[start:j])
        else:
            text = src[start:j]
            self._emit(kind, start, j, int(text) if kind is TokenKind.INT_LIT else float(text))
        self.i = j

    def _string(self) -> None:
        src, n = self.src, self.n
        start = self.i
        j = start + 1
        chars: list[str] = []
        while True:
            if j >= n or src[j] in _NEWLINES:
                # Skipped: from '"' up to (not including) the end of the line.
                self._error("LEX-UNTERMINATED-STRING", start, j - 1, found=src[start:j])
                self.i = j
                return
            c = src[j]
            if c == '"':
                self._emit(TokenKind.STRING_LIT, start, j + 1, "".join(chars))
                self.i = j + 1
                return
            if c == "\\" and j + 1 < n and src[j + 1] not in _NEWLINES:
                e = src[j + 1]
                if e in ESCAPES:
                    chars.append(ESCAPES[e])
                else:
                    # Only the two-character escape is dropped; the literal is still emitted.
                    self._error("LEX-INVALID-ESCAPE", j, j + 1, found=src[j:j + 2], sets_gap=False)
                j += 2
                continue
            chars.append(c)
            j += 1

    def _char(self) -> None:
        src = self.src
        start = self.i
        eol = self._eol(start)
        k = start + 1
        while k < eol and src[k] != "'":                     # a backslash hides the next character
            k += 2 if src[k] == "\\" and k + 1 < eol else 1
        if k >= eol:                                          # unclosed on its line
            self._error("LEX-BAD-CHAR-LITERAL", start, eol - 1, found=src[start:eol])
            self.i = eol
            return
        body = src[start + 1:k]
        if len(body) == 1 and body != "\\":
            self._emit(TokenKind.CHAR_LIT, start, k + 1, body)
        elif len(body) == 2 and body[0] == "\\":
            if body[1] in ESCAPES:
                self._emit(TokenKind.CHAR_LIT, start, k + 1, ESCAPES[body[1]])
            else:                                             # whole literal skipped, no token
                self._error("LEX-INVALID-ESCAPE", start + 1, k, found=body)
        else:                                                 # '' or more than one character
            self._error("LEX-BAD-CHAR-LITERAL", start, k, found=src[start:k + 1])
        self.i = k + 1

    def _symbol(self) -> None:
        start = self.i
        for sym in _SYMBOLS:
            if self.src.startswith(sym, start):
                if sym in PUNCTUATORS:
                    kind = TokenKind.PUNCT
                elif sym in OPERATORS:
                    kind = TokenKind.OP
                else:
                    kind = TokenKind.UNSUPPORTED_OP
                self._emit(kind, start, start + len(sym))
                self.i = start + len(sym)
                return
        self._error("LEX-INVALID-CHAR", start, start, found=self.src[start])
        self.i = start + 1
````

Create `tests/unit/test_lexer.py` with exactly this content (steps 5 and 6 append to it):

````python
"""Unit tests for cea.lexer (plan 005, steps 4-6)."""
import json
from pathlib import Path

import pytest

from cea.diagnostics import ErrorSink
from cea.lexer import lex
from cea.records import Position
from cea.tokens import TokenKind

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "corpus"


def run(source):
    """Lex `source`; return (LexResult, records)."""
    sink = ErrorSink(source)
    result = lex(source, sink)
    return result, sink.records


def toks(source):
    """(kind name, text) of every non-EOF token; asserts there are no records."""
    result, records = run(source)
    assert records == [], [(r.code, r.line, r.column) for r in records]
    return [(t.kind.name, t.text) for t in result.tokens[:-1]]


# ---------------------------------------------------------------- step 4: tokens and literals

@pytest.mark.parametrize("source,expected", [
    ("int x = 5;", [("KEYWORD", "int"), ("IDENT", "x"), ("OP", "="), ("INT_LIT", "5"), ("PUNCT", ";")]),
    ("struct sizeof whilex _a1 A9", [("UNSUPPORTED_KEYWORD", "struct"), ("UNSUPPORTED_KEYWORD", "sizeof"),
                                    ("IDENT", "whilex"), ("IDENT", "_a1"), ("IDENT", "A9")]),
    ("a+++b", [("IDENT", "a"), ("OP", "++"), ("OP", "+"), ("IDENT", "b")]),
    ("i-->0", [("IDENT", "i"), ("OP", "--"), ("OP", ">"), ("INT_LIT", "0")]),
    ("x<<=2", [("IDENT", "x"), ("UNSUPPORTED_OP", "<<"), ("OP", "="), ("INT_LIT", "2")]),
    ("x>>1", [("IDENT", "x"), ("UNSUPPORTED_OP", ">>"), ("INT_LIT", "1")]),
    ("p->q", [("IDENT", "p"), ("UNSUPPORTED_OP", "->"), ("IDENT", "q")]),
    ("s.f", [("IDENT", "s"), ("UNSUPPORTED_OP", "."), ("IDENT", "f")]),
    ("a&&b||!c", [("IDENT", "a"), ("OP", "&&"), ("IDENT", "b"), ("OP", "||"), ("OP", "!"), ("IDENT", "c")]),
    ("a&b|c^~d", [("IDENT", "a"), ("UNSUPPORTED_OP", "&"), ("IDENT", "b"), ("UNSUPPORTED_OP", "|"),
                  ("IDENT", "c"), ("UNSUPPORTED_OP", "^"), ("UNSUPPORTED_OP", "~"), ("IDENT", "d")]),
    ("a?b:c", [("IDENT", "a"), ("UNSUPPORTED_OP", "?"), ("IDENT", "b"), ("UNSUPPORTED_OP", ":"), ("IDENT", "c")]),
    ("a==b!=c<=d>=e<f>g", [("IDENT", "a"), ("OP", "=="), ("IDENT", "b"), ("OP", "!="), ("IDENT", "c"),
                           ("OP", "<="), ("IDENT", "d"), ("OP", ">="), ("IDENT", "e"), ("OP", "<"),
                           ("IDENT", "f"), ("OP", ">"), ("IDENT", "g")]),
    ("+= -= *= /= %=", [("OP", "+="), ("OP", "-="), ("OP", "*="), ("OP", "/="), ("OP", "%=")]),
    ("a*b/c%d-e", [("IDENT", "a"), ("OP", "*"), ("IDENT", "b"), ("OP", "/"), ("IDENT", "c"),
                   ("OP", "%"), ("IDENT", "d"), ("OP", "-"), ("IDENT", "e")]),
    ("(){}[],;", [("PUNCT", c) for c in "(){}[],;"]),
    (".5", [("UNSUPPORTED_OP", "."), ("INT_LIT", "5")]),
])
def test_token_kinds_and_maximal_munch(source, expected):
    assert toks(source) == expected


@pytest.mark.parametrize("source,kind,value", [
    ("42", "INT_LIT", 42),
    ("0", "INT_LIT", 0),
    ("007", "INT_LIT", 7),
    ("3.14", "FLOAT_LIT", 3.14),
    ("10.0", "FLOAT_LIT", 10.0),
    ("'a'", "CHAR_LIT", "a"),
    ("'\"'", "CHAR_LIT", '"'),
    ("' '", "CHAR_LIT", " "),
    ("'\\n'", "CHAR_LIT", "\n"),
    ("'\\t'", "CHAR_LIT", "\t"),
    ("'\\0'", "CHAR_LIT", "\0"),
    ("'\\''", "CHAR_LIT", "'"),
    ("'\\\"'", "CHAR_LIT", '"'),
    ("'\\\\'", "CHAR_LIT", "\\"),
    ('"hi"', "STRING_LIT", "hi"),
    ('""', "STRING_LIT", ""),
    ('"a\\tb\\n"', "STRING_LIT", "a\tb\n"),
    ('"say \\"x\\""', "STRING_LIT", 'say "x"'),
    ('"it\'s"', "STRING_LIT", "it's"),
    ('"\\\\"', "STRING_LIT", "\\"),
    ('"// not a comment"', "STRING_LIT", "// not a comment"),
])
def test_literal_values(source, kind, value):
    result, records = run(source)
    assert records == []
    [tok, eof] = result.tokens
    assert (tok.kind.name, tok.text, tok.value) == (kind, source, value)
    assert eof.kind is TokenKind.EOF


@pytest.mark.parametrize("source,expected", [
    # (text, line, col, end_line, end_col) of every token, EOF last
    ("int  x;\n\tif", [("int", 1, 1, 1, 3), ("x", 1, 6, 1, 6), (";", 1, 7, 1, 7),
                       ("if", 2, 2, 2, 3), ("EOF", 2, 4, 2, 4)]),
    ('x = "ab";', [("x", 1, 1, 1, 1), ("=", 1, 3, 1, 3), ('"ab"', 1, 5, 1, 8), (";", 1, 9, 1, 9),
                   ("EOF", 1, 10, 1, 10)]),
    ("return 0;", [("return", 1, 1, 1, 6), ("0", 1, 8, 1, 8), (";", 1, 9, 1, 9), ("EOF", 1, 10, 1, 10)]),
    ("return 0;\n", [("return", 1, 1, 1, 6), ("0", 1, 8, 1, 8), (";", 1, 9, 1, 9), ("EOF", 1, 10, 1, 10)]),
    ("a\n\n\n", [("a", 1, 1, 1, 1), ("EOF", 1, 2, 1, 2)]),
    ("", [("EOF", 1, 1, 1, 1)]),
    ("  \n\t\n", [("EOF", 1, 1, 1, 1)]),
    ("int a;\r\nint b;\r\n", [("int", 1, 1, 1, 3), ("a", 1, 5, 1, 5), (";", 1, 6, 1, 6),
                              ("int", 2, 1, 2, 3), ("b", 2, 5, 2, 5), (";", 2, 6, 2, 6), ("EOF", 2, 7, 2, 7)]),
    ("a\r\n\r\nb", [("a", 1, 1, 1, 1), ("b", 3, 1, 3, 1), ("EOF", 3, 2, 3, 2)]),
    ("a\rb", [("a", 1, 1, 1, 1), ("b", 2, 1, 2, 1), ("EOF", 2, 2, 2, 2)]),
    ("\t\tx", [("x", 1, 3, 1, 3), ("EOF", 1, 4, 1, 4)]),
])
def test_positions(source, expected):
    result, records = run(source)
    assert records == []
    assert [(t.text, t.line, t.col, t.end_line, t.end_col) for t in result.tokens] == expected


def test_exactly_one_eof_token_last():
    result, _ = run("int main(void) { return 0; }")
    assert [t.kind for t in result.tokens].count(TokenKind.EOF) == 1
    assert result.tokens[-1].kind is TokenKind.EOF and result.tokens[-1].text == "EOF"
    assert all(t.lex_gap is None for t in result.tokens)


def test_no_stdio_include_without_directive():
    assert run("int x;")[0].stdio_include is None
````

**Verify**:
- `grep -c "def _" src/cea/lexer.py` → `11`
- `.venv/Scripts/python -m pytest -q tests/unit/test_lexer.py` → `50 passed`
- `.venv/Scripts/python -m pytest -q tests/unit` → `143 passed`
- Commit `src/cea/lexer.py tests/unit/test_lexer.py` with message `cea: add lexer for tokens and literals (plan 005 step 4)` plus the trailer.

### Step 5: Lexer, part 2: comments and directives

Two edits to `src/cea/lexer.py`.

**Edit A**: in `_Lexer.run`, insert three branches between the whitespace branch and the letter branch. Replace exactly:

````python
            if ch in _WHITESPACE:
                self.i += 1
            elif ch in _LETTERS:
````

with:

````python
            if ch in _WHITESPACE:
                self.i += 1
            elif src.startswith("//", self.i):
                self._line_comment()
            elif src.startswith("/*", self.i):
                self._block_comment()
            elif ch == "#" and self._at_line_start():
                self._directive()
            elif ch in _LETTERS:
````

Comments are tested before `_symbol`, so `/` and `/=` remain operators while `//` and `/*` start comments. A string such as `"// x"` stays a string, because the scan is already inside `_string` when it reaches the `//`.

**Edit B**: append this block at the end of the file, after the `_symbol` method, inside class `_Lexer` (4-space indent), separated from `_symbol` by one blank line:

````python
    # ---- comments and directives
    def _line_comment(self) -> None:
        self.i = self._eol(self.i)

    def _block_comment(self) -> None:
        start = self.i
        close = self.src.find("*/", start + 2)
        if close == -1:
            last = self.n - 1
            while last > start + 1 and self.src[last] in _NEWLINES:
                last -= 1
            self._error("LEX-UNTERMINATED-COMMENT", start, last, found="/*")
            self.i = self.n
            return
        self.i = close + 2

    def _at_line_start(self) -> bool:
        """True if only spaces and tabs precede index i on its line."""
        k = self.i - 1
        while k >= 0 and self.src[k] in " \t":
            k -= 1
        return k < 0 or self.src[k] in _NEWLINES

    def _directive(self) -> None:
        start = self.i
        eol = self._eol(start)
        text = self.src[start:eol]
        if _STDIO_INCLUDE.fullmatch(text):
            if self.stdio_include is None:
                self.stdio_include = Position(*self.pos[start])
        else:
            found = text.rstrip(" \t\f\v")
            self._error("LEX-UNSUPPORTED-DIRECTIVE", start, start + len(found) - 1, found=found,
                        sets_gap=False)
        self.i = eol
````

Behaviour: a block comment ends at the first `*/` after its `/*` (comments do not nest, and `/*/` does not close itself). No `*/` → LEX-UNTERMINATED-COMMENT at the `/`, the rest of the file skipped, and the EOF token gets the `lex_gap`. A directive is the text from `#` to the end of the line. It produces no token. An accepted `#include <stdio.h>` (optionally followed by blanks, `/* … */` comments closed on that line, and a final `// …` comment, per the `_STDIO_INCLUDE` regex from step 4) sets `stdio_include` once. Anything else is LEX-UNSUPPORTED-DIRECTIVE, which sets no `lex_gap`. In particular `#include <stdio.h> /* open`, with the comment left unclosed on that line, is LEX-UNSUPPORTED-DIRECTIVE, and because the directive consumed the whole line the `/*` opens no comment: the next line is lexed as code.

Then append this block to the end of `tests/unit/test_lexer.py`, separated from the existing last line by two blank lines:

````python
# ---------------------------------------------------------------- step 5: comments and directives

@pytest.mark.parametrize("source,expected", [
    # (text, line, col) of every non-EOF token
    ("a // c\nb", [("a", 1, 1), ("b", 2, 1)]),
    ("a // c", [("a", 1, 1)]),
    ("a /* x\ny */ b", [("a", 1, 1), ("b", 2, 6)]),
    ("a/**/b", [("a", 1, 1), ("b", 1, 6)]),
    ("/*/ */x", [("x", 1, 7)]),
    ("/* a /* b */ c */", [("c", 1, 14), ("*", 1, 16), ("/", 1, 17)]),
    ("a / b", [("a", 1, 1), ("/", 1, 3), ("b", 1, 5)]),
    ("a /= b", [("a", 1, 1), ("/=", 1, 3), ("b", 1, 6)]),
    ("x = 1; // done\r\ny", [("x", 1, 1), ("=", 1, 3), ("1", 1, 5), (";", 1, 6), ("y", 2, 1)]),
])
def test_comments_are_skipped(source, expected):
    result, records = run(source)
    assert records == []
    assert [(t.text, t.line, t.col) for t in result.tokens[:-1]] == expected


@pytest.mark.parametrize("source,stdio", [
    ("#include <stdio.h>\nint x;", Position(1, 1)),
    ("#include<stdio.h>", Position(1, 1)),
    ("#  include   <stdio.h>  \n", Position(1, 1)),
    ("# include <stdio.h>", Position(1, 1)),
    ("   #include <stdio.h>\n", Position(1, 4)),
    ("\t#include <stdio.h>", Position(1, 2)),
    ("#include <stdio.h>\r\nint x;\r\n", Position(1, 1)),
    ("int x;\n#include <stdio.h>\n#include <stdio.h>\n", Position(2, 1)),
    # comments are whitespace: a trailing // comment or a /* */ closed on the line is allowed
    ("#include <stdio.h> // io", Position(1, 1)),
    ("#include <stdio.h>// io\nint x;", Position(1, 1)),
    ("#include <stdio.h> /* io */", Position(1, 1)),
    ("#include <stdio.h>/* a */ /* b */  // c\r\nint x;", Position(1, 1)),
])
def test_accepted_stdio_include(source, stdio):
    result, records = run(source)
    assert records == []
    assert result.stdio_include == stdio
    assert all(t.text != "#" and t.text != "include" for t in result.tokens)


def test_include_alone_gives_only_eof():
    result, records = run("#include <stdio.h>\n")
    assert records == []
    assert [(t.kind, t.line, t.col) for t in result.tokens] == [(TokenKind.EOF, 1, 1)]


@pytest.mark.parametrize("source,found,span_end", [
    ("#include <math.h>\n", "#include <math.h>", Position(1, 17)),
    ("#define N 10\n", "#define N 10", Position(1, 12)),
    ('#include "stdio.h"', '#include "stdio.h"', Position(1, 18)),
    ("#include < stdio.h >", "#include < stdio.h >", Position(1, 20)),
    ("#include <stdio.h> x", "#include <stdio.h> x", Position(1, 20)),
    ("#include <stdio.h> /* io */ x", "#include <stdio.h> /* io */ x", Position(1, 29)),
    ("#include <stdio.h> /* never closed here", "#include <stdio.h> /* never closed here",
     Position(1, 39)),
    ("#\n", "#", Position(1, 1)),
    ("#pragma once   \r\n", "#pragma once", Position(1, 12)),
])
def test_unsupported_directive(source, found, span_end):
    result, records = run(source)
    [rec] = records
    assert (rec.code, rec.line, rec.column, rec.found, rec.span_end) == \
        ("LEX-UNSUPPORTED-DIRECTIVE", 1, 1, found, span_end)
    assert rec.message == f"Only '#include <stdio.h>' is supported; '{found}' is not"
    assert result.stdio_include is None


def test_unclosed_block_comment_after_include_stays_inside_the_directive():
    # The directive owns the whole line, so the /* opens no comment: line 2 is lexed normally.
    result, records = run("#include <stdio.h> /* open\nint x; */")
    assert [(r.code, r.line, r.column) for r in records] == [("LEX-UNSUPPORTED-DIRECTIVE", 1, 1)]
    assert [t.text for t in result.tokens] == ["int", "x", ";", "*", "/", "EOF"]


def test_unsupported_directive_does_not_set_lex_gap():
    result, records = run("#define N 10\nint x;")
    assert [r.code for r in records] == ["LEX-UNSUPPORTED-DIRECTIVE"]
    assert [(t.text, t.lex_gap) for t in result.tokens] == \
        [("int", None), ("x", None), (";", None), ("EOF", None)]


def test_hash_after_code_is_an_invalid_char():
    result, records = run("int x; # 2\n")
    [rec] = records
    assert (rec.code, rec.line, rec.column, rec.found) == ("LEX-INVALID-CHAR", 1, 8, "#")
    assert [(t.text, t.lex_gap) for t in result.tokens] == \
        [("int", None), ("x", None), (";", None), ("2", "E-0001"), ("EOF", None)]
````

**Verify**:
- `grep -c "def _" src/cea/lexer.py` → `15`
- `.venv/Scripts/python -m pytest -q tests/unit/test_lexer.py` → `84 passed`
- `.venv/Scripts/python -m pytest -q tests/unit` → `177 passed`
- Commit `src/cea/lexer.py tests/unit/test_lexer.py` with message `cea: lex comments and the stdio include directive (plan 005 step 5)` plus the trailer.

### Step 6: Lexer, part 3: error recovery, `lex_gap`, traces T5/T6 and the corpus

No source change is expected in this step: steps 4 and 5 already contain every recovery path. This step pins each one with tests, checks traces T5 and T6, and runs the lexer over the real corpus files (read as raw bytes, so CRLF is exercised).

First, run this probe and compare its output line by line (it was produced by the plan's code on the real corpus files):

```bash
.venv/Scripts/python -c "
import sys, pathlib; sys.path.insert(0, 'src')
from cea.diagnostics import ErrorSink; from cea.lexer import lex
for p in sorted(pathlib.Path('tests/corpus/dev').glob('00[1-7]-*.c')):
    s = p.read_bytes().decode('utf-8'); k = ErrorSink(s); r = lex(s, k)
    print(p.name, [(e.code, e.line, e.column, e.found) for e in k.records], [(t.text, t.line, t.col, t.lex_gap) for t in r.tokens if t.lex_gap])
"
```

Expected output, exactly:

```
001-stray-at-sign.c [('LEX-INVALID-CHAR', 12, 27, '@')] [('}', 13, 5, 'E-0001')]
002-unclosed-printf-string.c [('LEX-UNTERMINATED-STRING', 11, 12, '"Total: %d\\n, sum);')] [('return', 12, 5, 'E-0001')]
003-two-char-literal.c [('LEX-BAD-CHAR-LITERAL', 5, 18, "'AB'")] [(';', 5, 22, 'E-0001')]
004-unclosed-todo-comment.c [('LEX-UNTERMINATED-COMMENT', 11, 1, '/*')] [('EOF', 10, 2, 'E-0001')]
005-number-with-letters.c [('LEX-MALFORMED-NUMBER', 4, 17, '10x')] [(';', 4, 20, 'E-0001')]
006-windows-path-escape.c [('LEX-INVALID-ESCAPE', 10, 24, '\\d')] []
007-unsupported-include.c [('LEX-UNSUPPORTED-DIRECTIVE', 2, 1, '#include <math.h>')] []
```

Then append this block to the end of `tests/unit/test_lexer.py`, separated from the existing last line by two blank lines:

````python
# ---------------------------------------------------------------- step 6: error recovery and lex_gap

@pytest.mark.parametrize("source,code,line,col,found,span_end,gap_token", [
    # gap_token = (text, line, col) of the one token that must carry lex_gap = "E-0001"
    ("x = 5 @ 2;", "LEX-INVALID-CHAR", 1, 7, "@", (1, 7), ("2", 1, 9)),
    ("$a", "LEX-INVALID-CHAR", 1, 1, "$", (1, 1), ("a", 1, 2)),
    ("a `b", "LEX-INVALID-CHAR", 1, 3, "`", (1, 3), ("b", 1, 4)),
    ("a \\ b", "LEX-INVALID-CHAR", 1, 3, "\\", (1, 3), ("b", 1, 5)),
    ("caf\u00e9 = 1;", "LEX-INVALID-CHAR", 1, 4, "\u00e9", (1, 4), ("=", 1, 6)),
    ('printf("hi);\nx', "LEX-UNTERMINATED-STRING", 1, 8, '"hi);', (1, 12), ("x", 2, 1)),
    ('printf("hi);\r\nx', "LEX-UNTERMINATED-STRING", 1, 8, '"hi);', (1, 12), ("x", 2, 1)),
    ('"abc', "LEX-UNTERMINATED-STRING", 1, 1, '"abc', (1, 4), ("EOF", 1, 1)),
    ('x "', "LEX-UNTERMINATED-STRING", 1, 3, '"', (1, 3), ("EOF", 1, 2)),
    ('"abc\\\ny', "LEX-UNTERMINATED-STRING", 1, 1, '"abc\\', (1, 5), ("y", 2, 1)),
    ("c = 'ab';", "LEX-BAD-CHAR-LITERAL", 1, 5, "'ab'", (1, 8), (";", 1, 9)),
    ("c = '';", "LEX-BAD-CHAR-LITERAL", 1, 5, "''", (1, 6), (";", 1, 7)),
    ("c = '\\n\\n';", "LEX-BAD-CHAR-LITERAL", 1, 5, "'\\n\\n'", (1, 10), (";", 1, 11)),
    ("c = 'a;\nx", "LEX-BAD-CHAR-LITERAL", 1, 5, "'a;", (1, 7), ("x", 2, 1)),
    ("c = '\\';\nx", "LEX-BAD-CHAR-LITERAL", 1, 5, "'\\';", (1, 8), ("x", 2, 1)),
    ("c = '", "LEX-BAD-CHAR-LITERAL", 1, 5, "'", (1, 5), ("EOF", 1, 4)),
    ("c = '\\q';", "LEX-INVALID-ESCAPE", 1, 6, "\\q", (1, 8), (";", 1, 9)),
    ("x /* never closed\n\n", "LEX-UNTERMINATED-COMMENT", 1, 3, "/*", (1, 17), ("EOF", 1, 2)),
    ("x\n/* a\r\nb\r\n", "LEX-UNTERMINATED-COMMENT", 2, 1, "/*", (3, 1), ("EOF", 1, 2)),
    ("/*", "LEX-UNTERMINATED-COMMENT", 1, 1, "/*", (1, 2), ("EOF", 1, 1)),
    ("n = 12abc;", "LEX-MALFORMED-NUMBER", 1, 5, "12abc", (1, 9), (";", 1, 10)),
    ("n = 1.2.3;", "LEX-MALFORMED-NUMBER", 1, 5, "1.2.3", (1, 9), (";", 1, 10)),
    ("n = 12.;", "LEX-MALFORMED-NUMBER", 1, 5, "12.", (1, 7), (";", 1, 8)),
    ("n = 10x;", "LEX-MALFORMED-NUMBER", 1, 5, "10x", (1, 7), (";", 1, 8)),
    ("n = 1e5;", "LEX-MALFORMED-NUMBER", 1, 5, "1e5", (1, 7), (";", 1, 8)),
    ("n = 0x1F;", "LEX-MALFORMED-NUMBER", 1, 5, "0x1F", (1, 8), (";", 1, 9)),
    ("n = 3_000;", "LEX-MALFORMED-NUMBER", 1, 5, "3_000", (1, 9), (";", 1, 10)),
    ("n = 1..2;", "LEX-MALFORMED-NUMBER", 1, 5, "1..2", (1, 8), (";", 1, 9)),
    ("n = 2.5x;", "LEX-MALFORMED-NUMBER", 1, 5, "2.5x", (1, 8), (";", 1, 9)),
    ("n = 5.", "LEX-MALFORMED-NUMBER", 1, 5, "5.", (1, 6), ("EOF", 1, 4)),
])
def test_one_lexical_error_and_lex_gap(source, code, line, col, found, span_end, gap_token):
    result, records = run(source)
    [rec] = records
    assert (rec.id, rec.code, rec.line, rec.column, rec.found) == ("E-0001", code, line, col, found)
    assert (rec.span_end.line, rec.span_end.column) == span_end
    assert (rec.phase, rec.severity, rec.caused_by, rec.expected) == ("lexical", "fatal", None, [])
    gapped = [(t.text, t.line, t.col, t.lex_gap) for t in result.tokens if t.lex_gap is not None]
    assert gapped == [gap_token + ("E-0001",)]


LEX_CASES = [
    ("LEX-INVALID-CHAR", "@", "token"),
    ("LEX-UNTERMINATED-STRING", '"a', "STRING_LIT"),
    ("LEX-BAD-CHAR-LITERAL", "'ab'", "CHAR_LIT"),
    ("LEX-UNTERMINATED-COMMENT", "/* a", "BLOCK_COMMENT"),
    ("LEX-MALFORMED-NUMBER", "1x", "number"),
    ("LEX-INVALID-ESCAPE", '"\\q"', "escape"),
    ("LEX-UNSUPPORTED-DIRECTIVE", "#define X", "directive"),
]


@pytest.mark.parametrize("code,source,rule_ref", LEX_CASES, ids=[c[0] for c in LEX_CASES])
def test_every_lex_code_is_reachable(code, source, rule_ref):
    [rec] = run(source)[1]
    assert (rec.code, rec.rule_ref, rec.phase) == (code, rule_ref, "lexical")


def test_invalid_escape_in_string_keeps_the_token():
    result, records = run('x = "a\\qb";')
    [rec] = records
    assert (rec.code, rec.line, rec.column, rec.found) == ("LEX-INVALID-ESCAPE", 1, 7, "\\q")
    assert rec.span_end == Position(1, 8)
    assert rec.message == "Unknown escape sequence '\\q'"
    s = result.tokens[2]
    assert (s.kind, s.text, s.value, s.lex_gap) == (TokenKind.STRING_LIT, '"a\\qb"', "ab", None)
    assert all(t.lex_gap is None for t in result.tokens)


def test_string_with_bad_escape_and_no_close_gives_two_records():
    result, records = run('"a\\q\ny')
    assert [(r.id, r.code, r.line, r.column) for r in records] == [
        ("E-0001", "LEX-INVALID-ESCAPE", 1, 3),
        ("E-0002", "LEX-UNTERMINATED-STRING", 1, 1),
    ]
    assert [(t.text, t.lex_gap) for t in result.tokens] == [("y", "E-0002"), ("EOF", None)]


def test_lex_gap_is_the_last_record_and_is_used_once():
    result, records = run("@ $ a b @")
    assert [r.id for r in records] == ["E-0001", "E-0002", "E-0003"]
    assert [(t.text, t.lex_gap) for t in result.tokens] == \
        [("a", "E-0002"), ("b", None), ("EOF", "E-0003")]


def test_lexing_continues_after_an_error():
    result, records = run("int x = 5 @ 2;\nint y;")
    assert len(records) == 1
    assert [t.text for t in result.tokens] == ["int", "x", "=", "5", "2", ";", "int", "y", ";", "EOF"]


# Traces T5 and T6 of docs/error-recovery.md section 9 (lexical part only).
T5 = "int main(void) {\n    int x = 5 @ 2;\n    return x;\n}\n"
T6 = ('#include <stdio.h>\nint main(void) {\n    int count = 0;\n    printf("total\\q\\n", count);\n'
      "    count = count + 1\n    result = count;\n    return 0;\n}\n")


def test_trace_t5_lexical_record():
    result, records = run(T5)
    assert [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by) for r in records] == \
        [("E-0001", "LEX-INVALID-CHAR", "2:15", "@", None)]
    assert records[0].snippet == "int main(void) {\n    int x = 5 @ 2;\n    return x;"
    assert [(t.text, t.line, t.col, t.lex_gap) for t in result.tokens if t.lex_gap] == \
        [("2", 2, 17, "E-0001")]


def test_trace_t6_lexical_record():
    result, records = run(T6)
    assert [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by) for r in records] == \
        [("E-0001", "LEX-INVALID-ESCAPE", "4:18", "\\q", None)]
    assert result.stdio_include == Position(1, 1)
    assert all(t.lex_gap is None for t in result.tokens)
    strings = [t for t in result.tokens if t.kind is TokenKind.STRING_LIT]
    assert [(s.line, s.col, s.value) for s in strings] == [(4, 12, "total\n")]
    assert (result.tokens[-1].line, result.tokens[-1].col) == (8, 2)


# ---------------------------------------------------------------- corpus: dev/001-007 and valid/

DEV_LEX = sorted((CORPUS / "dev").glob("00[1-7]-*.c"))
VALID = sorted((CORPUS / "valid").glob("*.c"))


def _read_raw(path):
    """File text with its newlines untouched (CRLF when git checked it out that way)."""
    return path.read_bytes().decode("utf-8")


def _sidecar(path):
    return json.loads(path.with_name(path.stem + ".expected.json").read_text(encoding="utf-8"))


def test_corpus_files_found():
    assert len(DEV_LEX) == 7
    assert len(VALID) >= 10


@pytest.mark.parametrize("c_path", DEV_LEX, ids=[p.name for p in DEV_LEX])
def test_dev_lexical_program_gives_its_root(c_path):
    _, records = run(_read_raw(c_path))
    assert [{"code": r.code, "line": r.line} for r in records] == _sidecar(c_path)["roots"]


@pytest.mark.parametrize("c_path", VALID, ids=[p.name for p in VALID])
def test_valid_program_has_no_lexical_record(c_path):
    text = _read_raw(c_path)
    result, records = run(text)
    assert records == []
    assert result.stdio_include == Position(1, 1)
    assert result.tokens[-1].line == len(text.splitlines())


@pytest.mark.parametrize("c_path", DEV_LEX + VALID, ids=[p.name for p in DEV_LEX + VALID])
def test_crlf_and_lf_give_the_same_result(c_path):
    lf = _read_raw(c_path).replace("\r\n", "\n")
    crlf = lf.replace("\n", "\r\n")
    (res_lf, rec_lf), (res_crlf, rec_crlf) = run(lf), run(crlf)
    assert res_lf == res_crlf
    assert [(r.code, r.line, r.column, r.found, r.span_end, r.snippet) for r in rec_lf] == \
        [(r.code, r.line, r.column, r.found, r.span_end, r.snippet) for r in rec_crlf]
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_lexer.py` → `166 passed`
- `.venv/Scripts/python -m pytest -q tests/unit` → `259 passed`
- If `test_valid_program_has_no_lexical_record` fails for any file, STOP (STOP condition 3). Do not change the corpus.
- Commit `tests/unit/test_lexer.py` with message `test: pin lexer recovery, lex_gap and corpus results (plan 005 step 6)` plus the trailer.

### Step 7: The no-print rule (PRD F1)

`tests/unit/test_no_print.py`:

````python
"""PRD F1: "No phase may print directly to the console" (plan 005, step 7).

Only src/cea/cli.py (plan 007) may call print( or write to sys.stdout / sys.stderr.
Every other module reports through cea.diagnostics.ErrorSink.
"""
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "src" / "cea"
ALLOWED = {"cli.py"}
FORBIDDEN = re.compile(r"\bprint\s*\(|\bsys\.(stdout|stderr)\b")
FOUNDATION = {"__init__.py", "catalog.py", "records.py", "diagnostics.py", "tokens.py", "lexer.py"}


def test_foundation_modules_exist():
    assert FOUNDATION <= {p.name for p in PKG.glob("*.py")}


def test_no_module_except_cli_prints():
    offenders = []
    for path in sorted(PKG.glob("*.py")):
        if path.name in ALLOWED:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "console output outside cli.py:\n" + "\n".join(offenders)


def test_the_check_catches_a_print():
    assert FORBIDDEN.search('    print("debug")')
    assert FORBIDDEN.search("sys.stderr.write('x')")
    assert not FORBIDDEN.search('printf("%d", x)  # a C call inside a docstring')
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_no_print.py` → `3 passed`
- `.venv/Scripts/python -m pytest -q tests/unit` → `262 passed`
- `grep -rnE "\bprint\s*\(|sys\.std(out|err)" src/cea/` → no output (exit status 1)
- Commit `tests/unit/test_no_print.py` with message `test: forbid console output outside cli.py (plan 005 step 7)` plus the trailer.

### Step 8: Final checks

**Verify** (all must hold):
- `.venv/Scripts/python -m pytest -q` → `358 passed, 1 skipped` (B = 96 plus 262; `357 passed, 2 skipped` if gcc is missing) and no `failed`.
- `.venv/Scripts/python -m pytest -q -rs tests/test_corpus_compile.py` → `1 skipped`, and the reason line contains `No module named 'cea.pipeline'`.
- `test -e src/cea/pipeline.py && echo EXISTS || echo absent` → `absent`
- `ls src/cea` → exactly `__init__.py  catalog.py  diagnostics.py  lexer.py  records.py  tokens.py` (plus `__pycache__` if present)
- `ls tests/unit` → exactly `test_catalog.py  test_diagnostics.py  test_lexer.py  test_no_print.py  test_records.py  test_tokens.py` (plus `__pycache__` if present)
- `git diff --name-only main..HEAD` → exactly the 12 in-scope files (6 under `src/cea/`, 6 under `tests/unit/`).
- `git status --short` → no modified tracked files (untracked `~$ project prd.docx` may appear; leave it).
- `git log --format=%B -n 7 | grep -c "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"` → `7`
- Then update this plan's row in `plans/README.md` (Status → `DONE (branch advisor/005-m1-foundation, not merged)`) unless the reviewer told you they maintain it. If you edit it, commit it by explicit path with message `plans: mark plan 005 done` plus the trailer.

## Test plan

Six new test files in `tests/unit/`, in the style of `tests/test_corpus_schema.py` (module docstring, small helpers, `pytest.mark.parametrize` tables, plain `assert`). Expected pass counts, verified by running this plan's exact code and tests on copies of `docs/` and the corpus files (CRLF preserved) with pytest 8.4.2 on Python 3.13.1:

| After step | New tests | `pytest -q tests/unit` |
|---|---|---|
| 1 | test_catalog.py 17, test_records.py 3 | 20 passed |
| 2 | test_diagnostics.py 63 | 83 passed |
| 3 | test_tokens.py 10 | 93 passed |
| 4 | test_lexer.py part 1: 50 | 143 passed |
| 5 | test_lexer.py part 2: 34 (84 in the file) | 177 passed |
| 6 | test_lexer.py part 3: 82 (166 in the file) | 259 passed |
| 7 | test_no_print.py 3 | 262 passed |

As a control, the step-5 tests run against the step-4 lexer give `31 failed, 53 passed`, so they really test the new code.

### Catalog and records (step 1)

| Case | Expected |
|---|---|
| `load_catalog()` | 37 entries in table order; phases lexical 7, syntax 8, semantic 22; warnings = the 5 `WRN-` codes, all others fatal |
| backticks | `LEX-INVALID-CHAR.rule_ref == "token"`; no `` ` `` left in any rule_ref |
| `<production>` rows | exactly the 7 `SYN-` codes listed in the test; `SYN-INVALID-ASSIGN-TARGET` has `assignment` |
| explicit path, 1-row table | one `CatalogEntry` with the row's values |
| row with 5 cells | `ValueError` |
| `load_grammar_rules()` | 36 names; includes `program`, `statement`, `var_decl`, `assignment`, `primary`; excludes `token` |
| `ErrorRecord` fields | exactly the 15 contract fields in contract order; `to_dict()` turns `span_end` into `{"line", "column"}` and is JSON-serialisable |

### ErrorSink (step 2)

| Input | Expected |
|---|---|
| two reports | ids `E-0001`, `E-0002`; `root_id == id`; `language == "c"`; `caused_by` passed through |
| 10 reports | last id `E-0010` |
| snippet of line 1 / 3 / 5 in a 5-line file | `l1\nl2` / `l2\nl3\nl4` / `l4\nl5` |
| same file with CRLF, line 3 | `l2\nl3\nl4` (no `\r`) |
| `"only"` line 1; `""` line 1 | `only`; empty string |
| `SYN-EXPECTED-TOKEN`, expected `[")", ";"]` | `Expected ')' or ';' but found 'x'` |
| `SEM-ARG-COUNT`, `found="1"`, expected `["2"]`, `name="add"` | `'add' expects 2 argument(s) but got 1` (semantic: no quotes added) |
| `SEM-TYPE-MISMATCH`, `found="double"`, expected `["int"]` | `Cannot use double where int is required` |
| `SEM-ARG-TYPE` / `SEM-RETURN-TYPE` | `Argument 2 of 'area' must be double but is char` / `Function 'log_it' returns void but this returns int` |
| `WRN-IMPLICIT-NARROWING`, `found="double"`, expected `["int"]` | `double value converted to int; the fractional part is lost` |
| `render_expected` with phase `semantic` or `lexical` | items joined raw: `2`, `int or double`, `x` |
| `SYN-UNBALANCED-BRACKET`, expected `[")"]`, `opener="("`, `open_line=3` | `Expected ')' to close '(' from line 3 but found '{'` (no double quotes) |
| `SEM-UNDECLARED-VAR` without `name=` | `KeyError` |
| unknown code | `KeyError` |
| `<production>` code without `rule_ref`; with `rule_ref="not_a_rule"` | `ValueError`; `ValueError` |
| `expected="("` (a str) | `TypeError` |
| default `span_end` for `found="count"` at 3:5 | `Position(3, 9)`; for `found=""` → `Position(3, 5)` |
| default `span_end` at 5:3 for SYN-UNEXPECTED-EOF, SYN-EXPECTED-EXPRESSION and SEM-MISSING-MAIN with `found="EOF"`, and SYN-MISSING-SEMICOLON with `found="result"` | zero-width `Position(5, 3)` in all four |
| summary with (fatal, warnings) = (0,0) (1,0) (0,1) (1,1) (2,3) | `0 fatal, 0 warnings`, `1 fatal, 0 warnings`, `0 fatal, 1 warning`, `1 fatal, 1 warning`, `2 fatal, 3 warnings` |

### Lexer: tokens and positions (step 4)

| Source | Tokens (kind, text) or positions |
|---|---|
| `a+++b` | IDENT a, OP `++`, OP `+`, IDENT b |
| `i-->0` | IDENT i, OP `--`, OP `>`, INT_LIT 0 |
| `x<<=2` | IDENT x, UNSUPPORTED_OP `<<`, OP `=`, INT_LIT 2 |
| `p->q`, `s.f`, `a?b:c`, `x>>1`, `a&b\|c^~d` | the unsupported operator is one UNSUPPORTED_OP token |
| `.5` | UNSUPPORTED_OP `.`, INT_LIT 5 |
| `struct sizeof whilex` | UNSUPPORTED_KEYWORD, UNSUPPORTED_KEYWORD, IDENT |
| `3.14`, `007`, `'\''`, `'\\'`, `"say \"x\""` | values `3.14`, `7`, `'`, `\`, `say "x"`; `text` is the exact source |
| `int  x;` newline tab `if` | `int` 1:1–1:3, `x` 1:6, `;` 1:7, `if` 2:2–2:3 (tab = 1 column), EOF 2:4 |
| `return 0;` with and without a final newline | EOF 1:10 in both |
| empty file; whitespace-only file | only EOF, at 1:1 |
| `int a;` CRLF `int b;` CRLF | `b` at 2:5, EOF 2:7 (same as LF) |
| `a` CR `b` (lone CR) | `b` at 2:1 |

### Lexer: comments and directives (step 5)

| Source | Expected |
|---|---|
| `a /* x` newline `y */ b` | `b` at 2:6 |
| `/*/ */x` | `x` at 1:7 (`/*/` does not close) |
| `/* a /* b */ c */` | tokens `c`, `*`, `/` (no nesting) |
| `#  include   <stdio.h>  `, `#include<stdio.h>`, `   #include <stdio.h>` | accepted; `stdio_include` = position of `#` (1:1, 1:1, 1:4) |
| include on lines 2 and 3 | `stdio_include == Position(2, 1)` |
| `#include <stdio.h>` alone | tokens = only EOF, at 1:1 |
| `#include <stdio.h> // io`, `#include <stdio.h>// io`, `#include <stdio.h> /* io */`, `#include <stdio.h>/* a */ /* b */  // c` | accepted, `stdio_include` 1:1, no record |
| `#include <math.h>`, `#define N 10`, `#include "stdio.h"`, `#include < stdio.h >`, `#include <stdio.h> x`, `#include <stdio.h> /* io */ x`, `#include <stdio.h> /* never closed here`, `#`, `#pragma once   ` | LEX-UNSUPPORTED-DIRECTIVE at 1:1, `found` = the line without trailing blanks |
| `#include <stdio.h> /* open` LF `int x; */` | one LEX-UNSUPPORTED-DIRECTIVE; line 2 gives `int x ; * /` (the unclosed `/*` belonged to the directive) |
| `#define N 10` newline `int x;` | no token has `lex_gap` |
| `int x; # 2` | LEX-INVALID-CHAR at 1:8; token `2` has `lex_gap = E-0001` |

### Lexer: every error and `lex_gap` (step 6)

Each row gives one record `E-0001` (phase lexical, fatal, `caused_by` None, `expected` []) and exactly one token carrying `lex_gap = "E-0001"`.

| Source | Code | at | found | span_end | token with lex_gap |
|---|---|---|---|---|---|
| `x = 5 @ 2;` | LEX-INVALID-CHAR | 1:7 | `@` | 1:7 | `2` 1:9 |
| `café = 1;` | LEX-INVALID-CHAR | 1:4 | `é` | 1:4 | `=` 1:6 |
| `printf("hi);` LF `x` (also CRLF) | LEX-UNTERMINATED-STRING | 1:8 | `"hi);` | 1:12 | `x` 2:1 |
| `"abc` (EOF) | LEX-UNTERMINATED-STRING | 1:1 | `"abc` | 1:4 | EOF 1:1 |
| `"abc\` LF `y` | LEX-UNTERMINATED-STRING | 1:1 | `"abc\` | 1:5 | `y` 2:1 |
| `c = 'ab';` | LEX-BAD-CHAR-LITERAL | 1:5 | `'ab'` | 1:8 | `;` 1:9 |
| `c = '';` | LEX-BAD-CHAR-LITERAL | 1:5 | `''` | 1:6 | `;` 1:7 |
| `c = 'a;` LF `x` | LEX-BAD-CHAR-LITERAL | 1:5 | `'a;` | 1:7 | `x` 2:1 |
| `c = '\';` LF `x` | LEX-BAD-CHAR-LITERAL | 1:5 | `'\';` | 1:8 | `x` 2:1 |
| `c = '\q';` | LEX-INVALID-ESCAPE | 1:6 | `\q` | 1:8 | `;` 1:9 |
| `x /* never closed` LF LF | LEX-UNTERMINATED-COMMENT | 1:3 | `/*` | 1:17 | EOF 1:2 |
| `/*` | LEX-UNTERMINATED-COMMENT | 1:1 | `/*` | 1:2 | EOF 1:1 |
| `n = 12abc;` / `1.2.3` / `12.` / `10x` / `1e5` / `0x1F` / `3_000` / `1..2` / `2.5x` | LEX-MALFORMED-NUMBER | 1:5 | the run | end of run | `;` |
| `n = 5.` (EOF) | LEX-MALFORMED-NUMBER | 1:5 | `5.` | 1:6 | EOF 1:4 |

Plus: `x = "a\qb";` → LEX-INVALID-ESCAPE at 1:7, the STRING_LIT is still emitted (text `"a\qb"`, value `ab`) and no token has `lex_gap`. `"a\q` LF `y` → E-0001 LEX-INVALID-ESCAPE 1:3, then E-0002 LEX-UNTERMINATED-STRING 1:1, and `y` gets `lex_gap = E-0002`. `@ $ a b @` → `a` gets E-0002 (the last record), `b` gets None, EOF gets E-0003. Every LEX code maps to its catalog `rule_ref` (`token`, `STRING_LIT`, `CHAR_LIT`, `BLOCK_COMMENT`, `number`, `escape`, `directive`).

Traces: T5 gives exactly `E-0001 LEX-INVALID-CHAR 2:15 @` (snippet = lines 1–3), and the only gap token is `2` at 2:17. T6 gives exactly `E-0001 LEX-INVALID-ESCAPE 4:18 \q`, `stdio_include == Position(1, 1)`, no `lex_gap`, the string at 4:12 has value `total` + newline, and EOF is at 8:2.

Corpus (parametrized): each `dev/00[1-7]-*.c` gives records whose `[{"code", "line"}]` list **equals** its sidecar `roots` (one record each); each `valid/*.c` gives zero records, `stdio_include == Position(1, 1)`, and an EOF line equal to the file's line count; and every one of these 19 files gives identical tokens and records when lexed as LF and as CRLF.

### No print (step 7)

`src/cea/*.py` except `cli.py` contains no `print(` and no `sys.stdout`/`sys.stderr`; the regex itself is checked to catch `print("debug")` and not `printf(`.

## Done criteria

All must hold:

- [ ] `.venv/Scripts/python -m pytest -q tests/unit` → `262 passed`
- [ ] `.venv/Scripts/python -m pytest -q` → `358 passed, 1 skipped` (`357 passed, 2 skipped` if gcc is missing), no failures
- [ ] `tests/test_corpus_compile.py` is still skipped; `src/cea/pipeline.py` does not exist
- [ ] `git diff --name-only main..HEAD` lists exactly the 12 in-scope files (plus `plans/README.md` if you updated the status row)
- [ ] `grep -rnE "\bprint\s*\(|sys\.std(out|err)" src/cea/` prints nothing
- [ ] Nothing under `docs/`, `tests/corpus/`, `tools/` or the existing `tests/*.py` changed: `git diff --stat main..HEAD -- docs tests/corpus tools tests/*.py pyproject.toml requirements-dev.txt` prints nothing
- [ ] 7 step commits on `advisor/005-m1-foundation`, each ending with the `Co-Authored-By` trailer; nothing pushed
- [ ] Final report ends with a **Viva notes** list

## STOP conditions

Stop and report back (do not improvise) if:

1. The drift check fails (someone already created `src/` or `tests/unit/`, or touched them since `1bbfed4`).
2. **The catalog parse does not yield 37 entries** (`load_catalog()` length ≠ 37), or a catalog row does not have 7 cells. The catalog changed after this plan was written, and the counts in the tests are wrong.
3. **A valid corpus program produces a lexical record** (`test_valid_program_has_no_lexical_record` fails), or a `dev/00[1-7]` program's records differ from its sidecar root. Do not edit the corpus or the sidecars; report the file, the record and the line.
4. **The contract in `plans/m1-architecture.md` cannot be followed as written**: for example a name, field or signature in this plan's code differs from the contract, a later plan's needs clash with it, or a test only passes by changing a contract type. Do not diverge; report.
5. `docs/language-spec.md` §1 tables differ from `tokens.py` (`test_tables_match_the_spec` fails) and the difference is in the spec rather than in your copy of the code.
6. Any step's verification fails twice after you have compared your files with the plan's code character for character.
7. Something seems to require `src/cea/pipeline.py`, a `conftest.py`, an `__init__.py` under `tests/`, or an edit to any out-of-scope file.

## Maintenance notes

- **Plan 006 (parser)** consumes `LexResult.tokens` and `Token.lex_gap` (rule R1). It calls `ErrorSink.report()` with a `rule_ref` for every `<production>` code. EOF errors (`found="EOF"`) and SYN-MISSING-SEMICOLON get a zero-width `span_end` by default, so the parser need not pass one for them.
- **Plan 007 (semantic)** relies on the phase-dependent quoting rule: semantic `{expected}` items (type names, counts) are inserted raw. If a syntax template ever needs raw items, write `'{expected}'` in the template; do not quote or unquote in the caller.
- `catalog.load_grammar_rules()` depends on the heading `## 2. Syntax grammar` and the first `ebnf` block after it in `docs/language-spec.md`. If that heading is renamed, `report()` will fail with `ValueError` from `str.index`.
- The lexer is linear and builds a position table of `len(source) + 1` tuples. That is fine for course-sized files. If very large inputs ever matter, replace `_positions` with incremental tracking.
- Reviewer focus: `_char` (escape hiding when finding the closing quote), the order of the two records in an unterminated string with a bad escape, `_at_line_start`, and that no test reads `tests/corpus/heldout/`.
- The include regex accepts trailing comments per the amended contract §3. A `/*` left open after an include is deliberately not treated as a comment start (the directive owns its line), unlike a C preprocessor. If this confuses students, report it; do not change the lexer alone.
