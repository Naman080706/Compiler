# Plan 003: Build the faulty/valid C program corpus and the pytest harness

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. Do **not** edit `plans/README.md`: the advisor
> maintains the index. End your final report with a **Viva notes** list
> (decisions, trade-offs or deviations an examiner might ask about).
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat 85702b6..HEAD -- tests/ tools/gcc_check.py pyproject.toml requirements-dev.txt`
>    must print **nothing**. If it prints anything, someone has already started
>    this work. STOP and report.
> 2. `test -f docs/error-catalog.md && grep -cE '^\| (LEX|SYN|SEM|WRN)-' docs/error-catalog.md`
>    must print `37`. If the file is missing (plan 001 is not merged into `main`)
>    or the count is not 37, STOP and report.
>
> HEAD will be later than `85702b6`, because plan 001's commits (`docs/`,
> `tools/check_spec.py`) land in between. That is expected. Only the paths above
> must be unchanged.

## Status

- **Priority**: P1
- **Effort**: L (about 90 small C programs plus their sidecars, and a small harness)
- **Risk**: LOW (test data and test code only; no compiler code)
- **Depends on**: `plans/001-define-c-subset-and-error-catalog.md` (it creates `docs/language-spec.md` and `docs/error-catalog.md`). This plan does **not** depend on plan 002 (lexer/parser), because the location convention below is fixed here and shared with 002.
- **Category**: tests
- **Planned at**: commit `85702b6`, 2026-10-10

## Why this matters

The project is a "Compiler Error Assistant": a course compiler for a strict C99 subset, written in Python, plus an AI layer. The AI layer captures errors per phase (F1), clusters cascades under root causes (F2), explains them, and verifies proposed fixes by re-compiling (F8). The PRD's success metrics are measured "on 20 faulty programs" with known injected faults. Its tech stack says testing is "pytest with a folder of faulty programs and expected root causes", which "doubles as the evaluation set for the metrics".

The owner decided to build this corpus **before** milestone 1. Every milestone then gets automatic pass/fail tests from day one: F1 (records at the right line), F2 (one root per cascade), F8 (fixable faults). This plan builds that corpus, a sidecar format recording the expected root causes, a schema test that runs now, a compiler contract test that skips until milestone 1, and a gcc cross-check. The gcc cross-check enforces the project's design rule: **every program the compiler accepts is valid C99**.

## Current state

- The repo is at `C:\Users\Naman\OneDrive\Desktop\Compiler project`, branch `main`, no remote. Planned at `85702b6` ("Initial commit: PRD, project README, viva notes and plan 001"). There is **no code**: no `src/`, no `tests/`, no `pyproject.toml`.
- After plan 001 is merged, these exist. Read them; do not edit them:
  - `docs/language-spec.md`: the C subset (lexical grammar, syntax grammar, types, 16 `sem.*` rules, an example program, the unsupported-feature list).
  - `docs/error-catalog.md`: the **37 error codes**. It is one markdown table with columns `Code | Phase | Severity | Category | rule_ref | Message template | Example trigger`, and every row starts with `| LEX-`, `| SYN-`, `| SEM-` or `| WRN-`. After the table is a section "Choosing among syntax codes".
  - `tools/check_spec.py`: plan 001's spec/catalog checker. Not touched here.
- `.gitignore` already ignores `.venv/`, `__pycache__/` and `.pytest_cache/`.
- `git config core.autocrlf` is `true` on this machine. Files are checked out with CRLF. Python's `read_text` and gcc both handle that, and line counts are unaffected.
- Environment: Windows 11, Python 3.13.1 as `python`, `gcc (GCC) 12.4.0` on PATH. **pytest is not installed globally**; this plan installs it in `.venv/`.

### The 37 codes (from plan 001; `WRN-*` are warnings, everything else is fatal)

| # | Code | Category | Catalog example trigger |
|---|---|---|---|
| 1 | LEX-INVALID-CHAR | malformed-token | `int x = 5 @ 2;` |
| 2 | LEX-UNTERMINATED-STRING | unclosed-delimiter | `printf("hi);` |
| 3 | LEX-BAD-CHAR-LITERAL | malformed-token | `char c = 'ab';` |
| 4 | LEX-UNTERMINATED-COMMENT | unclosed-delimiter | `/* note` at end of file |
| 5 | LEX-MALFORMED-NUMBER | malformed-token | `int x = 12abc;` |
| 6 | LEX-INVALID-ESCAPE | malformed-token | `printf("a\q");` |
| 7 | LEX-UNSUPPORTED-DIRECTIVE | syntax-structure | `#define N 10` |
| 8 | SYN-MISSING-SEMICOLON | missing-semicolon | `int x = 5` then next line |
| 9 | SYN-UNBALANCED-BRACKET | unclosed-delimiter | `if (x > 1 { }` |
| 10 | SYN-EXPECTED-TOKEN | syntax-structure | `while x > 1) { }` |
| 11 | SYN-EXPECTED-EXPRESSION | syntax-structure | `int x = ;` |
| 12 | SYN-EXPECTED-TYPE | syntax-structure | `int f(a) { }` |
| 13 | SYN-UNEXPECTED-EOF | unclosed-delimiter | `int main() { return 0;` |
| 14 | SYN-INVALID-ASSIGN-TARGET | syntax-structure | `5 = x;` |
| 15 | SYN-UNSUPPORTED-FEATURE | syntax-structure | `int *p;` |
| 16 | SEM-UNDECLARED-VAR | undeclared-identifier | `y = 3;` with no `y` |
| 17 | SEM-UNDECLARED-FUNC | undeclared-identifier | `foo(1);` before `foo` is declared |
| 18 | SEM-REDECLARED | redeclaration | `int x; int x;` in one block |
| 19 | SEM-CONFLICTING-TYPES | function-misuse | `int f(int a);` then `float f(int a) {...}` |
| 20 | SEM-TYPE-MISMATCH | type-mismatch | `int x = "hi";` |
| 21 | SEM-VOID-VALUE | type-mismatch | `int x = log();` where `void log()` |
| 22 | SEM-NOT-CALLABLE | function-misuse | `int x; x(1);` |
| 23 | SEM-ARG-COUNT | function-misuse | `add(1);` for `int add(int a, int b)` |
| 24 | SEM-ARG-TYPE | function-misuse | `add(1, "two");` |
| 25 | SEM-RETURN-TYPE | function-misuse | `return 5;` in `void f()` |
| 26 | SEM-NOT-ARRAY | type-mismatch | `int x; x[0] = 1;` |
| 27 | SEM-INDEX-NOT-INT | type-mismatch | `a[1.5] = 2;` |
| 28 | SEM-BAD-ARRAY-SIZE | type-mismatch | `int a[n];` |
| 29 | SEM-BREAK-OUTSIDE-LOOP | control-flow | `break;` in `main` body |
| 30 | SEM-NONCONST-GLOBAL-INIT | syntax-structure | `int y = x + 1;` at file scope |
| 31 | SEM-PRINTF-FORMAT | function-misuse | `printf(x);` |
| 32 | SEM-MISSING-MAIN | control-flow | file with only `void g() { }` |
| 33 | WRN-UNUSED-VAR | unused-code | `int t = 1;` never read |
| 34 | WRN-UNREACHABLE-CODE | unused-code | `return 0; printf("x");` |
| 35 | WRN-IMPLICIT-NARROWING | type-mismatch | `int n = 2.5;` |
| 36 | WRN-MISSING-RETURN | control-flow | `int f(int b) { if (b) { return 1; } }` |
| 37 | WRN-ASSIGN-IN-CONDITION | type-mismatch | `if (x = 5) { }` |

The 10 categories are `malformed-token`, `unclosed-delimiter`, `missing-semicolon`, `syntax-structure`, `undeclared-identifier`, `redeclaration`, `type-mismatch`, `function-misuse`, `control-flow` and `unused-code`.

If `docs/error-catalog.md` disagrees with this table, the **catalog file wins**. If the difference changes which codes exist, STOP.

### The C subset in one paragraph (details in `docs/language-spec.md`)

**Supported:**
- types `int char float double void`
- globals with literal initialisers only
- locals, including `int a, b = 2;`
- 1-D arrays with an integer-literal size and no initialiser list
- functions, prototypes and recursion
- `if/else`, `while`, `for` (with `for (int i = 0; ...)`), `break` and `continue`
- `+ - * / %`, comparisons, `&& || !`, `= += -= *= /= %=`, `++` and `--`
- `printf` with a string-literal first argument, only after `#include <stdio.h>`
- `//` and `/* */` comments
- escapes `\n \t \0 \' \" \\` only

**Not supported:**
- pointers, `&`, `->`, `.`, `struct`, `union`, `enum`, `typedef`
- `switch`, `do`, `goto`, `sizeof`, `?:`, bitwise operators
- `long`, `short`, `unsigned`, `signed`, `const`, `static`, `extern`, `auto`, `register`, `volatile`
- `scanf`, string variables such as `char s[6] = "hello"`, array parameters
- any directive except `#include <stdio.h>`

**Semantic traps that silently add diagnostics:**
- A local that is never **read** gives WRN-UNUSED-VAR. A variable that is only assigned counts as never read.
- A float-to-int conversion in an initialisation, assignment, argument or return gives WRN-IMPLICIT-NARROWING.
- A non-void function other than `main` whose last statement is not a `return` (or an `if` with an `else` where every path returns) gives WRN-MISSING-RETURN. Loops never count.
- A plain `=` as the outermost operator of a condition gives WRN-ASSIGN-IN-CONDITION.
- Any statement directly after `return`, `break` or `continue` in the same block gives WRN-UNREACHABLE-CODE.
- Functions must be declared earlier in the file than any call.

### Verified gcc behaviour (gcc 12.4.0, `-std=c99 -pedantic-errors -fsyntax-only`, probed while planning)

| Snippet | gcc exit |
|---|---|
| call to an undeclared function (implicit declaration) | 1 (rejects) |
| `printf(x);` with `int x` | 1 |
| `int x = "hi";` | 1 |
| `return 5;` in a `void` function / `return;` in an `int` function | 1 / 1 |
| `int n = 3; int a[n];` (VLA) | **0 (accepts)** |
| file with only `void g(void){ }` (no main) | **0** (missing main is a link-time error) |
| `if (x = 5)` | **0** (warning only) |

So `gcc_rejects` is legitimately `false` for some faulty programs. This happens wherever the subset is stricter than gcc: SEM-BAD-ARRAY-SIZE, SEM-MISSING-MAIN, LEX-UNSUPPORTED-DIRECTIVE, SYN-UNSUPPORTED-FEATURE, possibly LEX-BAD-CHAR-LITERAL, and every warning-only program. This is fine. The only hard rule is in the other direction: **empty `roots` ⇒ gcc must accept**. Always record `gcc_rejects` by running gcc. Never guess.

## Commands you will need

Run all commands from the project root in **Git Bash** (paths use `/`).

| Purpose | Command | Expected on success |
|---|---|---|
| Create venv | `python -m venv .venv` | exit 0, `.venv/` exists |
| Install dev deps | `.venv/Scripts/python -m pip install -r requirements-dev.txt` | exit 0 |
| pytest version | `.venv/Scripts/python -m pytest --version` | `pytest 8.x.y` |
| Full suite | `.venv/Scripts/python -m pytest -q` | at the end: `<N+10> passed, 1 skipped` (N = number of `.c` files) |
| Partial-corpus suite (steps 3–6) | `.venv/Scripts/python -m pytest -q -k "not test_dev_ and not test_heldout_ and not test_valid_"` | `<N+6> passed, 1 skipped, 4 deselected` |
| Held-out evaluation tests | `.venv/Scripts/python -m pytest -q -m heldout` | `1 skipped, <M> deselected` until milestone 1 |
| gcc cross-check | `python -I tools/gcc_check.py` | last line `gcc_check: N files checked, R rejected by gcc, A accepted, 0 mismatches`, exit 0 |
| gcc on one file | `gcc -std=c99 -pedantic-errors -fsyntax-only tests/corpus/dev/023-arg-count-too-few.c; echo "exit=$?"` | `exit=1` for that file |
| Dev code coverage | see the `COVERAGE` command below | `MISSING: [...]` |

`COVERAGE` command (prints the catalog codes that no `dev` sidecar uses yet):

```bash
.venv/Scripts/python -c "import sys; sys.path.insert(0, 'tests'); import corpus_lib as c; cat = c.load_catalog(); used = {e['code'] for _, p in c.c_files('dev') for s in [c.load_sidecar(p)] for e in s['roots'] + s['warnings']}; print('MISSING:', sorted(set(cat) - used))"
```

Exact pass counts: `test_corpus_schema.py` has 9 fixed tests plus one `test_sidecar_schema[...]` per `.c` file, and `test_gcc_crosscheck.py` adds 1. `test_corpus_compile.py` skips as a whole module (`1 skipped`). The `-k` filter in the partial-corpus row deselects the 4 aggregate tests (`test_dev_covers_every_catalog_code`, `test_dev_has_cascading_and_multi_fault_programs`, `test_heldout_size_and_coverage`, `test_valid_size`), which cannot pass until the corpus is complete.

## Scope

**In scope** (create only these):
- `pyproject.toml`
- `requirements-dev.txt`
- `tests/corpus_lib.py`: shared helpers (stdlib only)
- `tests/test_corpus_schema.py`
- `tests/test_corpus_compile.py`
- `tests/test_gcc_crosscheck.py`
- `tools/gcc_check.py`
- `tests/corpus/README.md`
- `tests/corpus/dev/*.c` and `tests/corpus/dev/*.expected.json`
- `tests/corpus/heldout/*.c` and `tests/corpus/heldout/*.expected.json`
- `tests/corpus/valid/*.c` and `tests/corpus/valid/*.expected.json`
- `.venv/` (local, git-ignored, never committed)

**Out of scope** (do NOT touch):
- `src/`. Do **not** create the `src/cea` package or any compiler code; milestone 1 does that. The compile test is designed to skip until then.
- `docs/` (including `docs/error-catalog.md` and `docs/language-spec.md`). If a catalog code seems impossible to trigger in isolation, **report it; do not edit the catalog**.
- `tools/check_spec.py`, `README.md`, `VIVA.md`, `plans/` (including `plans/README.md`) and `cd project prd.docx`.
- `.gitignore` (it already covers `.venv/`).
- Do not add dependencies beyond `pytest>=8,<9`. Do not add `[build-system]` or packaging config; milestone 1 owns that.

## Git workflow

- Start from up-to-date `main` (with plan 001 merged): `git switch main && git switch -c advisor/003-test-corpus`.
- Commit once per step (steps 1–7). Use this message style, ending with a blank line and the trailer:

  ```bash
  git add <files> && git commit -F - <<'MSG'
  test: add pytest skeleton and dev requirements (plan 003 step 1)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  MSG
  ```
- Never `git add .venv`. Run `git status --short` before each commit and add only in-scope paths.
- Do NOT push, merge or open a PR.

## Corpus specification (read fully before Step 3)

### Layout and naming

```
tests/corpus/
  README.md
  dev/       NNN-short-slug.c + NNN-short-slug.expected.json
  heldout/   exactly 20 programs, 001-...020-...
  valid/     >= 10 programs
```

- File names match `^\d{3}-[a-z0-9]+(-[a-z0-9]+)*\.c$`: three digits, a hyphen and a lowercase kebab slug. Numbers are unique within a folder. The sidecar is the same stem plus `.expected.json`, e.g. `023-arg-count-too-few.c` and `023-arg-count-too-few.expected.json`.
- `dev/` numbering:
  - `001`–`037`: one single-fault program per catalog code, in the catalog order of the table above. File `NNN` targets code `#NNN`.
  - `040`–`059`: cascading programs (at least 10).
  - `060`–`069`: programs with 2–3 independent faults (at least 3).
- Every `.c` file ends with **exactly one** `\n` and has no trailing blank lines. The schema test enforces this. In addition, **the last line must contain code** (for example the final `}`), not only a comment. The one exception is a program whose injected fault is an unterminated block comment. Together these make the file's line count equal to the line of its last token, which is where plan 002 places EOF.
- Sidecar JSON: UTF-8, 2-space indent, keys in the schema order below.

### Sidecar schema (exact; no other keys)

| Field | Type | Meaning |
|---|---|---|
| `description` | str (non-empty) | One sentence: what the program does and what is wrong with it. |
| `split` | `"dev"` \| `"heldout"` \| `"valid"` | Must equal the folder name. |
| `injected_faults` | list of str | One entry per deliberately injected fault, in plain English with its line. `[]` for valid programs. A single-fault or cascading program has exactly 1 entry; a multi-fault program has 2 or 3. |
| `roots` | list of `{"code": str, "line": int}` | The **root causes F2 should display**: fatal codes only, one per injected fatal fault, at the line given by the location convention. Never list cascade symptoms. Valid programs: `[]`. |
| `warnings` | list of `{"code": str, "line": int}` | Warnings (`WRN-*` only) the compiler must report. Must be `[]` if any root is a `LEX-` or `SYN-` code. |
| `cascading` | bool | `true` if one fault is expected to produce several symptoms (many records under one root). Valid programs: `false`. |
| `fixable` | bool | `true` if every injected fault can be fixed by editing **at most 3 lines** near the root cause (the injected fault's location) without changing what the program is meant to do. Valid programs: `false`. |
| `gcc_rejects` | bool | Whether `gcc -std=c99 -pedantic-errors -fsyntax-only <file>` exits non-zero. **Record it by running gcc.** Valid programs: always `false`. |
| `notes` | str (may be empty) | Anything useful: which symptoms the cascade should produce, where gcc reports the error, why `gcc_rejects` is false, etc. |

Do **not** record raw error counts. The compiler doesn't exist yet, and counts depend on recovery strategy.

### Location convention (shared with plan 002; do not change)

The sidecars record only `line`. Columns are not recorded.

- **SYN-MISSING-SEMICOLON** is reported at the line and column immediately after the last token of the unterminated statement. Its `line` is therefore the line of the statement missing the `;`, not the line of the next token.
- **Every other syntax error** is at the **found token**, i.e. the token the parser could not accept.
- **Lexical errors** are at the first bad character. For an unterminated string, char literal or block comment, that is the opening `"`, `'` or `/*`.
- **Semantic errors** are at the offending identifier or operator:
  - SEM-UNDECLARED-VAR and SEM-UNDECLARED-FUNC: at the first use. Later uses are symptoms grouped under it.
  - SEM-REDECLARED and SEM-CONFLICTING-TYPES: at the later declaration's name.
  - SEM-ARG-COUNT, SEM-ARG-TYPE and SEM-PRINTF-FORMAT: at the called function's name.
- **Warnings** are at the declaration or statement they concern:
  - WRN-UNUSED-VAR: at the variable's name in its declaration.
  - WRN-MISSING-RETURN: at the function's name in its definition.
  - WRN-UNREACHABLE-CODE: at the first unreachable statement, not at the `return`.
  - WRN-ASSIGN-IN-CONDITION and WRN-IMPLICIT-NARROWING: at the statement or declaration containing the `=`.
- **EOF** is located immediately after the last token of the file (plan 002 §8), so its `line` is the line of the last token. Under the authoring rule above, that equals the number of lines, `len(text.splitlines())`. This applies to SYN-UNEXPECTED-EOF. SEM-MISSING-MAIN is also reported at EOF, because it is detected at the end of semantic analysis.
- **Missing `}`**: a function definition cannot appear inside a block in this subset. When the parser is inside a block and sees `type_spec IDENT (` at the start of a statement, it reports the missing `}` there, at that type keyword, as SYN-UNBALANCED-BRACKET (the expected set is just `}`). This is plan 002's §4.7 repair: one record, and the following function is parsed normally. If no further function follows, the parser reaches EOF and reports SYN-UNEXPECTED-EOF.
- **Authoring rule:** keep each faulty construct on **one line** so the line is unambiguous. Multi-line statements are only allowed in cascading programs, and then only away from the root.

**Worked examples** (left numbers are file line numbers):

1. Missing `;` followed by a comment and a blank line:
   ```c
   5:     total = total + price
   6:     // apply the discount next
   7:
   8:     count++;
   ```
   The parser only notices the problem at `count` (line 8), and gcc reports line 8 too. Our convention reports it just after `price`, so the root is `{"code": "SYN-MISSING-SEMICOLON", "line": 5}`.

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
   The fault is the missing `}` after line 5. The `}` on line 7 closes the `if` block, so `max`'s body is still open. The parser meets `int main (` at line 9, which is the found token where `}` was expected. Root: `{"code": "SYN-UNBALANCED-BRACKET", "line": 9}`. `fixable` is still `true`: the fix is one added line near the injected fault (after line 5). The "near the root" in the `fixable` definition refers to the root **cause**, not the reported line.

3. Missing `}` in the **last** function, reported at EOF. If the same `max` function were the last thing in a 7-line file, the parser would reach EOF while `max`'s body is open. Root: `{"code": "SYN-UNEXPECTED-EOF", "line": 7}`, where 7 is the file's line count.

4. Unterminated block comment:
   ```c
   20: }
   21: /* TODO: handle negative marks
   22:    and print a warning
   ```
   The file ends after line 22 and the comment is never closed with `*/`. The error is at the `/*` on line 21, not at EOF (line 22). Root: `{"code": "LEX-UNTERMINATED-COMMENT", "line": 21}`.

### Quality rules for every C program

1. **Real student-style code.** Each program is a meaningful small program, not a single line. Single-fault `dev` programs are 10–30 lines; `heldout` programs are 15–40 lines. Examples: summing marks, finding a maximum, a grade classifier, a factorial, a times table, counting vowels by character codes, temperature conversion, prime checking, a running average.
2. **Each `dev` single-fault program triggers ONLY its intended code.** Exactly one injected fault, and no accidental extra faults: no unused locals, no float-to-int narrowing, no missing returns, no assignment in a condition, no unreachable code, and no undeclared functions (put prototypes or definitions before use). Symptoms that the fault itself causes are allowed (describe them in `notes`), but `roots` and `warnings` list only the intended code.
3. **Supported subset only.** Use only plan 001's supported subset. The exceptions are `007` (LEX-UNSUPPORTED-DIRECTIVE), `015` (SYN-UNSUPPORTED-FEATURE) and any program deliberately testing those two codes.
4. **`#include <stdio.h>`** as the first line of every program that calls `printf`, except where the missing include *is* the injected fault.
5. **Missing `;` faults.** Put the statement missing its `;` before a line that starts with an identifier, a keyword or `}`. Never put it before a line starting with `(`, `[`, `+`, `-`, `++`, `--` or another operator: those would legally continue the expression.
6. **Warning-only faulty programs** (`roots == []`) must be accepted by gcc. `tools/gcc_check.py` enforces this.
7. **Programs with a `LEX-` or `SYN-` root** must not contain any warning trigger. Their `warnings` is `[]`; the schema test enforces this. Whether semantic warnings survive a syntax error depends on recovery, so we do not test it here.
8. **Run gcc on every program** and copy the result into `gcc_rejects`. Use `true` if the exit code is non-zero.

### Pattern 1: `dev` single-fault program (verified with gcc 12.4.0: exit 1)

`tests/corpus/dev/023-arg-count-too-few.c`:

```c
#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

int main(void) {
    int total = 0;
    int i;
    for (i = 1; i <= 5; i++) {
        total = add(total);
    }
    printf("total = %d\n", total);
    return 0;
}
```

`tests/corpus/dev/023-arg-count-too-few.expected.json`:

```json
{
  "description": "Loop accumulates with add() but the call passes one argument instead of two.",
  "split": "dev",
  "injected_faults": [
    "line 11: call add(total) is missing its second argument (should be add(total, i))"
  ],
  "roots": [
    {"code": "SEM-ARG-COUNT", "line": 11}
  ],
  "warnings": [],
  "cascading": false,
  "fixable": true,
  "gcc_rejects": true,
  "notes": "Single fault. Line 11 is the line of the identifier 'add' in the call. gcc: 11:17 too few arguments to function 'add'."
}
```

### Pattern 2: `dev` cascading program (verified with gcc 12.4.0: exit 1)

`tests/corpus/dev/040-missing-semicolon-decl-cascade.c`:

```c
#include <stdio.h>

int main(void) {
    int scores[5];
    int count = 0
    int i;
    for (i = 0; i < 5; i++) {
        scores[i] = i * 10;
        count += 1;
    }
    if (count > 3) {
        printf("count is %d\n", count);
    }
    count = count * 2;
    printf("final %d %d\n", count, scores[0]);
    return 0;
}
```

`tests/corpus/dev/040-missing-semicolon-decl-cascade.expected.json`:

```json
{
  "description": "Declaration 'int count = 0' lacks its ';', so the parser can lose both 'count' and the next declaration 'int i'.",
  "split": "dev",
  "injected_faults": [
    "line 5: missing ';' at the end of 'int count = 0'"
  ],
  "roots": [
    {"code": "SYN-MISSING-SEMICOLON", "line": 5}
  ],
  "warnings": [],
  "cascading": true,
  "fixable": true,
  "gcc_rejects": true,
  "notes": "Cascade: depending on recovery, uses of 'i' (lines 7-8) and 'count' (lines 9, 11, 12, 14, 15) become SEM-UNDECLARED-VAR symptoms (10+ records), all under the one root. gcc reports line 6 col 5 (before 'int') and then 'i' undeclared; our convention reports line 5, just after '0'."
}
```

## Steps

### Step 0: Preconditions

Run the drift check at the top of this plan. Then run:
- `python --version`, which must be ≥ 3.11;
- `gcc --version | head -1`, which should show `gcc (GCC) 12.4.0` (any gcc ≥ 9 is fine; if gcc is missing, see STOP conditions);
- `git status --short`, which must print nothing.

**Verify**: drift command prints nothing; catalog count is `37`; `git status --short` prints nothing.

### Step 1: Python project skeleton

On the new branch (see Git workflow), create `pyproject.toml` exactly:

```toml
[project]
name = "compiler-error-assistant"
version = "0.0.0"
description = "Course compiler for a C99 subset with an AI error-assistant layer"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-m 'not heldout'"
markers = [
    "corpus: tests driven by the C program corpus in tests/corpus",
    "heldout: evaluation-only tests over tests/corpus/heldout (milestone 5; deselected by default)",
    "gcc: cross-checks the corpus against gcc -std=c99 -pedantic-errors -fsyntax-only",
]
```

`pythonpath = ["src"]` lets milestone 1's `src/cea/pipeline.py` be imported by the tests without installing the package. `src/` does not need to exist yet; pytest tolerates that.

Create `requirements-dev.txt` containing exactly one line, `pytest>=8,<9`.

Then:
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

**Verify**:
- `.venv/Scripts/python -m pytest --version` → `pytest 8.` followed by a version.
- `git status --short` → only `?? pyproject.toml` and `?? requirements-dev.txt`. `.venv/` must not appear.

Commit: `test: add pytest skeleton and dev requirements (plan 003 step 1)`.

### Step 2: Harness, corpus README and the two pattern programs

Create the following files **exactly as given** (cosmetic formatting changes only).

`tests/corpus_lib.py`:

```python
"""Shared helpers for the corpus tests (plan 003). Stdlib only.

Test modules import it as ``import corpus_lib``. pytest puts the ``tests/``
folder on sys.path because that folder has no ``__init__.py``.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "corpus"
CATALOG = ROOT / "docs" / "error-catalog.md"
SPLITS = ("dev", "heldout", "valid")
SIDECAR_SUFFIX = ".expected.json"
CODE_ROW = re.compile(r"^\| (LEX|SYN|SEM|WRN)-")


def load_catalog():
    """Return {code: {"phase", "severity", "category"}} parsed from docs/error-catalog.md."""
    codes = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if CODE_ROW.match(line):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            codes[cells[0]] = {"phase": cells[1], "severity": cells[2], "category": cells[3]}
    return codes


def c_files(split=None):
    """Sorted list of (split, path) for every .c file in the corpus, or in one split."""
    out = []
    for s in SPLITS if split is None else (split,):
        out += [(s, p) for p in sorted((CORPUS / s).glob("*.c"))]
    return out


def sidecar_files(split=None):
    """Sorted list of (split, path) for every *.expected.json file."""
    out = []
    for s in SPLITS if split is None else (split,):
        out += [(s, p) for p in sorted((CORPUS / s).glob("*" + SIDECAR_SUFFIX))]
    return out


def sidecar_for(c_path):
    return c_path.with_name(c_path.stem + SIDECAR_SUFFIX)


def c_for(sidecar_path):
    return sidecar_path.with_name(sidecar_path.name[: -len(SIDECAR_SUFFIX)] + ".c")


def load_sidecar(c_path):
    return json.loads(sidecar_for(c_path).read_text(encoding="utf-8"))


def line_count(c_path):
    return len(c_path.read_text(encoding="utf-8").splitlines())
```

`tests/test_corpus_schema.py`:

```python
"""Structural checks on tests/corpus (plan 003). Runs before any compiler code exists."""
import re

import pytest

import corpus_lib as cl

pytestmark = pytest.mark.corpus

FIELDS = {
    "description": str, "split": str, "injected_faults": list, "roots": list,
    "warnings": list, "cascading": bool, "fixable": bool, "gcc_rejects": bool, "notes": str,
}
NAME_RE = re.compile(r"^\d{3}-[a-z0-9]+(-[a-z0-9]+)*\.c$")
ALL_C = cl.c_files()


@pytest.fixture(scope="module")
def catalog():
    if not cl.CATALOG.exists():
        pytest.fail("docs/error-catalog.md is missing; it is created by plan 001")
    return cl.load_catalog()


def test_catalog_has_37_codes(catalog):
    assert len(catalog) == 37, sorted(catalog)


def test_corpus_folders_exist():
    for split in cl.SPLITS:
        assert (cl.CORPUS / split).is_dir(), f"missing tests/corpus/{split}/"


def test_every_c_file_has_sidecar():
    missing = [str(p.relative_to(cl.CORPUS)) for _, p in ALL_C if not cl.sidecar_for(p).exists()]
    assert not missing, f"no sidecar for: {missing}"


def test_every_sidecar_has_c_file():
    orphans = [str(p.relative_to(cl.CORPUS)) for _, p in cl.sidecar_files() if not cl.c_for(p).exists()]
    assert not orphans, f"sidecar without .c: {orphans}"


def test_numbers_unique_per_split():
    for split in cl.SPLITS:
        nums = [p.name[:3] for _, p in cl.c_files(split)]
        dupes = sorted({n for n in nums if nums.count(n) > 1})
        assert not dupes, f"{split}: duplicate numbers {dupes}"


def _check_loc_list(value, field, n_lines, catalog, want_severity):
    seen = set()
    for item in value:
        assert isinstance(item, dict) and set(item) == {"code", "line"}, \
            f"{field} items must be objects with exactly 'code' and 'line': {item!r}"
        code, line = item["code"], item["line"]
        assert isinstance(code, str), f"{field}: code must be str: {item!r}"
        assert isinstance(line, int) and not isinstance(line, bool), f"{field}: line must be int: {item!r}"
        assert code in catalog, f"{field}: {code} is not in docs/error-catalog.md"
        assert catalog[code]["severity"] == want_severity, \
            f"{field}: {code} has severity {catalog[code]['severity']}, expected {want_severity}"
        assert 1 <= line <= n_lines, f"{field}: line {line} outside 1..{n_lines} for {code}"
        assert (code, line) not in seen, f"{field}: duplicate entry {item!r}"
        seen.add((code, line))


@pytest.mark.parametrize("split,c_path", ALL_C, ids=[f"{s}/{p.name}" for s, p in ALL_C])
def test_sidecar_schema(split, c_path, catalog):
    assert NAME_RE.match(c_path.name), f"bad file name {c_path.name} (want NNN-short-slug.c)"
    side = cl.load_sidecar(c_path)
    assert set(side) == set(FIELDS), \
        f"fields differ: extra={sorted(set(side) - set(FIELDS))} missing={sorted(set(FIELDS) - set(side))}"
    for name, typ in FIELDS.items():
        assert isinstance(side[name], typ), f"{name} must be {typ.__name__}"
    assert side["description"].strip(), "description is empty"
    assert side["split"] == split, f"split is {side['split']!r} but the file is in {split}/"
    assert all(isinstance(f, str) and f.strip() for f in side["injected_faults"]), \
        "injected_faults must be non-empty strings"
    text = c_path.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n"), \
        "file must end with exactly one newline (no trailing blank lines)"
    n = cl.line_count(c_path)
    _check_loc_list(side["roots"], "roots", n, catalog, "fatal")
    _check_loc_list(side["warnings"], "warnings", n, catalog, "warning")
    if split == "valid":
        assert side["roots"] == [], "valid programs must have empty roots"
        assert side["injected_faults"] == [], "valid programs have no injected faults"
        assert side["cascading"] is False and side["fixable"] is False, \
            "valid programs have cascading=false and fixable=false"
        assert side["gcc_rejects"] is False, "a valid program must be accepted by gcc"
    else:
        assert side["injected_faults"], "faulty programs must list their injected faults"
        assert side["roots"] or side["warnings"], "a faulty program must expect at least one diagnostic"
    if any(r["code"].startswith(("LEX-", "SYN-")) for r in side["roots"]):
        assert side["warnings"] == [], "programs with a LEX/SYN root must not expect warnings"
    if side["cascading"]:
        assert side["roots"], "a cascading program needs at least one root"
    if split == "heldout":
        assert 15 <= n <= 40, f"heldout programs must be 15-40 lines, got {n}"


def _sidecars(split):
    return [cl.load_sidecar(p) for _, p in cl.c_files(split)]


def test_dev_covers_every_catalog_code(catalog):
    used = {e["code"] for s in _sidecars("dev") for e in s["roots"] + s["warnings"]}
    missing = sorted(set(catalog) - used)
    assert not missing, f"codes with no dev program: {missing}"


def test_dev_has_cascading_and_multi_fault_programs():
    dev = _sidecars("dev")
    cascading = sum(1 for s in dev if s["cascading"])
    multi = sum(1 for s in dev if len(s["injected_faults"]) in (2, 3))
    assert cascading >= 10, f"dev has {cascading} cascading programs, need >= 10"
    assert multi >= 3, f"dev has {multi} programs with 2-3 faults, need >= 3"


def test_heldout_size_and_coverage(catalog):
    held = _sidecars("heldout")
    assert len(held) == 20, f"heldout must hold exactly 20 programs, has {len(held)}"
    cascading = sum(1 for s in held if s["cascading"])
    assert cascading >= 8, f"heldout has {cascading} cascading programs, need >= 8"
    cats = {catalog[e["code"]]["category"] for s in held for e in s["roots"] + s["warnings"]}
    assert len(cats) >= 8, f"heldout covers {len(cats)} categories {sorted(cats)}, need >= 8"


def test_valid_size():
    valid = _sidecars("valid")
    assert len(valid) >= 10, f"valid has {len(valid)} programs, need >= 10"
    with_warnings = sum(1 for s in valid if s["warnings"])
    assert with_warnings >= 2, f"{with_warnings} valid programs expect warnings, need >= 2"
```

`tests/test_corpus_compile.py` (the milestone-1 contract; it skips today):

```python
"""Corpus-versus-compiler contract test (plan 003).

Skipped until milestone 1 provides ``cea.pipeline.compile_source``. The full
interface contract is written in tests/corpus/README.md.
"""
import pytest

pipeline = pytest.importorskip("cea.pipeline")

import corpus_lib as cl  # noqa: E402

RECORD_ATTRS = ("id", "code", "line", "column", "severity", "phase", "root_id", "caused_by")


def _cases():
    cases = []
    for split, c_path in cl.c_files():
        marks = [pytest.mark.corpus]
        if split == "heldout":
            marks.append(pytest.mark.heldout)  # deselected by default (addopts); milestone 5 only
        cases.append(pytest.param(c_path, id=f"{split}/{c_path.name}", marks=marks))
    return cases


@pytest.mark.parametrize("c_path", _cases())
def test_expected_diagnostics_are_reported(c_path):
    side = cl.load_sidecar(c_path)
    result = pipeline.compile_source(c_path.read_text(encoding="utf-8"), c_path.name)
    for rec in result.errors:
        for attr in RECORD_ATTRS:
            assert hasattr(rec, attr), f"error record lacks attribute {attr!r}: {rec!r}"
    got = {(rec.code, rec.line) for rec in result.errors}
    # Deliberately a SUBSET check: every expected root and warning must be
    # reported with the same (code, line). Exact equality between the expected
    # roots and the records the compiler marks as roots (root_id == id) is
    # deferred to the F2 clustering milestone, which will tighten this test.
    missing = [e for e in side["roots"] + side["warnings"] if (e["code"], e["line"]) not in got]
    assert not missing, f"not reported as (code, line): {missing}; got {sorted(got)}"
    if side["split"] == "valid":
        fatal = [(r.code, r.line) for r in result.errors if r.severity == "fatal"]
        assert not fatal, f"valid program produced fatal errors: {fatal}"
```

`tests/test_gcc_crosscheck.py`:

```python
"""Runs tools/gcc_check.py: the corpus against gcc -std=c99 -pedantic-errors (plan 003)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.gcc
@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not on PATH")
def test_gcc_agrees_with_sidecars():
    proc = subprocess.run(
        [sys.executable, "-I", str(ROOT / "tools" / "gcc_check.py")],
        capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
```

`tools/gcc_check.py` (stdlib only):

```python
"""Cross-check tests/corpus against gcc (plan 003). Stdlib only.

For every tests/corpus/<split>/*.c this runs
    gcc -std=c99 -pedantic-errors -fsyntax-only <file>
and checks two things:
  1. The design rule "accepted => valid C99": a program whose sidecar has
     empty "roots" (all of valid/, plus warning-only faulty programs) MUST be
     accepted by gcc (exit code 0).
  2. The sidecar's "gcc_rejects" equals what gcc actually did.
It prints a summary and exits 1 on any mismatch, otherwise 0.
If gcc is not on PATH it prints a skip message and exits 0.

Usage: python -I tools/gcc_check.py [corpus_dir]     (default: tests/corpus)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLITS = ("dev", "heldout", "valid")
GCC_ARGS = ["-std=c99", "-pedantic-errors", "-fsyntax-only"]


def main(argv):
    gcc = shutil.which("gcc")
    if gcc is None:
        print("SKIP: gcc not found on PATH; corpus not cross-checked")
        return 0
    corpus = Path(argv[1]) if len(argv) > 1 else ROOT / "tests" / "corpus"
    problems, checked, rejected = [], 0, 0
    for split in SPLITS:
        for c_path in sorted((corpus / split).glob("*.c")):
            rel = f"{split}/{c_path.name}"
            side_path = c_path.with_name(c_path.stem + ".expected.json")
            if not side_path.exists():
                problems.append(f"{rel}: missing sidecar {side_path.name}")
                continue
            side = json.loads(side_path.read_text(encoding="utf-8"))
            proc = subprocess.run([gcc, *GCC_ARGS, str(c_path)],
                                  capture_output=True, text=True, timeout=60)
            gcc_rejects = proc.returncode != 0
            checked += 1
            rejected += gcc_rejects
            first = next((ln for ln in proc.stderr.splitlines() if "error" in ln), "")
            if not side.get("roots") and gcc_rejects:
                problems.append(f"{rel}: no expected roots but gcc REJECTS it "
                                f"(breaks 'accepted => valid C99'): {first}")
            if side.get("gcc_rejects") != gcc_rejects:
                verdict = "rejects" if gcc_rejects else "accepts"
                problems.append(f"{rel}: sidecar gcc_rejects={side.get('gcc_rejects')} "
                                f"but gcc {verdict} it {first}".rstrip())
    for p in problems:
        print("MISMATCH:", p)
    print(f"gcc_check: {checked} files checked, {rejected} rejected by gcc, "
          f"{checked - rejected} accepted, {len(problems)} mismatches")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

Create the folders `tests/corpus/dev`, `tests/corpus/heldout` and `tests/corpus/valid`. Add the two pattern programs and their sidecars **exactly** as given in "Pattern 1" and "Pattern 2" above. Each `.c` file ends with one newline after the final `}`.

Write `tests/corpus/README.md` with these sections. Copy the content from this plan, rewording is fine.
1. **Purpose**: the corpus is the pytest suite and the PRD's evaluation set ("20 faulty programs" = `heldout/`).
2. **Layout and naming**: the folders, the `dev` number ranges and the sidecar naming.
3. **Sidecar schema**: the field table above, verbatim.
4. **Location convention**: all bullets and all four worked examples.
5. **Held-out rule**, verbatim:
   > **RULE:** files in `heldout/` must never be read or used when designing or tuning parser recovery, clustering (F2) heuristics, prompts or fix strategies. They are used only for the milestone-5 evaluation (`pytest -m heldout` and the metrics). If a heldout program reveals a bug, fix the bug using a new `dev/` program that reproduces it, never by looking at the heldout file again. `tools/gcc_check.py` and the schema test read heldout sidecars only to validate the corpus itself. That is allowed.
6. **Compiler interface contract (milestone 1 must implement this)**:
   - Module `cea.pipeline` (file `src/cea/pipeline.py`; `pyproject.toml` already puts `src/` on pytest's path).
   - `compile_source(source: str, filename: str) -> result`. It runs the lexical, syntax and semantic phases on the text and never raises on bad input.
   - `result.errors` is a list of records (dataclass or object) with these attributes:
     - `id: str`, unique within one result, e.g. `"E-0001"`;
     - `code: str`, a catalog code;
     - `line: int` and `column: int`, both 1-based, following the location convention above;
     - `severity: str`, `"fatal"` or `"warning"`, taken from the catalog;
     - `phase: str`, `"lexical"`, `"syntax"` or `"semantic"`;
     - `root_id: str`, the `id` of the root record of its cluster (a root's `root_id` equals its own `id`);
     - `caused_by: str | None`, the `id` of the record that directly caused it, or `None` if no cause is known (always `None` for roots).
   - Records also carry the PRD fields `found`, `expected`, `snippet` and `rule_ref`, plus plan 002's additions `language`, `span_end` and `message`. This test does not check them.
   - Today the test checks only that every expected root and warning appears as a record with the same `(code, line)`, and that `valid/` programs have no fatal records. Exact equality between expected roots and reported roots is deferred to the F2 milestone.
7. **How to run**: the four commands (`pytest`, `pytest -m heldout`, `pytest -m gcc`, `python -I tools/gcc_check.py`) and the venv setup.
8. **Authoring rules**: the 8 quality rules above.

**Verify**:
- `.venv/Scripts/python -m pytest -q -k "not test_dev_ and not test_heldout_ and not test_valid_"` → `8 passed, 1 skipped, 4 deselected`. Here N = 2, so 2 + 6 = 8. The skip is `test_corpus_compile.py`.
- `python -I tools/gcc_check.py` → `gcc_check: 2 files checked, 2 rejected by gcc, 0 accepted, 0 mismatches`, exit 0.
- `.venv/Scripts/python -m pytest -q -rs tests/test_corpus_compile.py` → `1 skipped`, and the skip reason mentions `cea.pipeline`.

Commit: `test: add corpus harness, gcc cross-check and corpus README (plan 003 step 2)`.

### Step 3: `dev` lexical and syntax single-fault programs (001–015)

Write one program per row. Follow the quality rules, and keep the faulty construct on one line. The ideas are suggestions; any realistic fault that yields exactly this root works.

| File | Root code | Suggested fault (realistic) |
|---|---|---|
| `001-stray-at-sign.c` | LEX-INVALID-CHAR | a stray `@` typed after a complete statement, e.g. `count++;@`, so nothing else breaks |
| `002-unclosed-printf-string.c` | LEX-UNTERMINATED-STRING | `printf("Total: %d\n, total);` (closing `"` forgotten). Line of the opening `"`. |
| `003-two-char-literal.c` | LEX-BAD-CHAR-LITERAL | `char grade = 'AB';` |
| `004-unclosed-todo-comment.c` | LEX-UNTERMINATED-COMMENT | `/* TODO: ...` after the last `}` of the file, never closed |
| `005-number-with-letters.c` | LEX-MALFORMED-NUMBER | `int limit = 10x;` |
| `006-windows-path-escape.c` | LEX-INVALID-ESCAPE | `printf("Saved to C:\data\n");` (`\d`) |
| `007-unsupported-include.c` | LEX-UNSUPPORTED-DIRECTIVE | `#include <math.h>` on line 2, not otherwise used |
| `008-missing-semicolon-assign.c` | SYN-MISSING-SEMICOLON | `sum = sum + i` followed by a line starting with an identifier |
| `009-if-missing-close-paren.c` | SYN-UNBALANCED-BRACKET | `if (score > 50 {` |
| `010-while-missing-open-paren.c` | SYN-EXPECTED-TOKEN | `while count < 10) {` |
| `011-empty-right-hand-side.c` | SYN-EXPECTED-EXPRESSION | `average = sum / ;` |
| `012-param-without-type.c` | SYN-EXPECTED-TYPE | `int max(a, int b)` |
| `013-missing-final-brace.c` | SYN-UNEXPECTED-EOF | last `}` of `main` (the last function) missing. Root line = file line count. |
| `014-reversed-assignment.c` | SYN-INVALID-ASSIGN-TARGET | `0 = count;` |
| `015-const-qualifier.c` | SYN-UNSUPPORTED-FEATURE | `const int LIMIT = 5;` (line of `const`) |

For each file, run `gcc -std=c99 -pedantic-errors -fsyntax-only <file>; echo "exit=$?"` and record `gcc_rejects`. Write the sidecar: `cascading` is `false` unless the fault clearly produces several symptoms (e.g. 002); `fixable` is `true`; `warnings` is `[]`.

**Verify**:
- partial-corpus suite → `23 passed, 1 skipped, 4 deselected` (N = 17).
- `COVERAGE` → `MISSING:` lists no `LEX-` or `SYN-` codes, only `SEM-` and `WRN-` codes (but not `SEM-ARG-COUNT`).
- `python -I tools/gcc_check.py` → `0 mismatches`, exit 0.

Commit: `test: add lexical and syntax dev programs (plan 003 step 3)`.

### Step 4: `dev` semantic and warning single-fault programs (016–037)

| File | Code | Suggested fault |
|---|---|---|
| `016-typo-in-variable.c` | SEM-UNDECLARED-VAR | `totl = totl + x;` where only `total` exists. Use the typo **once** (the first use is the root). |
| `017-call-before-definition.c` | SEM-UNDECLARED-FUNC | `main` calls `square(i)` and `square` is defined after `main` with no prototype |
| `018-redeclared-loop-var.c` | SEM-REDECLARED | `int i;` declared twice in the same block (root at the 2nd) |
| `019-prototype-disagrees.c` | SEM-CONFLICTING-TYPES | `int area(int w, int h);` then `float area(int w, int h) {` (root at the definition) |
| `020-string-into-int.c` | SEM-TYPE-MISMATCH | `int count = "five";` |
| `021-void-result-used.c` | SEM-VOID-VALUE | `int r = print_header();` where `void print_header(void)` |
| `022-variable-called-like-function.c` | SEM-NOT-CALLABLE | `int max = 0;` … `max(a, b);` |
| `023-arg-count-too-few.c` | SEM-ARG-COUNT | already written in Step 2 |
| `024-string-argument.c` | SEM-ARG-TYPE | `print_score("Alice", 90);` for `void print_score(int id, int score)` |
| `025-value-from-void-function.c` | SEM-RETURN-TYPE | `return 0;` inside a `void` function |
| `026-index-plain-int.c` | SEM-NOT-ARRAY | `int total = 0;` … `total[0] = 5;` |
| `027-double-index.c` | SEM-INDEX-NOT-INT | `marks[avg]` where `double avg` |
| `028-variable-array-size.c` | SEM-BAD-ARRAY-SIZE | `int n = 5; int marks[n];` (gcc accepts: VLA) |
| `029-break-in-if.c` | SEM-BREAK-OUTSIDE-LOOP | `break;` inside an `if` in `main`, not in a loop |
| `030-global-from-global.c` | SEM-NONCONST-GLOBAL-INIT | `int limit = 10;` then `int half = limit / 2;` at file scope |
| `031-printf-int-first.c` | SEM-PRINTF-FORMAT | `printf(total);` |
| `032-main-misspelled.c` | SEM-MISSING-MAIN | `int mian(void) { ... }` is the only function. Root line = file line count. gcc accepts. |
| `033-unused-temp.c` | WRN-UNUSED-VAR | `int temp = 0;` never read. `roots: []`. |
| `034-printf-after-return.c` | WRN-UNREACHABLE-CODE | `printf` directly after `return` in a helper function |
| `035-average-into-int.c` | WRN-IMPLICIT-NARROWING | `int avg = total / 2.0;` |
| `036-sign-no-final-return.c` | WRN-MISSING-RETURN | `int sign(int n) { if (n > 0) { return 1; } else if (n < 0) { return -1; } }` (line of `sign`) |
| `037-assign-in-if.c` | WRN-ASSIGN-IN-CONDITION | `if (choice = 1) {` |

For 033–037, `roots` is `[]` and gcc **must** accept the file. If it does not, the program contains an accidental fault: fix it. For 016–032, `warnings` is `[]`, so make sure no warning trigger is present. Record `gcc_rejects` by running gcc for every file.

**Verify**:
- partial-corpus suite → `44 passed, 1 skipped, 4 deselected` (N = 38).
- `.venv/Scripts/python -m pytest -q -k test_dev_covers_every_catalog_code` → `1 passed`.
- `COVERAGE` → `MISSING: []`.
- `python -I tools/gcc_check.py` → `0 mismatches`, exit 0.

Commit: `test: add semantic and warning dev programs (plan 003 step 4)`.

### Step 5: `dev` cascading (040–050) and multi-fault (060–063) programs

Cascading: one injected fault, `cascading: true`, and exactly one root. Write at least these 11 (040 already exists):

| File | Root (code, where) | Fault |
|---|---|---|
| `040-missing-semicolon-decl-cascade.c` | SYN-MISSING-SEMICOLON, the declaration's line | already written |
| `041-missing-brace-before-next-function.c` | SYN-UNBALANCED-BRACKET, the next function's type keyword | worked example 2 |
| `042-missing-loop-brace-at-eof.c` | SYN-UNEXPECTED-EOF, the last line | the `}` closing a `while` in the last function is missing |
| `043-loop-counter-never-declared.c` | SEM-UNDECLARED-VAR, the first use | forgot `int i;`; `i` is used 5+ times in two loops |
| `044-empty-initializer-then-uses.c` | SYN-EXPECTED-EXPRESSION, the declaration | `double average = ;` then `average` is used 4+ times |
| `045-while-missing-paren-cascade.c` | SYN-EXPECTED-TOKEN, the found token | `while count < 10) {` with a 5-line body |
| `046-unclosed-string-mid-function.c` | LEX-UNTERMINATED-STRING, the opening `"` | the unterminated `printf` string sits mid-function with statements after it |
| `047-helper-called-before-defined.c` | SEM-UNDECLARED-FUNC, the first call | `cube()` is called 4 times in `main`, defined after it, with no prototype |
| `048-global-missing-semicolon.c` | SYN-MISSING-SEMICOLON, the global's line | `int limit = 10` directly before `int main(void) {` |
| `049-pointer-declaration-uses.c` | SYN-UNSUPPORTED-FEATURE, the `*` | `int *values;` then `values` is used 5 times |
| `050-for-missing-close-paren.c` | SYN-UNBALANCED-BRACKET, the `{` | `for (i = 0; i < 5; i++ {` |

Multi-fault: 2–3 **independent** faults in different functions or regions, `injected_faults` with 2 or 3 entries, and one root per fatal fault:

| File | Faults |
|---|---|
| `060-one-per-phase.c` | the PRD F1 acceptance file: one LEX-INVALID-CHAR, one SYN-MISSING-SEMICOLON and one SEM-UNDECLARED-VAR, each in a different function (3 roots, `warnings: []` because there is a SYN root) |
| `061-two-semantic-faults.c` | SEM-ARG-COUNT in `main` and SEM-RETURN-TYPE in a helper (2 roots) |
| `062-syntax-and-semantic.c` | SYN-EXPECTED-EXPRESSION in one function and SEM-NOT-ARRAY in another (2 roots) |
| `063-fault-plus-warning.c` | SEM-TYPE-MISMATCH (root) and WRN-IMPLICIT-NARROWING (warning) in separate functions |

In `notes`, describe the symptoms you expect for each cascade. Record `gcc_rejects` by running gcc.

**Verify**:
- partial-corpus suite → `<N+6> passed, 1 skipped, 4 deselected`, where N = `ls tests/corpus/*/*.c | wc -l` (52 if you wrote exactly the listed files, so `58 passed`).
- `.venv/Scripts/python -m pytest -q -k "test_dev_"` → `2 passed`.
- `python -I tools/gcc_check.py` → `0 mismatches`.

Commit: `test: add cascading and multi-fault dev programs (plan 003 step 5)`.

### Step 6: `valid` programs (001–012)

Write 12 valid C99 programs, 15–45 lines each, using only supported features. All have `roots: []`, `injected_faults: []`, `cascading: false`, `fixable: false` and `gcc_rejects: false`. Suggested themes:
- `001-sum-of-marks`
- `002-factorial-recursive` (prototype + definition)
- `003-fibonacci-array`
- `004-max-in-array`
- `005-grade-classifier` (`if/else` chain ending in `else`)
- `006-prime-check-while-continue`
- `007-temperature-table-double`
- `008-char-arithmetic`
- `009-times-table-nested-for` (using `for (int i = 0; ...)`)
- `010-global-counter` (a global with a literal initialiser, `+=`, `%=`)
- `011-narrowing-warning`: one intentional `int whole = 7.9;` → `warnings: [{"code": "WRN-IMPLICIT-NARROWING", "line": <that line>}]`
- `012-unused-local-warning`: one local declared and never read → `warnings: [{"code": "WRN-UNUSED-VAR", "line": <that line>}]`

At least 2 valid programs must have non-empty `warnings` (011 and 012). Everything else must trigger **no** warning (re-check the semantic traps listed under "Current state").

**Verify**:
- `.venv/Scripts/python -m pytest -q -k test_valid_size` → `1 passed`.
- partial-corpus suite → `<N+6> passed, 1 skipped, 4 deselected`.
- `python -I tools/gcc_check.py` → `0 mismatches`. If any valid program is rejected, fix it within the subset; see STOP conditions.

Commit: `test: add valid C99 programs (plan 003 step 6)`.

### Step 7: `heldout` programs (exactly 20: 001–020)

These are the PRD's "20 faulty programs" for the final metrics. Write them as a student would: realistic, 15–40 lines, with faults students actually make. **Do not copy or lightly edit `dev/` programs.** Use different program themes and different fault instances. The constraints, enforced by `test_heldout_size_and_coverage` and the per-file schema test:
- exactly 20 programs, each 15–40 lines;
- at least **8** have `cascading: true`;
- the catalog categories of all their roots and warnings cover at least **8 of the 10** categories. Aim for all 10.

Recommended mix:
- at least 6 programs with a syntax root;
- at least 2 with a lexical root;
- at least 7 with a semantic root;
- at least 1 warning-only program, which gcc must accept;
- at least 2 multi-fault programs (2–3 faults);
- at least 2 cascades caused by a missing `}` or a missing `;`, which are the F2 headline cases.

Suggested themes (one per file): bank balance loop, bubble-sort pass, GPA calculator, digit sum, leap-year check, triangle classifier, word-length histogram with arrays, power function, min/max/average of 5 readings, countdown timer, multiplication quiz scorer, Celsius table, palindrome number, array reverse, series sum, simple interest, number guessing check, even/odd counter, factorial table, attendance percentage.

Record `gcc_rejects` by running gcc on each file.

**Verify**:
- `.venv/Scripts/python -m pytest -q` → `<N+10> passed, 1 skipped`, no failures (N = total `.c` files; 84 if you wrote exactly the listed files, so `94 passed, 1 skipped`).
- `.venv/Scripts/python -m pytest -q -m heldout` → `1 skipped, <N+10> deselected`.
- `python -I tools/gcc_check.py` → `0 mismatches`, exit 0.

Commit: `test: add 20 held-out evaluation programs (plan 003 step 7)`.

### Step 8: Final checks (no commit unless a fix was needed)

Run the full "Done criteria" list below. Then run the mutation checks in "Test plan" and revert each mutation with `git checkout -- <file>`.

**Verify**: every Done criterion holds; `git status --short` prints nothing.

## Test plan

The deliverable *is* tests. Prove the checks actually catch mistakes by applying each mutation, confirming the failure, then reverting with `git checkout -- <file>`:
1. In `tests/corpus/dev/023-arg-count-too-few.expected.json`, change `"line": 11` to `"line": 99`. Then `.venv/Scripts/python -m pytest -q -k sidecar_schema` → 1 failed, with `roots: line 99 outside 1..15 for SEM-ARG-COUNT`. Revert.
2. In the same sidecar, change `"gcc_rejects": true` to `false`. Then `python -I tools/gcc_check.py` → a line `MISMATCH: dev/023-arg-count-too-few.c: sidecar gcc_rejects=False but gcc rejects it ...`, exit 1. Revert.
3. In `tests/corpus/valid/001-*.c`, delete one `;`. Then `python -I tools/gcc_check.py` → `MISMATCH: valid/001-...: no expected roots but gcc REJECTS it (breaks 'accepted => valid C99')`, exit 1. Revert.
4. Rename `tests/corpus/dev/023-arg-count-too-few.c` to `023-arg-count-too-few.c.bak`. Then `.venv/Scripts/python -m pytest -q -k sidecar_has_c_file` → 1 failed (orphan sidecar). Rename it back.
5. In `tests/corpus/dev/033-*.expected.json`, put `{"code": "WRN-UNUSED-VAR", "line": <n>}` into `roots` instead of `warnings`. The schema test should fail with `has severity warning, expected fatal`. Revert.

The structural pattern for future corpus-driven tests is `tests/test_corpus_compile.py` (parametrize over `corpus_lib.c_files()` and mark heldout cases with `pytest.mark.heldout`).

## Done criteria

All must hold:

- [ ] `.venv/Scripts/python -m pytest -q` exits 0, prints `<N+10> passed, 1 skipped` (N = `ls tests/corpus/*/*.c | wc -l`), and shows no failures or errors
- [ ] `.venv/Scripts/python -m pytest -q -rs` shows the single skip is `tests/test_corpus_compile.py` (reason mentions `cea.pipeline`)
- [ ] `python -I tools/gcc_check.py` exits 0 and ends with `0 mismatches`
- [ ] `ls tests/corpus/heldout/*.c | wc -l` → `20`; `ls tests/corpus/valid/*.c | wc -l` → ≥ 10; `ls tests/corpus/dev/*.c | wc -l` → ≥ 52
- [ ] `COVERAGE` command → `MISSING: []`
- [ ] `git diff --stat main...HEAD -- src docs README.md VIVA.md plans "cd project prd.docx" tools/check_spec.py .gitignore` prints nothing
- [ ] `git ls-files .venv | wc -l` → `0`
- [ ] `git log --oneline main..HEAD` shows 7 commits, `(plan 003 step 1)` through `(plan 003 step 7)`, each with the `Co-Authored-By` trailer (`git log main..HEAD --format=%b | grep -c "Co-Authored-By: Claude Opus 5.5"` → `7`)
- [ ] All 5 mutation checks failed as expected and were reverted
- [ ] `git status --short` prints nothing

## STOP conditions

Stop and report back (do not improvise) if:

- The drift check prints anything, `docs/error-catalog.md` is missing, or it does not have exactly 37 code rows.
- `docs/error-catalog.md` defines codes that differ from the table in "Current state" (renamed, added or removed codes).
- **A catalog code cannot be triggered alone.** Every program you try that triggers it also needs a second, independent fault, or the location convention gives no single unambiguous line. Report the code and what you tried; do not edit the catalog or invent a convention.
- **A `valid` program (or a warning-only faulty program) is rejected by gcc and cannot be fixed without leaving the subset.** Report the program and gcc's message. This would be a hole in the "accepted ⇒ valid C99" design rule.
- gcc is not on PATH. `gcc_check.py` would just print SKIP, but this plan requires real `gcc_rejects` values, so you cannot record them honestly.
- `pip install` fails, e.g. because there is no network.
- A step's verification fails twice after a reasonable fix attempt.
- Any change seems to require touching `src/`, `docs/`, `plans/`, `README.md`, `VIVA.md` or `tools/check_spec.py`.

## Maintenance notes

- **Milestone 1 (F1/F4)** must create `src/cea/pipeline.py` with `compile_source(source, filename)` per the contract in `tests/corpus/README.md`. Its done criteria should include "`tests/test_corpus_compile.py` is **no longer skipped**". Otherwise a typo in the module path would leave the contract test silently skipped forever.
- **F2 milestone**: tighten `test_corpus_compile.py` to exact root-set equality: `{(r.code, r.line) for r in result.errors if r.root_id == r.id and r.severity == "fatal"}` must equal the sidecar's `roots`. Also add the clustering-reduction metric over `cascading: true` programs.
- **F8 milestone**: `fixable: true` programs are the denominator for "≥ 80% of fixable errors verified within 3 attempts".
- **Milestone 5**: compute every metric on `heldout/` only (`pytest -m heldout` plus an eval script). Never tune on heldout (README rule).
- **Plan 002 (lexer/parser)** must implement the location convention in this plan, in particular: SYN-MISSING-SEMICOLON at the end of the unterminated statement; a missing `}` reported at `type_spec IDENT (` inside a block (plan 002 §4.7); EOF just after the last token, which is the last line under this plan's authoring rule.
- If the catalog gains or loses codes, update `test_catalog_has_37_codes` and add `dev` programs for the new codes. The coverage test will flag them.
- Reviewers should scrutinise: (a) that single-fault `dev` programs contain no accidental warning triggers; (b) that each sidecar `line` follows the convention, especially SYN-MISSING-SEMICOLON and missing `}`; (c) that heldout programs are not near-copies of dev programs.
- Deferred: column checks (only `line` is recorded), raw error counts (they depend on recovery), and `printf` format checking (not in the subset's rules).
