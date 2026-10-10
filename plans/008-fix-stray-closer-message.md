# Plan 008: Give SYN-UNBALANCED-BRACKET a message that is right for both a missing closer and a stray closer

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md` (the "Milestone 2" table, row 008), unless a reviewer
> dispatched you and told you they maintain the index. End your final report
> with a **Viva notes** list: the decisions, trade-offs or deviations an
> examiner might ask about (see `plans/README.md`, "Viva notes convention").
> Do not edit `VIVA.md`; the advisor folds your notes into it.
>
> Every code block marked "exact content" or "replace with" is the text to
> write. Copy it verbatim. The advisor ran exactly these edits on a copy of
> the repo at `231049a` and got the results quoted under each step.
>
> **Drift check (run first, from the project root, in Git Bash)**:
> `git diff --stat 231049a..HEAD -- docs/error-catalog.md src/cea/parser.py tests/unit/test_catalog.py tests/unit/test_diagnostics.py tests/unit/test_parser_core.py tests/unit/test_parser_panic.py tests/unit/test_parser_repairs.py`
> must print **nothing**. If it prints anything, compare the "Current state"
> excerpts below with the live files; on any mismatch, STOP and report.

## Status

- **Priority**: P1 (milestone 2 starts here; the AI layer of plan 011 will read these messages)
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (milestone 1, plans 005–007, is merged)
- **Category**: bug
- **Planned at**: commit `231049a`, 2026-10-10

## Why this matters

The project is a course compiler for a strict C99 subset (Python, `src/cea/`). Every diagnostic's text comes from a template in `docs/error-catalog.md`. SYN-UNBALANCED-BRACKET has ONE template, written for the "missing closer" case: `Expected '{expected}' to close '{opener}' from line {open_line} but found '{found}'`. The same code is also chosen for a **stray closer** (a `}`, `)` or `]` that nothing opened; catalog selection rule 3, second clause). Then there is no opener, so the parser fills `?` and the student sees nonsense:

```
int main(void) { return 0; }
}
```
gives today: `Expected 'type' to close '{' from line ? but found '}'`.

After this plan the message is `Unbalanced bracket at '}': nothing opened it`, and the missing-closer case reads `Unbalanced bracket at '{': expected ')' to close '(' from line 3`. Milestone 2's AI explanation layer (plan 011) builds on these messages, so they must be right first. This was recorded as a follow-up in `plans/README.md` ("From plan 006's review: the stray-closer message is wrong").

## Current state

- `docs/error-catalog.md` line 30, the row to change (7 cells; `tools/check_spec.py` checks the row shape):
  ```
  | SYN-UNBALANCED-BRACKET | syntax | fatal | unclosed-delimiter | `<production>` | Expected '{expected}' to close '{opener}' from line {open_line} but found '{found}' | `if (x > 1 { }` |
  ```
- `src/cea/diagnostics.py` (`ErrorSink.report`, NOT changed): formats the template with `found=`, `expected=` (rendered) and `**message_args`. `str.format` ignores unused keyword arguments, so a template that no longer uses `{expected}` is fine. A placeholder with no value raises `KeyError` (strict).
- `src/cea/parser.py` lines 238–256, `Parser.message_args` (the only code that fills `opener`/`open_line`; `grep -n "opener\|open_line" src/cea/parser.py` → only lines 245, 248, 249):
  ```python
      def message_args(self, code: str, tok: Token, expected: list[str]) -> dict[str, object]:
          if code in ("SYN-MISSING-SEMICOLON", "SYN-UNEXPECTED-EOF"):
              ...
          if code == "SYN-UNBALANCED-BRACKET":
              want = OPENER_OF.get(expected[0]) if expected and expected[0] in OPENER_OF else None
              if want is None:                                  # rule 3 via a stray closer
                  return {"opener": OPENER_OF.get(tok.text, "?"), "open_line": "?"}
              for b in reversed(self.brackets):
                  if b.text == want:
                      return {"opener": b.text, "open_line": b.line}
              return {"opener": want, "open_line": "?"}
          if code == "SYN-UNSUPPORTED-FEATURE":
              ...
          return {}

      def report(self, code: str, tok: Token, expected: list[str], *,
                 at: tuple[int, int] | None = None) -> str:
  ```
  `OPENER_OF = {")": "(", "]": "[", "}": "{"}` (line 43). `self.brackets` is the stack of opener tokens consumed by successful matches (`docs/error-recovery.md` §4.1).
- Every test that depends on the template (found with `grep -rn "to close\|from line\|open_line\|opener" tests src docs tools`):
  - `tests/unit/test_catalog.py:57-58`: asserts the raw template string.
  - `tests/unit/test_diagnostics.py:85-87`: fills the template with `opener="(", open_line=3`.
  - `tests/unit/test_parser_repairs.py:64` and `:79`: assert two full messages.
  - `tests/unit/test_diagnostics.py:69-70` use the literal string `"Expected '{expected}' to close"` only to test `render_expected()`'s quoting rule. They do NOT read the catalog. **Leave them unchanged.**
  - `tests/unit/test_parser_panic.py:87-98`: two stray-closer tests that assert codes but not messages (this plan adds message asserts).
- Message strings in the dev/valid corpus today (advisor probe; there are no message asserts in corpus tests):
  - `dev/009`: `Expected ')' to close '(' from line 6 but found '{'`
  - `dev/041`: `Expected '}' to close '{' from line 3 but found 'int'`
  - `dev/050`: `Expected ')' to close '(' from line 7 but found '{'`
- `docs/error-recovery.md` §4.3/§4.7 say "the message names the `(` that opened the header and its line" and "names the innermost open `{` and its line". The new detail still does that, so those docs need no change.
- `plans/m1-architecture.md` §6: "No changes to `docs/`" applied to plans 005–007. **This plan is explicitly allowed to edit `docs/error-catalog.md`, one row only.** No other doc changes.

## Commands you will need

| Purpose | Command (project root, Git Bash) | Expected on success |
|---|---|---|
| venv (once, if `.venv` is missing) | `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt` | exit 0 |
| Tests | `.venv/Scripts/python -m pytest -q` | `858 passed, 20 deselected` before you start |
| Spec check | `.venv/Scripts/python tools/check_spec.py` | `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules` |
| Probe | `printf 'int main(void) { return 0; }\n}\n' > /tmp/p008.c && PYTHONPATH=src .venv/Scripts/python -m cea /tmp/p008.c` | see Step 1 |

The counts above assume `gcc` is on PATH (1 gcc test runs). Without gcc that test is skipped, and every "N passed" below becomes "N-1 passed, 1 skipped".

## Scope

**In scope** (the only files you may modify):
- `docs/error-catalog.md` (the SYN-UNBALANCED-BRACKET row only)
- `src/cea/parser.py` (`message_args` and a new method `bracket_detail`)
- `tests/unit/test_catalog.py`, `tests/unit/test_diagnostics.py`, `tests/unit/test_parser_repairs.py`, `tests/unit/test_parser_panic.py`, `tests/unit/test_parser_core.py`
- `plans/README.md` (status row 008 only)

**Out of scope** (do NOT touch):
- `src/cea/diagnostics.py`, `src/cea/catalog.py`: the formatting rules stay as they are.
- Catalog selection rules 0–5 (`docs/error-catalog.md` "Choosing among syntax codes") and `Parser.select_code`: which code is chosen does not change, only its text.
- Any other catalog row, `docs/error-recovery.md`, `docs/language-spec.md`, `tests/corpus/**` (sidecars hold no messages).
- `plans/005`–`007` (historical), `VIVA.md`.
- `tests/unit/test_diagnostics.py` lines 69–70 (see Current state).

## Git workflow

- Branch: `advisor/008-fix-stray-closer-message` from `main`.
- One commit per step. Stage by explicit path (never `git add -A` / `git add .`). Message style follows `git log` (e.g. `cea: add compile pipeline and trace tests (plan 007 step 4)`). Every commit message ends with a blank line and then:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
- Do NOT push (there is no remote). Do NOT merge; the owner reviews first.

## Steps

### Step 1: New catalog template, parser detail, and the tests that assert the old text

1. `docs/error-catalog.md`: in the SYN-UNBALANCED-BRACKET row, replace the message cell (only that cell):
   - old cell text: `Expected '{expected}' to close '{opener}' from line {open_line} but found '{found}'`
   - new cell text: `Unbalanced bracket at '{found}': {detail}`

   The full row afterwards (exact content):
   ```
   | SYN-UNBALANCED-BRACKET | syntax | fatal | unclosed-delimiter | `<production>` | Unbalanced bracket at '{found}': {detail} | `if (x > 1 { }` |
   ```

2. `src/cea/parser.py`, in `Parser.message_args`, replace these 8 lines:
   ```python
           if code == "SYN-UNBALANCED-BRACKET":
               want = OPENER_OF.get(expected[0]) if expected and expected[0] in OPENER_OF else None
               if want is None:                                  # rule 3 via a stray closer
                   return {"opener": OPENER_OF.get(tok.text, "?"), "open_line": "?"}
               for b in reversed(self.brackets):
                   if b.text == want:
                       return {"opener": b.text, "open_line": b.line}
               return {"opener": want, "open_line": "?"}
   ```
   with:
   ```python
           if code == "SYN-UNBALANCED-BRACKET":
               return {"detail": self.bracket_detail(tok, expected)}
   ```

3. `src/cea/parser.py`: insert this new method directly ABOVE `    def report(self, code: str, tok: Token, expected: list[str], *,` (keep one blank line between methods, as in the rest of the class):
   ```python
       def bracket_detail(self, tok: Token, expected: list[str]) -> str:
           """The {detail} of SYN-UNBALANCED-BRACKET (plan 008).

           Missing closer (the expected set is a closing bracket): name the innermost
           open opener and its line. Stray closer (catalog rule 3, second clause):
           say that nothing opened it.
           """
           closer = expected[0] if expected and expected[0] in OPENER_OF else None
           if closer is None:                                    # rule 3 via a stray closer
               return "nothing opened it"
           want = OPENER_OF[closer]
           for b in reversed(self.brackets):
               if b.text == want:
                   return f"expected '{closer}' to close '{want}' from line {b.line}"
           return f"expected '{closer}' but no '{want}' is open"
   ```
   (`tok` is unused today; it is kept so the signature matches `message_args` and a later plan can quote the token.)

4. `tests/unit/test_catalog.py`, in the `test_message_templates` parameter list, replace
   ```python
       ("SYN-UNBALANCED-BRACKET",
        "Expected '{expected}' to close '{opener}' from line {open_line} but found '{found}'"),
   ```
   with
   ```python
       ("SYN-UNBALANCED-BRACKET", "Unbalanced bracket at '{found}': {detail}"),
   ```

5. `tests/unit/test_diagnostics.py`, in the `test_message_is_the_filled_template` parameter list, replace
   ```python
       ("SYN-UNBALANCED-BRACKET",
        dict(found="{", expected=[")"], rule_ref="while_stmt", opener="(", open_line=3),
        "Expected ')' to close '(' from line 3 but found '{'"),
   ```
   with (two cases; this adds 1 test):
   ```python
       ("SYN-UNBALANCED-BRACKET",
        dict(found="{", expected=[")"], rule_ref="while_stmt",
             detail="expected ')' to close '(' from line 3"),
        "Unbalanced bracket at '{': expected ')' to close '(' from line 3"),
       ("SYN-UNBALANCED-BRACKET",
        dict(found="}", expected=["type"], rule_ref="type_spec", detail="nothing opened it"),
        "Unbalanced bracket at '}': nothing opened it"),
   ```

6. `tests/unit/test_parser_repairs.py`:
   - replace `    assert recs[0].message == "Expected ')' to close '(' from line 3 but found '{'"`
     with `    assert recs[0].message == "Unbalanced bracket at '{': expected ')' to close '(' from line 3"`
   - replace `    assert recs[0].message == "Expected '}' to close '{' from line 3 but found 'int'"`
     with `    assert recs[0].message == "Unbalanced bracket at 'int': expected '}' to close '{' from line 3"`

**Verify**:
- `.venv/Scripts/python -m pytest -q` → `859 passed, 20 deselected`
- `.venv/Scripts/python tools/check_spec.py` → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`
- `grep -rn "open_line\|'{opener}'" src docs tests/unit` → no output
- Probe (table above) → stdout line 1 is `E-0001 p008.c:2:1: fatal [SYN-UNBALANCED-BRACKET] Unbalanced bracket at '}': nothing opened it`, then `1 fatal, 0 warnings`; exit status 1.

Commit: `cea: neutral SYN-UNBALANCED-BRACKET message for stray closers (plan 008 step 1)`, staging exactly these 5 paths: `docs/error-catalog.md src/cea/parser.py tests/unit/test_catalog.py tests/unit/test_diagnostics.py tests/unit/test_parser_repairs.py`.

### Step 2: Regression tests for the stray-closer text

1. `tests/unit/test_parser_panic.py`, in `test_stray_closing_brace_at_top_level`, after the line `    assert recs[0].rule_ref == "type_spec"` add:
   ```python
       assert recs[0].message == "Unbalanced bracket at '}': nothing opened it"
   ```
2. Same file, in `test_brackets_opened_in_a_failed_statement_are_forgotten`, after the line ending `# stray: its '(' was dropped` add:
   ```python
       assert recs[1].message == "Unbalanced bracket at ')': nothing opened it"
   ```
3. `tests/unit/test_parser_core.py`: insert these two tests directly ABOVE `def test_caused_by_precedence_r2_then_r1_then_r9():` (two blank lines between top-level functions):
   ```python
   def test_bracket_detail_names_opener_or_says_nothing_opened_it():
       p, _ = make("( x )")
       p.match("(")                                                           # '(' on line 1 is open
       assert p.bracket_detail(p.cur, [")"]) == "expected ')' to close '(' from line 1"
       assert p.bracket_detail(p.cur, ["]"]) == "expected ']' but no '[' is open"
       p.pos = 2
       assert p.bracket_detail(p.cur, [P.EXPR]) == "nothing opened it"         # stray closer


   def test_probe_stray_closing_brace_message():
       src = "int main(void) { return 0; }\n}\n"
       sink = ErrorSink(src)
       P.parse(lex(src, sink), sink)
       (rec,) = sink.records
       assert rec.code == "SYN-UNBALANCED-BRACKET" and (rec.line, rec.column) == (2, 1)
       assert rec.message == "Unbalanced bracket at '}': nothing opened it"
       assert "?" not in rec.message
   ```
   (`make`, `P`, `ErrorSink` and `lex` are already imported/defined at the top of that file. The `\n` inside the string is a Python escape: backslash then `n`, not a real line break.)

**Verify**: `.venv/Scripts/python -m pytest -q` → `861 passed, 20 deselected`; `.venv/Scripts/python -m pytest -q tests/unit/test_parser_core.py -k "bracket_detail or probe_stray"` → `2 passed`.

Commit: `tests: stray-closer message regression tests (plan 008 step 2)`, staging `tests/unit/test_parser_panic.py tests/unit/test_parser_core.py`.

### Step 3: Status row

In `plans/README.md`, "Milestone 2" table, set row 008's Status to `DONE (861 passed)` (keep the other columns). Commit `plans: 008 done`, staging `plans/README.md`.

## Test plan

- Changed: 4 existing assertions now expect the new text (catalog template, diagnostics fill, 2 parser repairs).
- New: 1 diagnostics case (stray-closer fill), 2 message asserts inside existing panic tests, 2 new parser-core tests (all three `bracket_detail` branches, and the PRD probe end to end).
- Final: `861 passed, 20 deselected` (858 + 1 + 2).

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` → `861 passed, 20 deselected`
- [ ] `.venv/Scripts/python tools/check_spec.py` → `OK: 37 codes, ...`
- [ ] `grep -c "Unbalanced bracket at '{found}': {detail}" docs/error-catalog.md` → `1`
- [ ] `grep -rn "from line ?" src tests` → no output; the probe prints `nothing opened it`
- [ ] `git diff --name-only main..HEAD` (on the plan branch) lists only the 8 in-scope paths
- [ ] `plans/README.md` row 008 updated

## STOP conditions

Stop and report (do not improvise) if:
- The drift check prints anything and the excerpts above do not match the live code.
- `check_spec.py` reports anything but `OK: 37 codes` after Step 1 (for example a 6- or 8-column row: a `|` crept into the message cell).
- Any test outside the 5 listed test files fails after Step 1. That would mean another place depends on the old text; list it in your report rather than editing it.
- A `KeyError: 'detail'` (or `'opener'`) appears anywhere: some caller creates SYN-UNBALANCED-BRACKET without going through `Parser.report`. `grep -rn "SYN-UNBALANCED-BRACKET" src` should show only `src/cea/parser.py`.
- You feel the wording should be different. The wording is the advisor's choice; propose alternatives in the report instead.

## Maintenance notes

- The catalog template is now generic and the parser owns the wording of `{detail}`. Any future phrase-level repair that reports SYN-UNBALANCED-BRACKET must go through `Parser.report` so `detail` is filled.
- The branch `expected ']' but no '[' is open` is defensive: no corpus program reaches it (a closer is only expected after its opener was matched). It exists so a parser bug can never print `?` again.
- Plan 011 (AI explanations) will quote `record.message`; a reviewer should check that the three detail forms read well as a sentence after "Unbalanced bracket at 'X':".
- `plans/006-*.md` still quotes the old template; that file is a historical record and is not updated.

## Viva notes (ask the executor to report)

End your report with a **Viva notes** list covering at least: why one template with a parser-filled `{detail}` was chosen over two catalog codes (keeps 37 codes, the F9 category and the selection rules unchanged); why `{expected}` left the template (for a stray closer the expected set is e.g. `type` or `expression`, which is not a bracket); and the exact before/after text of the probe.
