# Plan 004: Close the four recovery-spec gaps found by the test corpus

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md`, unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3af5d50..HEAD -- docs/error-recovery.md docs/language-spec.md docs/decisions/0002-error-recovery-and-cascade-linking.md tests/corpus/dev/049-pointer-declaration-uses.expected.json tests/corpus/dev/051-for-header-missing-semicolon.expected.json tests/corpus/heldout/020-menu-switch.expected.json`
> It must print nothing. If any of those files changed since this plan was
> written, compare the "Current state" excerpts against the live files. On a
> mismatch, STOP.

## Status

- **Priority**: P1 (blocks plans 006 and 007)
- **Effort**: S–M
- **Risk**: LOW (docs and test sidecars only; no compiler code exists yet)
- **Depends on**: plans 001, 002, 003 (all merged into `main`)
- **Category**: docs / tests
- **Planned at**: commit `3af5d50`, 2026-10-10

## Why this matters

The project is a course compiler for a C99 subset, written in Python. It records every error and links cascading errors to their cause through a `caused_by` field, so the UI can show one root cause per mistake (PRD feature F2).

The recovery rules are in `docs/error-recovery.md`. When the test corpus (`tests/corpus/`) was hand-traced against those rules, four gaps appeared:
- Two make one student mistake show up as **several unrelated root causes**: an unsupported pointer declaration, and an unsupported `switch`.
- Two are **unstated rules** the compiler writers would otherwise guess at.

Milestone 1 (plans 005–007) implements the spec literally, so the spec must be fixed first. This plan changes documentation and test expectations only.

## Current state

- `docs/error-recovery.md` (440 lines, from plan 002) is the recovery spec. The relevant parts:
  - §4.1 says the `expected` field uses "the token or token class that the failing `expect(...)` call required at that point". It does not say what happens at an **optional** construct (e.g. a call's argument list).
  - §5 `ErrorStmt` fields: `kind_hint: str  # 'if' 'while' 'for' 'return' 'break' 'continue' 'decl' 'expr' 'top'` and `declared_names: list[tuple[str, str]]  # (name, type) for each "type_spec IDENT" consumed inside it`.
  - §6, last bullet: "For `sem.unused_declaration`, a plain `=` assignment target is a write, not a read, so a variable that is only assigned is still unused". It says nothing about `+=`, `-=`, `*=`, `/=`, `%=`, `++` and `--`.
  - §7 has a table with exactly 8 rows, `| R1 ` … `| R8 `. R7 reads: `| R7 orphan loop body | SEM-BREAK-OUTSIDE-LOOP | the break/continue is inside (at any depth, with no real while or for node in between) a Block whose orphan_of points to an ErrorStmt with kind_hint while or for | orphan_of |`. The notes under it say "R1 and R2 are the only rules that apply to syntax records" and "Precedence: for syntax records, R2 then R1."
  - §9 has traces T1, T1b, T2–T7, a "Record table" (columns `| Trace | Id | Code | Line:Col | Found | caused_by | root_id |`) and a "Summary table" (`| Trace | Raw | Displayed | Fatal | Warning | Reference |`) with 8 rows.
- `docs/language-spec.md` line ~299: `### sem.unused_declaration` / "A local variable that is declared but never read produces a warning. Parameters and globals are exempt."
- `docs/decisions/0002-error-recovery-and-cascade-linking.md` is the ADR for recovery, with sections Status, Context, Decision, Consequences and Still open.
- The corpus (`tests/corpus/`, from plan 003): each `NNN-slug.c` has an `NNN-slug.expected.json` sidecar. Its `notes` field starts `Expected under plan 002: raw N.` followed by records `CODE line (caused_by: Rk | none)`. **Held-out rule** (from `tests/corpus/README.md`): files in `heldout/` must never be used to design or tune recovery. A bug a held-out file reveals is reproduced as a new `dev/` program. Updating a held-out sidecar's `notes` to match the spec is allowed (corpus validation).
- The gaps, with evidence:
  1. **Unsupported pointer declaration loses the name.** `dev/049-pointer-declaration-uses.c` line 6 is `    int *values;`. The parser consumes `int`, expects IDENT and finds `*`, giving SYN-UNSUPPORTED-FEATURE (catalog rule 0). The IDENT was never consumed, so the `ErrorStmt` has `declared_names = []`. Its 5 later uses of `values` are 5 unlinked SEM-UNDECLARED-VAR records, so F2 would show 2 roots for one mistake.
  2. **`switch` body cascades are unlinked.** In a `switch (x) { case 1: ... break; ... }`, the `switch` error's panic stops before `{`, making an orphan block. The first `case` is linked by R2. Its panic consumes a `;`, which closes the region, so later `case`/`default` errors and every `break` (R7 covers only while/for) are unlinked. This was observed in held-out program 020.
  3. **Compound assignment and `++`/`--` are unspecified for "unused".** The corpus already assumes they READ their target, so `sum += i` reads `sum`.
  4. **Optional constructs and the expected set are unspecified.** For example `printf(` followed by `return`. The corpus (`dev/002`, `dev/046`, `heldout/010`) already assumes SYN-EXPECTED-EXPRESSION.
  5. **A trivial note error:** the `dev/051` sidecar note says "'n' is read again on line 11". It is line 10.

## Commands you will need

| Purpose | Command (project root, Git Bash) | Expected on success |
|---|---|---|
| venv (once) | `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt` | exit 0 |
| All tests | `.venv/Scripts/python -m pytest -q` | `96 passed, 1 skipped` (95 + 1 new schema case for the new dev program), exit 0 |
| Spec checker | `python -I tools/check_spec.py` | `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules` |
| gcc cross-check | `python -I tools/gcc_check.py` | `gcc_check: 86 files checked, 59 rejected by gcc, 27 accepted, 0 mismatches` |

The pytest count adds 1 because the new `dev/052` program adds one parametrized schema case. If the baseline before your change is not `95 passed, 1 skipped`, STOP.

## Scope

**In scope** (modify or create only these):
- `docs/error-recovery.md`
- `docs/language-spec.md` (the `sem.unused_declaration` paragraph only)
- `docs/decisions/0002-error-recovery-and-cascade-linking.md`
- `tests/corpus/dev/049-pointer-declaration-uses.expected.json` (`notes` only)
- `tests/corpus/dev/051-for-header-missing-semicolon.expected.json` (`notes` only)
- `tests/corpus/heldout/020-menu-switch.expected.json` (`notes` only)
- `tests/corpus/dev/052-switch-grade-menu.c` and `tests/corpus/dev/052-switch-grade-menu.expected.json` (create)
- `plans/README.md` (status row only)

**Out of scope** (do NOT touch):
- `docs/error-catalog.md`, `tools/check_spec.py`. No new error codes; the checker must keep printing the same counts.
- Any `.c` file except the new `dev/052`. Any sidecar field except `notes`, and any sidecar not listed above.
- `heldout/020-menu-switch.c`. Do not edit it, and do not base `dev/052` on its text. Write a different program (see Step 5).
- Any `src/` code. None exists yet; milestone 1 builds it from these docs.

## Git workflow

- Branch: `advisor/004-recovery-spec-gaps`, created from `main`. If a reviewer runs you in an isolated worktree, commit on the worktree's branch instead.
- One commit per step that changes files. Stage by explicit path (never `git add -A`). Message: `docs: <what> (plan 004 step N)` or `test: <what> (plan 004 step N)`, then a blank line, then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use two `-m` flags.
- Do not push or merge.

## Steps

### Step 1: Baseline

Run the three commands in the table above **before** changing anything. Expect `95 passed, 1 skipped`, the `OK: 37 codes…` line, and `gcc_check: 85 files checked, 59 rejected by gcc, 26 accepted, 0 mismatches`.

**Verify**: all three outputs match. Otherwise STOP.

### Step 2: Gap 4 and gap 3 (clarifications in §4.1 and §6, plus the spec)

1. In `docs/error-recovery.md` §4.1, append this paragraph verbatim:
   > **Optional constructs.** Where the grammar has an optional part (`[ arg_list ]` in a call, `[ expression ]` in `return_stmt`, the optional parts of a `for` header, `params`), the parser decides with one token of lookahead. If the current token is the token that ends the construct (`)` for a call or parameter list, `;` for `return` and the `for` header parts), the optional part is absent. Otherwise the parser **commits** to the optional part, and a failure inside it is reported with that part's expected set. Example: in `printf(` followed by `return`, the token is not `)`, so the parser commits to `arg_list`, needs the start of an expression, and selection rule 4 gives SYN-EXPECTED-EXPRESSION at `return`.
2. In §6, replace the last bullet (the one beginning "For `sem.unused_declaration`, a plain `=` assignment target is a write") with:
   > For `sem.unused_declaration`, a plain `=` assignment target is a write, not a read, so a variable that is only assigned with `=` is still unused (this is what happens to `x` in trace T3 and `b` in T1b). The compound assignments `+=`, `-=`, `*=`, `/=`, `%=` and the operators `++` and `--` (prefix or postfix) **read and write** their target, so they count as reads. An array element target `a[i] = …` reads `i` and writes `a`. Reads inside an `ErrorStmt` or an `ErrorExpr` are never seen by the analyser, which is what rules R4 and R6 compensate for.
3. In `docs/language-spec.md`, change the `sem.unused_declaration` paragraph text (keep the heading line `### sem.unused_declaration` and the C example unchanged) to:
   > A local variable that is declared but never read produces a warning. Assigning with `=` is not a read. Compound assignment (`+=` and the like) and `++`/`--` both read and write. Parameters and globals are exempt.

**Verify**:
- `grep -c '^> \*\*Optional constructs\.\*\*\|^\*\*Optional constructs\.\*\*' docs/error-recovery.md` → `1`. You may write the paragraph as a blockquote or as plain text; either form matches.
- `grep -c 'read and write' docs/error-recovery.md` → at least `1`
- `grep -c 'both read and write' docs/language-spec.md` → `1`
- `python -I tools/check_spec.py` → the same `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`
- Commit: `docs: specify optional-construct lookahead and compound-assignment reads (plan 004 step 2)`

### Step 3: Gap 1, names in unsupported declarations (§5)

1. In §5's `ErrorStmt` sketch, change the `kind_hint` comment to: `# 'if' 'while' 'for' 'return' 'break' 'continue' 'decl' 'expr' 'top' 'unsupported'`.
2. Under "Rules:" in §5, add these two bullets verbatim:
   > - **`kind_hint = 'unsupported'`** is used when the statement (or top-level declaration) **starts** with an UNSUPPORTED_KEYWORD (`switch`, `do`, `struct`, `const`, …). The error is SYN-UNSUPPORTED-FEATURE at that keyword, and statement-level (or top-level) panic follows as usual.
   > - **Declarator-like names in unsupported code.** When an `ErrorStmt`'s error is SYN-UNSUPPORTED-FEATURE, `declared_names` additionally contains every IDENT in its span that (a) is immediately preceded by a type keyword, by `*`, or by another IDENT, and (b) is immediately followed by `=`, `;`, `,` or `[`. Each such name gets type `"<unsupported>"`, in source order without duplicates. Example: `int *values;` gives `declared_names = [("values", "<unsupported>")]`, so R5 links later uses of `values` to the SYN-UNSUPPORTED-FEATURE record. This is mechanical (a token pattern), so it meets invariant 3. It deliberately applies only to unsupported-feature errors, where the student clearly meant to declare something.

**Verify**:
- `grep -c "'unsupported'" docs/error-recovery.md` → at least `2`
- `grep -c '<unsupported>' docs/error-recovery.md` → at least `2`
- Commit: `docs: keep declarator names in unsupported declarations (plan 004 step 3)`

### Step 4: Gap 2, `switch`-like bodies (§7: new R9, extended R7)

1. In the §7 table, replace the R7 row with:
   `| R7 orphan loop body | SEM-BREAK-OUTSIDE-LOOP | the break/continue is inside (at any depth, with no real while or for node in between) a Block whose orphan_of points to an ErrorStmt with kind_hint while, for or unsupported | orphan_of |`
2. Add a ninth row after R8:
   `| R9 orphan unsupported body | any syntax record | R2 and R1 do not apply, and the innermost Block being parsed has orphan_of = X, where X is an ErrorStmt with kind_hint unsupported | X's error_id |`
3. In the notes under the table, change the precedence sentence to: "Precedence: for syntax records, R2, then R1, then R9." Change "R1 and R2 are the only rules that apply to syntax records. R3 to R8 apply to semantic records only." to "R1, R2 and R9 apply to syntax records. R3 to R8 apply to semantic records only."
4. Add one sentence after the table explaining R9: an unsupported construct such as `switch` makes its whole `{ … }` body unparseable as intended, so every syntax error inside that orphan body (each `case`/`default`) is a consequence of the unsupported construct. The parser knows this mechanically through `orphan_of`. R9 may over-link a genuinely independent error inside such a body. That is accepted, because the body must be rewritten anyway.
5. Wherever the doc says the table has "exactly 8 rows" or "R1–R8" as the complete set, update it to 9 / R1–R9. Use `grep -n 'R1.R8\|R1 to R8\|8 rows' docs/error-recovery.md` to find them. §11's "records `caused_by` for R1/R2" becomes "R1/R2/R9".

**Verify**:
- `grep -cE '^\| R[1-9] ' docs/error-recovery.md` → `9`
- `grep -c 'kind_hint while, for or unsupported' docs/error-recovery.md` → `1`
- `grep -c 'R2, then R1, then R9' docs/error-recovery.md` → `1`
- Commit: `docs: link switch-body cascades with R9 and extended R7 (plan 004 step 4)`

### Step 5: New traces T8 and T9 in §9

Add two traces after T7, in the same format as the others: a `c` code block, a numbered narrative naming the rule for each record, and rows in the Record and Summary tables. These are the advisor's **reference answers**. Reproduce them exactly, or STOP if a rule in the amended doc contradicts them.

**T8, unsupported `switch` with cases** (4 spaces per indent level; line 6 has 12 leading spaces):
```c
int main(void) {
    int n = 2;
    switch (n) {
        case 1:
            n = 5;
            break;
        default:
            n = 0;
    }
    return n;
}
```
Reference narrative:
1. The lexer records nothing.
2. Line 3: `statement()` sees `switch`, an UNSUPPORTED_KEYWORD. This gives E-0001 SYN-UNSUPPORTED-FEATURE at 3:5 (selection rule 0, `rule_ref = statement`). No region is open and there is no `lex_gap`, so `caused_by` is null. Statement-level panic opens the region (owner E-0001), skips `switch ( n )` and stops before `{`. The result is `ErrorStmt` with kind_hint `unsupported`, `stopped_before = "{"` and `declared_names = []`, because no IDENT is followed by `= ; , [`.
3. The `{` at 3:16 starts a block with `orphan_of = E-0001`.
4. Line 4: `case` gives E-0002 SYN-UNSUPPORTED-FEATURE at 4:9, linked to E-0001 by R2 (the region is open). Panic skips `case 1 :` and `n = 5`, then consumes `;`, which closes the region.
5. Line 6 `break;` parses as a `Break`.
6. Line 7: `default` gives E-0003 SYN-UNSUPPORTED-FEATURE at 7:9. R2 does not apply (the region is closed) and neither does R1. R9 applies (the innermost block is an orphan of the `unsupported` E-0001), so `caused_by = E-0001`. Panic skips `default : n = 0` and consumes `;`.
7. The `}` on line 9 ends the orphan block. Lines 10 and 11 parse normally.
8. Semantics: the `break` at 6:13 is inside the orphan block of an `unsupported` ErrorStmt with no real loop in between. This gives E-0004 SEM-BREAK-OUTSIDE-LOOP at 6:13, linked to E-0001 by R7. `n` is read in `return n`, so there is no warning.

| Trace | Id | Code | Line:Col | Found | caused_by | root_id |
|---|---|---|---|---|---|---|
| T8 | E-0001 | SYN-UNSUPPORTED-FEATURE | 3:5 | switch | — | E-0001 |
| T8 | E-0002 | SYN-UNSUPPORTED-FEATURE | 4:9 | case | E-0001 | E-0001 |
| T8 | E-0003 | SYN-UNSUPPORTED-FEATURE | 7:9 | default | E-0001 | E-0001 |
| T8 | E-0004 | SEM-BREAK-OUTSIDE-LOOP | 6:13 | break | E-0001 | E-0001 |

Summary row: `| T8 | 4 | 1 | 4 | 0 | n/a |`

**T9, unsupported pointer declaration:**
```c
int main(void) {
    int *p;
    p = 0;
    return p;
}
```
Reference narrative:
1. The lexer records nothing.
2. Line 2: `var_decl` consumes `int`, then expects IDENT and finds `*` at 2:9 directly after a `type_spec`. This gives E-0001 SYN-UNSUPPORTED-FEATURE at 2:9 (rule 0, `found = *`), with null `caused_by`.
3. The IDENT was not consumed, so the result is an `ErrorStmt` with kind_hint `decl`. Panic skips `* p` and consumes `;` (the region opens and closes).
4. Because the error is SYN-UNSUPPORTED-FEATURE, §5's new rule applies: `p` is preceded by `*` and followed by `;`, so `declared_names = [("p", "<unsupported>")]`.
5. Semantics: `p` at 3:5 is undeclared, giving E-0002 SEM-UNDECLARED-VAR, linked to E-0001 by R5. `p` at 4:12 gives E-0003 SEM-UNDECLARED-VAR, also R5. Both have type `<error>`, so `return p` raises no type error.

| Trace | Id | Code | Line:Col | Found | caused_by | root_id |
|---|---|---|---|---|---|---|
| T9 | E-0001 | SYN-UNSUPPORTED-FEATURE | 2:9 | * | — | E-0001 |
| T9 | E-0002 | SEM-UNDECLARED-VAR | 3:5 | p | E-0001 | E-0001 |
| T9 | E-0003 | SEM-UNDECLARED-VAR | 4:12 | p | E-0001 | E-0001 |

Summary row: `| T9 | 3 | 1 | 3 | 0 | n/a |`

Also update the sentence under the Summary table that says "Across the five traces whose raw count is at least 2 (T1b, T2, T3, T4, T5), raw is 13 and displayed is 5, a reduction of 62%". Recompute it over all traces whose raw count is ≥ 2 and that are single-fault: T1b, T2, T3, T4, T5, T8 and T9. Raw = 2+2+2+5+2+4+3 = 20, displayed = 7, reduction = 65%. Write those numbers.

**Verify**:
- `grep -cE '^\| T[0-9]+b? \| [0-9]+ \|' docs/error-recovery.md` → `10`
- `grep -c '^| T8 | E-0003 | SYN-UNSUPPORTED-FEATURE | 7:9 | default | E-0001 | E-0001 |$' docs/error-recovery.md` → `1`
- `grep -c '^| T8 | E-0004 | SEM-BREAK-OUTSIDE-LOOP | 6:13 | break | E-0001 | E-0001 |$' docs/error-recovery.md` → `1`
- `grep -c '^| T9 | E-0003 | SEM-UNDECLARED-VAR | 4:12 | p | E-0001 | E-0001 |$' docs/error-recovery.md` → `1`
- `grep -c '^```c$' docs/error-recovery.md` → `10`
- Commit: `docs: add traces T8 (switch) and T9 (pointer) (plan 004 step 5)`

### Step 6: ADR note

In `docs/decisions/0002-error-recovery-and-cascade-linking.md`, under `## Decision`, append one bullet:

> - **Amended by plan 004 (2026-10-10), after the test corpus exposed gaps:**
>   - names in unsupported declarations are kept for linking (§5);
>   - new rule R9, and R7 extended to `unsupported` orphan bodies (§7);
>   - the lookahead rule for optional constructs (§4.1);
>   - compound assignment and `++`/`--` count as reads (§6);
>   - traces T8 and T9 added (§9).

Under `## Still open`, change item (4) so it also mentions that R9 may over-link an independent error inside an unsupported body.

**Verify**: `grep -c 'Amended by plan 004' docs/decisions/0002-error-recovery-and-cascade-linking.md` → `1`. `grep -c '^## ' docs/decisions/0002-error-recovery-and-cascade-linking.md` → `5`. Commit: `docs: record plan 004 amendments in ADR 0002 (plan 004 step 6)`.

### Step 7: Corpus, with a new dev program and updated notes

1. **Create `tests/corpus/dev/052-switch-grade-menu.c`.** It is a NEW realistic program (do not open `heldout/020`; its existence is the only thing you need to know). Requirements:
   - 15–25 lines, `#include <stdio.h>`.
   - It maps a numeric grade band to a message using `switch (band) { case 1: ... break; case 2: ... break; default: ... }`. There are exactly 2 `case` labels, 1 `default`, and 2 `break;`. Each `case`/`default` line is followed by one `printf(...)` line, and each `break;` is on its own line.
   - Every local is read (no accidental warnings). The last line is `}`. The file ends with exactly one `\n`.
   - The `switch` keyword is the only injected fault. Write the sidecar in the existing format (see `tests/corpus/dev/049-pointer-declaration-uses.expected.json` as the pattern):
     - `split`: "dev"; `roots`: `[{"code": "SYN-UNSUPPORTED-FEATURE", "line": <switch line>}]`; `warnings`: `[]`; `cascading`: true; `fixable`: false (rewriting a switch as if/else is more than 3 lines);
     - `gcc_rejects`: the result of running `gcc -std=c99 -pedantic-errors -fsyntax-only` on it (expected: false, because `switch` is valid C);
     - `notes`: `Expected under plan 004: raw N.` followed by every record, traced with the amended rules exactly like T8 (each `case`/`default` → SYN-UNSUPPORTED-FEATURE linked by R2 for the first and by R9 for the rest; each `break` → SEM-BREAK-OUTSIDE-LOOP linked by R7).
2. **`dev/049` sidecar `notes`:** rewrite it to `Expected under plan 004: raw 6.` with the 5 SEM-UNDECLARED-VAR records now `(caused_by: R5)`, and explain the §5 declarator-name rule in one sentence. Keep the existing gcc remark.
3. **`heldout/020` sidecar `notes`:** re-trace by the amended rules. Reading this one held-out file only to validate its sidecar is allowed. Do not change anything else in it. Write `Expected under plan 004: raw N.` with each record and its rule. Every record should now link to the `switch` record, giving displayed 1.
4. **`dev/051` sidecar `notes`:** change "read again on line 11" to "read again on line 10".

**Verify**:
- `.venv/Scripts/python -m pytest -q` → `96 passed, 1 skipped`
- `python -I tools/gcc_check.py` → `gcc_check: 86 files checked, 59 rejected by gcc, 27 accepted, 0 mismatches`
- `grep -c 'Expected under plan 004' tests/corpus/dev/049-pointer-declaration-uses.expected.json tests/corpus/dev/052-switch-grade-menu.expected.json tests/corpus/heldout/020-menu-switch.expected.json` → `1` for each
- `git diff --name-only main..HEAD -- tests/corpus | sort` → exactly the 5 corpus paths in Scope
- Commit: `test: add switch dev program and align sidecar notes with plan 004 (plan 004 step 7)`

## Test plan

There is no compiler yet, so the checks are the corpus schema test, the gcc cross-check, the spec checker and the grep-verified reference traces (T8 and T9 become exact-match tests in plan 007).

Mutation check: temporarily change the new `dev/052` sidecar's root line to a line that doesn't exist (e.g. 99). `pytest -q` must then fail with an "outside 1..N" message. Revert.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` → `96 passed, 1 skipped`
- [ ] `python -I tools/gcc_check.py` → 86 files, 0 mismatches
- [ ] `python -I tools/check_spec.py` → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`
- [ ] `grep -cE '^\| R[1-9] ' docs/error-recovery.md` → `9`; summary rows → `10`
- [ ] `git diff --name-only main..HEAD` lists only in-scope files
- [ ] The mutation check failed as expected and was reverted

## STOP conditions

- The baseline in Step 1 differs.
- Tracing T8 or T9 under the amended doc gives a different record table, and the cause is a contradiction between rules rather than a mistake in your trace.
- The new `dev/052` program cannot be written to trigger only `switch`-related records (for example an accidental warning you can't avoid).
- Re-tracing `heldout/020` under the amended rules still leaves more than one root. Report its full record list and do not adjust the rules.
- Any change appears to need a new error code or a catalog edit.

## Maintenance notes

- Plans 006 (parser) and 007 (semantic analyser) implement R9 and the extended R7. Plan 007's trace test asserts T8 and T9 exactly.
- R9's over-linking (an independent error inside an unsupported body gets linked) is a deliberate trade-off. Revisit it if F2 metrics show it hides real errors.
- The declarator-name heuristic in §5 is limited to unsupported-feature errors on purpose. Extending it to all `ErrorStmt`s would let ordinary syntax errors silently "declare" names.
- **Viva note for the advisor:** this plan follows the held-out discipline. A gap seen in `heldout/020` was reproduced as `dev/052`, and the fix was designed against the dev program and the new trace T8, not against the held-out file.
