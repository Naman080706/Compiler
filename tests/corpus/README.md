# Test corpus: faulty and valid C programs

## 1. Purpose

This folder is the pytest suite's input and the PRD's evaluation set. Each
`.c` program is a small, realistic student-style program for the strict C99
subset described in `docs/language-spec.md`. Each has a sidecar
`.expected.json` that records the root causes the compiler should report.

- `dev/` is the development set. Use it freely while building the lexer,
  parser, semantic checks, clustering (F2) and fix verification (F8).
- `heldout/` holds exactly 20 faulty programs. They are the PRD's "20 faulty
  programs" for the success metrics (milestone 5).
- `valid/` holds programs that must compile with no fatal errors. A few of
  them intentionally expect warnings.

The design rule behind the gcc cross-check is: **every program the compiler
accepts is valid C99.** `tools/gcc_check.py` enforces it.

## 2. Layout and naming

```
tests/corpus/
  README.md
  dev/       NNN-short-slug.c + NNN-short-slug.expected.json
  heldout/   exactly 20 programs, 001-...020-...
  valid/     >= 10 programs
```

- File names match `^\d{3}-[a-z0-9]+(-[a-z0-9]+)*\.c$`: three digits, a hyphen
  and a lowercase kebab slug. Numbers are unique within a folder. The sidecar
  is the same stem plus `.expected.json`, for example `023-arg-count-too-few.c`
  and `023-arg-count-too-few.expected.json`.
- `dev/` numbering:
  - `001`-`037`: one single-fault program per catalog code, in the catalog
    order. File `NNN` targets code `#NNN` of `docs/error-catalog.md`.
  - `040`-`059`: cascading programs (at least 10).
  - `060`-`069`: programs with 2-3 independent faults (at least 3).
  - `070`-`099`: course-level C (milestone 6): one program per new semantic code, plus programs for the features that are still unsupported (`goto`, function pointers, bit-fields, variadic definitions, `#ifdef`) which the gcc fallback handles. `valid/013`-`022` cover the new features.
- Every `.c` file ends with exactly one `\n` and has no trailing blank lines.
  The last line contains code (for example the final `}`), not only a comment.
  The one exception is a program whose injected fault is an unterminated block
  comment. Together these make the file's line count equal to the line of its
  last token, which is where EOF is located.
- Sidecar JSON: UTF-8, 2-space indent, keys in the schema order below.

## 3. Sidecar schema

Exact; no other keys.

| Field | Type | Meaning |
|---|---|---|
| `description` | str (non-empty) | One sentence: what the program does and what is wrong with it. |
| `split` | `"dev"` \| `"heldout"` \| `"valid"` | Must equal the folder name. |
| `injected_faults` | list of str | One entry per deliberately injected fault, in plain English with its line. `[]` for valid programs. A single-fault or cascading program has exactly 1 entry; a multi-fault program has 2 or 3. |
| `roots` | list of `{"code": str, "line": int}` | The **root causes F2 should display**: fatal codes only, one per injected fatal fault, at the line given by the location convention. Never list cascade symptoms. Valid programs: `[]`. |
| `warnings` | list of `{"code": str, "line": int}` | Warnings (`WRN-*` only) the compiler must report. Must be `[]` if any root is a `LEX-` or `SYN-` code. |
| `cascading` | bool | `true` if one fault is expected to produce several symptoms (many records under one root). Valid programs: `false`. |
| `fixable` | bool | `true` if every injected fault can be fixed by editing **at most 3 lines** near the root cause (the injected fault's location) without changing what the program is meant to do. Valid programs: `false`. |
| `gcc_rejects` | bool | Whether `gcc -std=c99 -pedantic-errors -fsyntax-only <file>` exits non-zero. **Recorded by running gcc.** Valid programs: always `false`. |
| `notes` | str (may be empty) | Anything useful: which symptoms the cascade should produce, where gcc reports the error, why `gcc_rejects` is false, etc. |

Raw error counts are deliberately not recorded: the counts depend on the
compiler's recovery strategy.

`gcc_rejects` is legitimately `false` for some faulty programs, wherever the
subset is stricter than gcc: SEM-BAD-ARRAY-SIZE (gcc accepts variable-length
arrays), SEM-MISSING-MAIN (a link-time error in real C), LEX-UNSUPPORTED-DIRECTIVE,
SYN-UNSUPPORTED-FEATURE and every warning-only program. The one hard rule goes
the other way: **empty `roots` implies gcc must accept the file.**

## 4. Location convention

The sidecars record only `line`. Columns are not recorded.

- **SYN-MISSING-SEMICOLON** is reported at the line and column immediately
  after the last token of the unterminated statement. Its `line` is therefore
  the line of the statement missing the `;`, not the line of the next token.
- **Every other syntax error** is at the **found token**, i.e. the token the
  parser could not accept.
- **Lexical errors** are at the first bad character. For an unterminated
  string, char literal or block comment, that is the opening `"`, `'` or `/*`.
- **Semantic errors** are at the offending identifier or operator:
  - SEM-UNDECLARED-VAR and SEM-UNDECLARED-FUNC: at the first use. Later uses
    are symptoms grouped under it.
  - SEM-REDECLARED and SEM-CONFLICTING-TYPES: at the later declaration's name.
  - SEM-ARG-COUNT, SEM-ARG-TYPE and SEM-PRINTF-FORMAT: at the called
    function's name.
- **Warnings** are at the declaration or statement they concern:
  - WRN-UNUSED-VAR: at the variable's name in its declaration.
  - WRN-MISSING-RETURN: at the function's name in its definition.
  - WRN-UNREACHABLE-CODE: at the first unreachable statement, not at the
    `return`.
  - WRN-ASSIGN-IN-CONDITION and WRN-IMPLICIT-NARROWING: at the statement or
    declaration containing the `=`.
- **EOF** is located immediately after the last token of the file, so its
  `line` is the line of the last token. Under the authoring rule above, that
  equals the number of lines, `len(text.splitlines())`. This applies to
  SYN-UNEXPECTED-EOF. SEM-MISSING-MAIN is also reported at EOF, because it is
  detected at the end of semantic analysis.
- **Missing `}`**: a function definition cannot appear inside a block in this
  subset. When the parser is inside a block and sees `type_spec IDENT (` at the
  start of a statement, it reports the missing `}` there, at that type keyword,
  as SYN-UNBALANCED-BRACKET (the expected set is just `}`). This is one record,
  and the following function is parsed normally. If no further function
  follows, the parser reaches EOF and reports SYN-UNEXPECTED-EOF.
- **Authoring rule:** keep each faulty construct on **one line** so the line is
  unambiguous. Multi-line statements are only allowed in cascading programs,
  and then only away from the root.

**Worked examples** (left numbers are file line numbers):

1. Missing `;` followed by a comment and a blank line:
   ```c
   5:     total = total + price
   6:     // apply the discount next
   7:
   8:     count++;
   ```
   The parser only notices the problem at `count` (line 8), and gcc reports
   line 8 too. Our convention reports it just after `price`, so the root is
   `{"code": "SYN-MISSING-SEMICOLON", "line": 5}`.

2. Missing `}`, reported at the next function's type keyword:
   ```c
    3: int max(int a, int b) {
    4:     if (a > b) {
    5:         return a;
    6:     return b;
    7: }
    8:
    9: int main(void) {
   10:     printf("%d\n", max(3, 4));
   ```
   The fault is the missing `}` after line 5. The `}` on line 7 closes the `if`
   block, so `max`'s body is still open. The parser meets `int main (` at line
   9, which is the found token where `}` was expected. Root:
   `{"code": "SYN-UNBALANCED-BRACKET", "line": 9}`. `fixable` is still `true`:
   the fix is one added line near the injected fault (after line 5). The "near
   the root" in the `fixable` definition refers to the root **cause**, not the
   reported line.

3. Missing `}` in the **last** function, reported at EOF. If the same `max`
   function were the last thing in a 7-line file, the parser would reach EOF
   while `max`'s body is open. Root:
   `{"code": "SYN-UNEXPECTED-EOF", "line": 7}`, where 7 is the file's line
   count.

4. Unterminated block comment:
   ```c
   20: }
   21: /* TODO: handle negative marks
   22:    and print a warning
   ```
   The file ends after line 22 and the comment is never closed with `*/`. The
   error is at the `/*` on line 21, not at EOF (line 22). Root:
   `{"code": "LEX-UNTERMINATED-COMMENT", "line": 21}`.

## 5. Held-out rule

> **RULE:** files in `heldout/` must never be read or used when designing or tuning parser recovery, clustering (F2) heuristics, prompts or fix strategies. They are used only for the milestone-5 evaluation (`pytest -m heldout` and the metrics). If a heldout program reveals a bug, fix the bug using a new `dev/` program that reproduces it, never by looking at the heldout file again. `tools/gcc_check.py` and the schema test read heldout sidecars only to validate the corpus itself. That is allowed.

## 6. Compiler interface contract (milestone 1 must implement this)

- Module `cea.pipeline` (file `src/cea/pipeline.py`; `pyproject.toml` already
  puts `src/` on pytest's path).
- `compile_source(source: str, filename: str) -> result`. It runs the lexical,
  syntax and semantic phases on the text and never raises on bad input.
- `result.errors` is a list of records (dataclass or object) with these
  attributes:
  - `id: str`, unique within one result, e.g. `"E-0001"`;
  - `code: str`, a catalog code;
  - `line: int` and `column: int`, both 1-based, following the location
    convention above;
  - `severity: str`, `"fatal"` or `"warning"`, taken from the catalog;
  - `phase: str`, `"lexical"`, `"syntax"` or `"semantic"`;
  - `root_id: str`, the `id` of the root record of its cluster (a root's
    `root_id` equals its own `id`);
  - `caused_by: str | None`, the `id` of the record that directly caused it, or
    `None` if no cause is known (always `None` for roots).
- Records also carry the PRD fields `found`, `expected`, `snippet` and
  `rule_ref`, plus the additions `language`, `span_end` and `message`. The test
  does not check them.
- `tests/test_corpus_compile.py` checks that every expected root and warning
  appears as a record with the same `(code, line)`, and that `valid/` programs
  have no fatal records. Since plan 009 (F2 clustering) it also checks, for
  `dev/` and `valid/`, that the `(code, line)` list of fatal roots (records
  with `root_id == id` and severity `fatal`) equals the sidecar `roots`
  exactly. Warnings keep the subset check, and `heldout/` keeps only the
  subset check until milestone 5.

## 7. How to run

Set up once (from the project root, Git Bash):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

Then:

```bash
.venv/Scripts/python -m pytest -q              # everything except heldout
.venv/Scripts/python -m pytest -q -m heldout   # held-out evaluation tests (milestone 5)
.venv/Scripts/python -m pytest -q -m gcc       # gcc cross-check through pytest
python -I tools/gcc_check.py                   # gcc cross-check, standalone
```

## 8. Authoring rules

1. **Real student-style code.** Each program is a meaningful small program, not
   a single line. Single-fault `dev` programs are 10-30 lines; `heldout`
   programs are 15-40 lines.
2. **Each `dev` single-fault program triggers ONLY its intended code.** Exactly
   one injected fault, and no accidental extra faults: no unused locals, no
   float-to-int narrowing, no missing returns, no assignment in a condition, no
   unreachable code, and no undeclared functions. Symptoms that the fault
   itself causes are allowed (describe them in `notes`), but `roots` and
   `warnings` list only the intended code.
3. **Supported subset only.** The exceptions are `dev/007` (LEX-UNSUPPORTED-DIRECTIVE),
   `dev/015` (SYN-UNSUPPORTED-FEATURE) and any program deliberately testing
   those two codes.
4. **`#include <stdio.h>`** as the first line of every program that calls
   `printf`, except where the missing include *is* the injected fault.
5. **Missing `;` faults.** Put the statement missing its `;` before a line that
   starts with an identifier, a keyword or `}`. Never before a line starting
   with `(`, `[`, `+`, `-`, `++`, `--` or another operator: those would legally
   continue the expression.
6. **Warning-only faulty programs** (`roots == []`) must be accepted by gcc.
   `tools/gcc_check.py` enforces this.
7. **Programs with a `LEX-` or `SYN-` root** must not contain any warning
   trigger. Their `warnings` is `[]`; the schema test enforces this.
8. **Run gcc on every program** and copy the result into `gcc_rejects`. Use
   `true` if the exit code is non-zero.

## 7. Course-level C and the gcc fallback

Sidecars describe what **our own compiler** reports (`compile_source(..., engine="cea")`); the corpus tests never use the gcc fallback.
Programs that became valid when switch, pointers, structs, `const` and more were added keep their slot:
heldout `020-menu-switch` now has empty `roots`, empty `injected_faults` and a `notes` text that starts with `NOW VALID`
(the schema test accepts that marker). `WRN-INCOMPATIBLE-POINTER` programs are accepted by plain `gcc -std=c99` but rejected by
`-pedantic-errors`; `tools/gcc_check.py` checks them with plain gcc.
