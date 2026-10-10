# Plan 007: Build the milestone-1 semantic analyser, pipeline and CLI, and switch on the corpus tests

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
> Every code block marked "exact content" is the file to write. Copy it
> verbatim. Do not "improve" it, reformat it or add features. The code was run
> by the advisor against a throwaway lexer and parser that follow
> `plans/m1-architecture.md`, and it reproduced every trace table and passed
> every dev and valid corpus program (see "Advisor's verification"). If a
> verification fails, first compare your file with the plan. If they are
> identical, the cause is in plan 005/006 code or in the plan: STOP and report.
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat efeb049..HEAD -- src/cea/semantic.py src/cea/pipeline.py src/cea/cli.py src/cea/__main__.py tests/test_recovery_traces.py tests/unit/test_semantic.py tests/unit/test_pipeline_cli.py docs/language-spec.md` must print **nothing**, and none of those 7 files may exist yet (`ls src/cea/semantic.py src/cea/pipeline.py src/cea/cli.py src/cea/__main__.py tests/test_recovery_traces.py tests/unit/test_semantic.py tests/unit/test_pipeline_cli.py 2>&1 | grep -c "No such file"` → `7`).
> 2. `test -f src/cea/parser.py && test -f src/cea/lexer.py && test -f src/cea/diagnostics.py && echo READY` must print `READY` (plans 005 and 006 have landed).
> 3. `grep -cE '^\| R9 ' docs/error-recovery.md` must print `1` (plan 004 has landed).
> 4. `grep -c 'last statement is a .return., or an .if. with an .else. whose branches both' docs/language-spec.md` must print `1` (the `sem.return_paths` paragraph that Step 2 rewrites is still the original).
> 5. `grep -c 'The first statement after a .return., .break. or .continue. in the same block' docs/language-spec.md` must print `1` (the `sem.unreachable` paragraph that Step 2 rewrites is still the original).
>
> If any check fails, STOP and report which one.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED (it is the last phase of the pipeline and the first plan that runs the whole corpus; any 005/006 deviation from the contract surfaces here)
- **Depends on**: `plans/004-amend-recovery-spec-corpus-gaps.md` (merged), `plans/005-m1-foundation-records-catalog-lexer.md`, `plans/006-*.md` (the parser)
- **Category**: direction (milestone 1: PRD F1 and F4)
- **Planned at**: commit `efeb049`, 2026-10-10 (first drafted against `b0352b1`; `efeb049` contains the merged plans 004 and 005 and the contract amendments from the review of this plan; plan 006 merges after it and before this plan runs)

## Why this matters

The project is the "Compiler Error Assistant": a course compiler for a strict C99 subset, written in Python, that records every error as a structured record and links cascading errors to their cause through `caused_by`. Milestone 1 delivers PRD F1 ("each compiler phase (lexical, syntax, semantic) reports errors through one interceptor"; acceptance: "a test file with one lexical, one syntax and one semantic error yields three records with the correct phase and position") and F4 ("every error is labelled fatal or warning … the summary line shows counts, for example '2 fatal, 3 warnings'"; acceptance: "a file with only warnings still compiles and reports them").

Plans 005 (records, catalog, error sink, lexer) and 006 (parser) build the first two phases. This plan builds the third phase (the semantic analyser: 22 SEM/WRN codes, the `<error>` type and the cascade rules R3–R8), the `compile_source` pipeline and the command line. Creating `src/cea/pipeline.py` switches on `tests/test_corpus_compile.py`, so after this plan every dev and valid corpus program is checked automatically, and the ten hand-traced examples of `docs/error-recovery.md` §9 become exact-match tests. That closes milestone 1.

## Current state

Files you will read but not change (all exist when the drift check passes):

- `plans/m1-architecture.md`: **the binding interface contract**. §5 defines what this plan must provide:
  ```python
  # semantic.py
  def analyze(program: A.Program, sink: ErrorSink, stdio_include: Position | None) -> None: ...

  # pipeline.py
  @dataclass
  class CompileResult:
      errors: list[ErrorRecord]       # sink.records, creation order
      program: A.Program
      tokens: list[Token]
      @property
      def ok(self) -> bool: ...       # True iff no record has severity "fatal" (PRD F4: "a file with only warnings still compiles")
      def summary(self) -> str: ...   # delegates to ErrorSink.summary()

  def compile_source(source: str, filename: str) -> CompileResult: ...
      # sink = ErrorSink(source); lr = lex(source, sink); prog = parse(lr, sink); analyze(prog, sink, lr.stdio_include)
      # never raises on any input; root_id stays == id (F2 is milestone 2)
  ```
  §1: "`__main__.py` contains only `from cea.cli import main` and `raise SystemExit(main())`; **`cli.py` is the only module allowed to call `print`**." Plan 005 added `tests/unit/test_no_print.py`, which greps `src/cea/*.py` for `print(` and `sys.stdout`/`sys.stderr` and allows them only in `cli.py`.
  §2 (amended in the review of plan 005): `ErrorSink.report(code, line, column, *, found, expected=(), span_end=None, caused_by=None, rule_ref=None, **message_args)`. "For lexical and semantic codes the [`{expected}`] items are inserted raw … `{found}` is always inserted raw … Formatting is **strict**: a missing placeholder raises `KeyError`." Default `span_end` is zero-width when `found == "EOF"`, otherwise `Position(line, column + max(len(found),1) - 1)`. When `rule_ref` is passed it must be a grammar rule name; semantic records never pass it (the catalog's `sem.*` value is used).
  §2 also says (amended in the review of this plan): "For codes whose template uses `{found}` as a type name or count (SEM-TYPE-MISMATCH, SEM-ARG-COUNT, SEM-ARG-TYPE, SEM-RETURN-TYPE, SEM-INDEX-NOT-INT, WRN-IMPLICIT-NARROWING), `found` holds that type/count text, and the caller passes `span_end` explicitly."
  §4: `Program`'s "span = 1:1 .. the EOF token's position …; semantic uses span.end_* as the EOF position".
  §6: "**One advisor-approved exception:** plan 007 rewrites the `sem.return_paths` paragraph of `docs/language-spec.md` (a block returns on every path if ANY of its statements does; statements after it are unreachable), because the literal 'last statement' wording made `return 1; f();` also warn about a missing return. The same step also rewrites the `sem.unreachable` paragraph so it matches: the first statement after a `break`, a `continue`, or any statement that returns on every path (including an `if`/`else` whose branches both return) is unreachable."
  §4: the AST (`src/cea/ast.py`, plan 006). Import it as `from cea import ast as A`. The node classes this plan consumes: `Program(decls, span)`, `Param(type_name, name, name_pos, span)`, `FunctionDecl(ret_type, name, name_pos, params, body, span, error_id, idents_in_span)`, `VarDecl(type_name, name, name_pos, array_size, init, is_global, span, error_id, idents_in_span)`, `VarDeclStmt(decls, span)`, `Block(stmts, span, orphan_of, closed_by_repair)`, `If(cond, then, els, span)`, `While(cond, body, span)`, `For(init, cond, step, body, span)`, `Return(value, span)` ("span starts at 'return'"), `Break(span)`, `Continue(span)`, `ExprStmt(expr, span)`, `EmptyStmt(span)`, `ErrorStmt(span, error_id, kind_hint, declared_names, idents_in_span, stopped_before)`, `IntLit`, `FloatLit`, `CharLit`, `StringLit` (each `value, span`), `Name(name, span)`, `Unary(op, operand, postfix, span)`, `Binary(op, left, right, op_pos, span)`, `Assign(op, target, value, op_pos, span)`, `Call(callee, args, span)`, `Index(base, index, span)`, `ErrorExpr(span, error_id)`.
- `docs/language-spec.md` §3 (types) and §4 (16 `sem.*` rules). Key lines: "Integer types are `int` and `char`. Floating types are `float` and `double`. `void` is a return type only." "String literals have no usable type. Their only legal use is as the first argument of `printf`." "A floating value converted to an integer type gives the warning WRN-IMPLICIT-NARROWING." "An array name is not a value: it cannot be assigned, returned or passed." `sem.unused_declaration` (amended by plan 004): "Assigning with `=` is not a read. Compound assignment (`+=` and the like) and `++`/`--` both read and write. Parameters and globals are exempt." `sem.return_paths` (today; Step 2 rewrites it): "the body's last statement is a `return`, or an `if` with an `else` whose branches both return on every path (recursively through blocks). Loops never count." `sem.unreachable` (today; Step 2 rewrites it): "The first statement after a `return`, `break` or `continue` in the same block produces one warning."
- `docs/error-catalog.md`: the 22 SEM/WRN rows (code, severity, `rule_ref`, template). The templates' placeholders are: SEM-UNDECLARED-VAR/FUNC `{name}`; SEM-REDECLARED `{name}`, `{prev_line}`; SEM-CONFLICTING-TYPES `{name}`, `{prev_sig}`, `{sig}`; SEM-TYPE-MISMATCH `{found}`, `{expected}`; SEM-NOT-CALLABLE `{name}`; SEM-ARG-COUNT `{name}`, `{expected}`, `{found}`; SEM-ARG-TYPE `{index}`, `{name}`, `{expected}`, `{found}`; SEM-RETURN-TYPE `{name}`, `{expected}`, `{found}`; SEM-NOT-ARRAY `{name}`; SEM-INDEX-NOT-INT `{found}`; SEM-BREAK-OUTSIDE-LOOP `{found}`; WRN-UNUSED-VAR `{name}`; WRN-IMPLICIT-NARROWING `{found}`, `{expected}`; WRN-MISSING-RETURN `{name}`; the other six have none.
- `docs/error-recovery.md` (as amended by plan 004):
  - §6: "On `ErrorStmt` it does nothing … On a broken declaration it declares the name and analyses whatever parts are not `ErrorExpr`." "**Type checks absorb `<error>`.**" "**Shape checks still run** on `ErrorExpr` operands … SEM-BAD-ARRAY-SIZE … SEM-NONCONST-GLOBAL-INIT … SEM-PRINTF-FORMAT … the record gets `caused_by` by R3." "The compound assignments `+=` … and the operators `++` and `--` … **read and write** their target … An array element target `a[i] = …` reads `i` and writes `a`."
  - §7 rules R3–R8 (the semantic ones), quoted exactly:
    > | R3 poison operand | SEM-BAD-ARRAY-SIZE, SEM-NONCONST-GLOBAL-INIT, SEM-PRINTF-FORMAT | the operand that fails the shape check is an `ErrorExpr` | that `ErrorExpr.error_id` |
    > | R4 broken declaration | WRN-UNUSED-VAR | the declaration it is about has `error_id` set | that `error_id` |
    > | R5 lost declaration | SEM-UNDECLARED-VAR, SEM-UNDECLARED-FUNC for name n; SEM-MISSING-MAIN (n = `main`) | an earlier node (in source order) in the current function body or at file scope is an `ErrorStmt` with n in `declared_names`, or a broken declaration named n | the `error_id` of the nearest such node |
    > | R6 lost read | WRN-UNUSED-VAR for variable v (when R4 does not apply) | an `ErrorStmt`, `ErrorExpr` or broken declaration in v's scope, after v's declaration, has v's name in `idents_in_span` | the `error_id` of the first such node |
    > | R7 orphan loop body | SEM-BREAK-OUTSIDE-LOOP | the `break`/`continue` is inside (at any depth, with no real `while` or `for` node in between) a `Block` whose `orphan_of` points to an `ErrorStmt` with `kind_hint` `while`, `for` or `unsupported` | `orphan_of` |
    > | R8 incomplete body | WRN-MISSING-RETURN | the function body contains an `ErrorStmt` at any depth, or the body `Block` has `closed_by_repair` set (§4.7) | the `error_id` of the first `ErrorStmt` in source order, else `closed_by_repair` |
  - §7 "Provisional F2 root rule": "`root(r) = root(caused_by(r))` if `caused_by` is set. Otherwise, if r is SEM-UNDECLARED-VAR or SEM-UNDECLARED-FUNC and an earlier record with the same code and the same name exists in the same function body (or both at file scope), `root(r)` = that record's root … Otherwise `root(r) = r.id`."
  - §8: "Semantic errors are reported at the offending identifier or operator." "SEM-MISSING-MAIN has no identifier. It is reported at the EOF position."
  - §9: traces T1, T1b, T2–T9 with a record table (`| Trace | Id | Code | Line:Col | Found | caused_by | root_id |`) and a summary table. The test in Step 4 contains both tables verbatim.
- `tests/test_corpus_compile.py` (do not modify): starts with `pipeline = pytest.importorskip("cea.pipeline")`, so it is skipped until `src/cea/pipeline.py` exists. It is "deliberately a SUBSET check: every expected root and warning must be reported with the same (code, line)", and `valid/` programs must have no fatal record. Held-out cases carry the `heldout` marker and are deselected by `pyproject.toml` (`addopts = "-m 'not heldout'"`).
- `tests/corpus/README.md` §4 (location convention used by the sidecars): "SEM-REDECLARED and SEM-CONFLICTING-TYPES: at the later declaration's name. SEM-ARG-COUNT, SEM-ARG-TYPE and SEM-PRINTF-FORMAT: at the called function's name." "WRN-UNUSED-VAR: at the variable's name in its declaration. WRN-MISSING-RETURN: at the function's name in its definition. WRN-UNREACHABLE-CODE: at the first unreachable statement … WRN-ASSIGN-IN-CONDITION and WRN-IMPLICIT-NARROWING: at the statement or declaration containing the `=`."
- `tests/corpus/README.md` §5, the **held-out rule**: "files in `heldout/` must never be read or used when designing or tuning …". You must not open, print or run anything under `tests/corpus/heldout/`. Never pass `-m heldout` to pytest.
- Test style exemplar: `tests/test_corpus_schema.py` (module docstring, small helpers, `pytest.mark.parametrize` tables, plain `assert`). There is no `tests/__init__.py` and no `tests/unit/__init__.py`; do not create them.

## Design decisions (each one checked against the traces)

These are fixed by this plan. They are implemented by the code below; you do not need to re-derive them, but you must report them in your Viva notes.

1. **Type representation.** Scalars are the strings `"int"`, `"char"`, `"float"`, `"double"`, `"void"`. A string literal has the pseudo-type `"string literal"` (spec §3: "no usable type"), which is not arithmetic, so every use except printf's first argument fails a check. `ArrayType(elem, size)`, `FuncType(ret, params)` and `ErrorType(cause)` are frozen dataclasses. `ErrorType.cause` is the id of the record that explains the unknown type: an `ErrorExpr`'s `error_id`, or the id of the SEM-UNDECLARED-VAR/FUNC, SEM-NOT-CALLABLE, SEM-NOT-ARRAY, SEM-TYPE-MISMATCH or SEM-VOID-VALUE record just created. Every check that sees an `ErrorType` passes silently (§6 "type checks absorb `<error>`"), which is why T4 and T9 have no type errors. Literal types: `IntLit` → int, `FloatLit` → double (C rule), `CharLit` → char.
2. **Scopes.** A stack of `Scope` objects; `scopes[0]` is file scope (globals, functions, the printf builtin). A function pushes ONE scope that holds the parameters and the body's top-level declarations (spec: "Parameters live in the function body's outermost scope"), so the body `Block` does not push another. Every nested `Block` (including orphan blocks) pushes a scope. A `for` pushes a scope for its init declaration (C99 6.8.5p5); its body block pushes its own, so `for (int i…) { int i; }` is legal, as in gcc. A variable is in scope during its own initialiser (C99 rule; `int x = x;` reads the new `x`).
3. **One pass, in source order.** C99 requires declaration before use, so a single pass is complete: a function's signature enters file scope when its `FunctionDecl` is reached, before its body is walked (recursion works), and a call earlier in the file than any declaration is SEM-UNDECLARED-FUNC (`dev/017`, `dev/047`). For `sem.function_declarations`: prototype then definition with equal signatures is fine (`valid/002`); a later declaration with a different return or parameter type list is SEM-CONFLICTING-TYPES at the later name (`dev/019`), and the symbol keeps the first signature; a second definition with an equal signature is SEM-REDECLARED; a function and a variable with the same file-scope name is SEM-REDECLARED. When a declaration both conflicts and redefines, only SEM-CONFLICTING-TYPES is reported.
4. **Record order** (invariant 5; ids follow creation order):
   - Statements and expressions are visited depth-first, left to right (an assignment's target before its value). A record is created when its check runs.
   - Declarations: SEM-REDECLARED / SEM-VOID-VALUE at the name come first, then the shape check of the array size (SEM-BAD-ARRAY-SIZE) and of a global initialiser (SEM-NONCONST-GLOBAL-INIT), then the records inside the initialiser, then the conversion check of the initialiser.
   - Calls: callee checks first (SEM-UNDECLARED-FUNC, SEM-NOT-CALLABLE, SEM-ARG-COUNT, SEM-PRINTF-FORMAT), then every argument's own records, then the per-argument checks (SEM-ARG-TYPE, WRN-IMPLICIT-NARROWING, SEM-VOID-VALUE) in argument order.
   - Index: SEM-NOT-ARRAY right after the base, SEM-INDEX-NOT-INT after the index expression.
   - **WRN-UNREACHABLE-CODE** is created during the block walk, *before* the records of the unreachable statement itself. A block is "terminated" after a `break`, a `continue`, or any statement that returns on every path (decision 9), so `if (b) return 1; else return 2; x = 3;` warns at `x = 3`. If that first statement is an `ErrorStmt`, no warning is created (the analyser "does nothing" on `ErrorStmt`, §6). T8 depends on this: its orphan block is `[ErrorStmt(case), Break, ErrorStmt(default)]`, and the reference table has no unreachable warning.
   - **WRN-ASSIGN-IN-CONDITION** is created after all records of the condition expression.
   - **WRN-UNUSED-VAR** is created when a scope is popped, for its variables in declaration order (inner scopes therefore come before outer ones). A function's outermost scope is popped at the end of its body. T1b and T3 check this.
   - **WRN-MISSING-RETURN** is created after the function's outermost-scope unused warnings, at the end of the function. T2 checks it.
   - **SEM-MISSING-MAIN** is the very last record, at the EOF position.
5. **Every SEM/WRN code** (location; `found`; `expected`; message arguments; `span_end`):

   | Code | Location | `found` | `expected` | Message args | `span_end` |
   |---|---|---|---|---|---|
   | SEM-UNDECLARED-VAR | the name | name | — | name | default |
   | SEM-UNDECLARED-FUNC | callee name | name | — | name | default |
   | SEM-REDECLARED | later declaration's name | name | — | name, prev_line | default |
   | SEM-CONFLICTING-TYPES | later declaration's name | name | — | name, prev_sig, sig (e.g. `int f(int)`) | default |
   | SEM-TYPE-MISMATCH | initialisation: the declarator name; assignment and operators: the operator (`op_pos`); condition: the condition's start | the bad type (`string literal`, `double`, `array int[5]`, …) | the required type, or `an arithmetic value` / `an integer` / `a variable or array element` | — | end of the name / operator / condition |
   | SEM-VOID-VALUE | the void call's callee name; a void variable or parameter's name | that name | — | — | default |
   | SEM-NOT-CALLABLE | callee name | name | — | name | default |
   | SEM-ARG-COUNT | callee name | `str(len(args))` | `[str(len(params))]` | name | end of the callee name |
   | SEM-ARG-TYPE | callee name | the argument's type | `[param type]` (printf: `an arithmetic value`) | name, index (1-based) | end of the callee name |
   | SEM-RETURN-TYPE | the `return` keyword | the value's type, or `nothing` for `return;` | `[return type]` | name | end of `return` |
   | SEM-NOT-ARRAY | the base name | name | — | name | end of the base |
   | SEM-INDEX-NOT-INT | the index expression's start | its type | — | — | end of the index |
   | SEM-BAD-ARRAY-SIZE | the size expression's start | its text (unparsed) | — | — | end of the size |
   | SEM-BREAK-OUTSIDE-LOOP | the keyword | `break` / `continue` | — | — | default |
   | SEM-NONCONST-GLOBAL-INIT | the initialiser's start | its text | — | — | end of the initialiser |
   | SEM-PRINTF-FORMAT | the `printf` name | `printf` | — | — | default |
   | SEM-MISSING-MAIN | the EOF position | `EOF` | — | — | zero-width |
   | WRN-UNUSED-VAR | the name in the declaration | name | — | name | default |
   | WRN-UNREACHABLE-CODE | start of the first unreachable statement | its first token's text | — | — | default |
   | WRN-IMPLICIT-NARROWING | initialisation: declarator name; assignment: operator; return: `return`; argument: callee name | the floating type | `[integer type]` | — | end of that token |
   | WRN-MISSING-RETURN | the function's name in its definition | name | — | name | default |
   | WRN-ASSIGN-IN-CONDITION | the `=` | `=` | — | — | zero-width (one character) |

   Note on `found`: the contract describes `found` as "offending text", but six templates use `{found}` for a type or a count ("Cannot use {found} where {expected} is required"). For those codes `found` holds the type or count, and `span_end` is passed explicitly so it still covers the offending token. With the amended raw rendering this gives, for example, "Cannot use string literal where int is required" and "'add' expects 2 argument(s) but got 1".
6. **The printf builtin** (`sem.builtins`). `printf` is inserted into file scope (as `FuncType("int", ())`, marked as the builtin by `decl=None`) the first time the analyser reaches a top-level declaration or a call whose position is after `stdio_include` (the position of the `#` of the first accepted `#include <stdio.h>`). Before that, or with no include, a `printf` call is SEM-UNDECLARED-FUNC. A user declaration of `printf` after the include is SEM-REDECLARED (`prev_line` = the include's line). The first argument must be a `StringLit` (shape check, R3 if it is an `ErrorExpr`); a call with no arguments is also SEM-PRINTF-FORMAT. Further arguments must be arithmetic (SEM-ARG-TYPE otherwise, SEM-VOID-VALUE for a void call). Format specifiers are not checked.
7. **R3–R8**:
   - R3: the shape check's operand (`array_size`, a global `init` or the `-` operand inside it, printf's first argument) is an `ErrorExpr` → its `error_id`.
   - R4: `VarDecl.error_id` of the unused variable.
   - R5: the analyser keeps two lists of `(name, error_id)` in source order: one for the current function body (reset per function) and one for file scope. An `ErrorStmt` adds each of its `declared_names` (including the `"<unsupported>"` ones from plan 004 and `(name, "function")` for a broken function header); a broken `VarDecl` or `FunctionDecl` adds its own name. A SEM-UNDECLARED-VAR/FUNC searches the function list newest-first, then the file list newest-first, which is exactly "the nearest earlier node". SEM-MISSING-MAIN searches the file list for `main`.
   - R6: every scope keeps the `(error_id, idents_in_span)` of each `ErrorStmt` or broken local `VarDecl` visited while it is open, in source order; a symbol remembers how many were there when it was declared, so only later nodes count. `ErrorExpr` carries no `idents_in_span` in the AST contract, but an `ErrorExpr` only ever occurs inside a broken declaration (error-recovery §4.4 catch point (b)), whose `idents_in_span` covers it.
   - R7: a loop stack holds `"loop"` for each real `while`/`for` body and the `orphan_of` id for each orphan `Block` whose `ErrorStmt` has `kind_hint` `while`, `for` or `unsupported`. A `break`/`continue` is legal if any `"loop"` is on the stack; otherwise the record's `caused_by` is the innermost orphan id (or `None`).
   - R8: the first `ErrorStmt` seen in the function body, else `body.closed_by_repair`.
8. **Read/write tracking** (`sem.unused_declaration`). A `Name` evaluated as a value marks its symbol read. The target of a plain `=` is visited with `write=True` (not a read); for `a[i] = …` the base `a` is written and the index `i` is read. Compound assignments and `++`/`--` visit their target as a normal value, so they read. A local variable used as a callee (`max(a, b)` where `max` is an `int`) is marked read, so `dev/022` gets only SEM-NOT-CALLABLE. Only locals (kind `"var"`, including `for`-init variables) are checked; parameters and globals are exempt, and so is a `void` variable, which already has SEM-VOID-VALUE (advisor ruling).
9. **Return paths** (advisor ruling, applied to the spec in Step 2). `returns(stmt)`: a `Return` returns; a `Block` returns if ANY of its statements returns (what follows is unreachable); an `If` returns if it has an `else` and both branches return; everything else (loops included) does not. Applied to non-void functions with a body, except `main`. So `return 1; f();` gives only WRN-UNREACHABLE-CODE, not also WRN-MISSING-RETURN.
10. **Provisional root rule.** `root_id` stays equal to `id` in the pipeline (F2 is milestone 2). `tests/test_recovery_traces.py` computes the provisional roots of error-recovery §7 in a test helper and compares them with the `root_id` column of the trace table and with the summary table's "displayed" count.

## Commands you will need

Run everything from the project root in Git Bash.

| Purpose | Command | Expected on success |
|---|---|---|
| venv (once) | `test -x .venv/Scripts/python \|\| (python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt)` | exit 0 |
| Full suite | `.venv/Scripts/python -m pytest -q` | exit 0; last line `N passed …` (see Step 0 / Step 6) |
| One file | `.venv/Scripts/python -m pytest -q tests/unit/test_semantic.py` | `74 passed` |
| Corpus test only | `.venv/Scripts/python -m pytest -q tests/test_corpus_compile.py` | `66 passed, 20 deselected` |
| Spec checker | `python -I tools/check_spec.py` | `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules` |
| CLI | `PYTHONPATH=src .venv/Scripts/python -m cea tests/corpus/valid/011-narrowing-warning.c` | last line `0 fatal, 1 warning`, exit 0 |

## Scope

**In scope** (create only these, plus the status row in `plans/README.md`):
- `docs/language-spec.md`: ONLY the paragraphs under `### sem.return_paths` and `### sem.unreachable` (Step 2; the advisor-approved docs exception, contract §6)
- `src/cea/semantic.py` (create)
- `src/cea/pipeline.py` (create; **last** of the source files, it switches on the corpus test)
- `src/cea/cli.py` (create)
- `src/cea/__main__.py` (create)
- `tests/unit/test_semantic.py` (create)
- `tests/test_recovery_traces.py` (create)
- `tests/unit/test_pipeline_cli.py` (create)
- `plans/README.md` (the 007 status row only)

**Out of scope** (do NOT touch):
- `src/cea/ast.py`, `parser.py`, `lexer.py`, `tokens.py`, `diagnostics.py`, `records.py`, `catalog.py`, `__init__.py` (plans 005/006). If one of them seems wrong, STOP and report; do not patch it.
- Every other part of `docs/` (including both headings and C examples that Step 2 keeps, and `docs/error-catalog.md`), `tests/corpus/` (including every sidecar), `tests/test_corpus_compile.py`, `tests/corpus_lib.py`, `tools/`, `VIVA.md`, `plans/m1-architecture.md`. A needed spec change is reported, not made.
- `tests/corpus/heldout/`: never read, run or print anything in it.
- Clustering (F2): do not set `root_id` to anything but `id`.

## Git workflow

- Branch: `advisor/007-m1-semantic`, created from `main` (`git switch -c advisor/007-m1-semantic main`). If a reviewer runs you in an isolated worktree, commit on the worktree's branch instead.
- One commit per step that changes files. Stage by explicit path (never `git add -A` or `git add .`).
- Message style (from `git log`): `<area>: <what> (plan 007 step N)`, then a blank line, then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use two `-m` flags, for example `git commit -m "cea: add semantic analyser (plan 007 step 3)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- Do not push, merge or open a PR.

## Steps

### Step 0: Branch, environment and baseline

1. `git switch -c advisor/007-m1-semantic main`
2. Create the venv if it is missing (Commands table).
3. Run `.venv/Scripts/python -m pytest -q` and write down the last line. Call its passed count **B**.

Baseline facts: at `efeb049` (plans 004 and 005 merged) the full suite was `358 passed, 1 skipped`. Plan 006 merges before this plan runs and adds its own tests, so B is larger and is **measured here**, not taken from this plan.

**Verify**: exit status 0; the last line has the form `B passed, 1 skipped in …` (the single skip is `tests/test_corpus_compile.py`, which waits for `cea.pipeline`). Confirm with `.venv/Scripts/python -m pytest -q tests/test_corpus_compile.py` → `1 skipped`. If anything fails or more than one test is skipped, STOP (plans 005/006 are not green).

### Step 1: Probe the plan 005/006 interfaces this plan relies on

Run each command and compare the output exactly. They read only the parser's and sink's behaviour; they write nothing.

1. Program span ends at the EOF token (needed for the SEM-MISSING-MAIN position):
   ```bash
   .venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from cea.diagnostics import ErrorSink; from cea.lexer import lex; from cea.parser import parse; s='void g(void) {\n}\n'; k=ErrorSink(s); lr=lex(s,k); p=parse(lr,k); print(p.span.end_line, p.span.end_col, lr.tokens[-1].line, lr.tokens[-1].col, len(k.records))"
   ```
   Expected `2 2 2 2 0` (contract §4: `Program.span` ends at the EOF token's position). Any other output: STOP; the parser does not follow the contract.
2. Semantic messages render raw (contract §2, amended):
   ```bash
   .venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from cea.diagnostics import ErrorSink; print(ErrorSink('x').report('SEM-ARG-COUNT',1,1,found='1',expected=['2'],name='add').message)"
   ```
   Expected `'add' expects 2 argument(s) but got 1`. Otherwise STOP.
3. The plan-004 parser features the analyser depends on (T9's declarator name, T8's orphan block):
   ```bash
   .venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from cea.diagnostics import ErrorSink; from cea.lexer import lex; from cea.parser import parse; s='int main(void) {\n    int *p;\n    p = 0;\n    return p;\n}\n'; k=ErrorSink(s); p=parse(lex(s,k),k); e=p.decls[0].body.stmts[0]; print(type(e).__name__, e.kind_hint, e.declared_names, e.error_id)"
   .venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from cea.diagnostics import ErrorSink; from cea.lexer import lex; from cea.parser import parse; s='int main(void) {\n    int n = 2;\n    switch (n) {\n        case 1:\n            n = 5;\n            break;\n        default:\n            n = 0;\n    }\n    return n;\n}\n'; k=ErrorSink(s); p=parse(lex(s,k),k); b=p.decls[0].body.stmts; print(b[1].kind_hint, b[1].stopped_before, b[2].orphan_of, [type(x).__name__ for x in b[2].stmts], [r.caused_by for r in k.records])"
   ```
   Expected `ErrorStmt decl [('p', '<unsupported>')] E-0001` and `unsupported { E-0001 ['ErrorStmt', 'Break', 'ErrorStmt'] [None, 'E-0001', 'E-0001']`. Otherwise STOP: the parser does not implement the amended recovery spec, and fixing it is plan 006's job.

No commit (nothing changed).

### Step 2: Rewrite the `sem.return_paths` and `sem.unreachable` paragraphs (the approved docs edit)

**Part A.** `docs/language-spec.md` currently says (directly under `### sem.return_paths`):

```text
A non-void function other than `main` should return on every path: the body's
last statement is a `return`, or an `if` with an `else` whose branches both
return on every path (recursively through blocks). Loops never count.
Violation is a warning, as in gcc's -Wreturn-type. `main` implicitly returns 0.
```

Replace exactly those four lines with these lines (keep the `### sem.return_paths` heading above and the blank line and the C example below unchanged):

```text
A non-void function other than `main` should return on every path. A
statement returns on every path if it is a `return`, a block in which ANY
statement returns on every path, or an `if` with an `else` whose two branches
both return on every path. Loops never count. Statements that follow a
statement which returns on every path, in the same block, can never run: the
first of them gets WRN-UNREACHABLE-CODE (`sem.unreachable`), not a missing
return. Violation is a warning, as in gcc's -Wreturn-type. `main` implicitly
returns 0.
```

Why: the advisor ruled (contract §6) that the standard rule applies: a statement list returns on every path if ANY statement in it does. The literal "last statement" wording made `return 1; f();` produce both WRN-UNREACHABLE-CODE and WRN-MISSING-RETURN. `returns()` in Step 3 implements the new wording, and the block walk treats a statement that returns on every path like a `return` for `sem.unreachable`.

**Part B.** The same file currently says (directly under `### sem.unreachable`):

```text
The first statement after a `return`, `break` or `continue` in the same block
produces one warning. This is a teaching warning that gcc does not emit.
```

Replace exactly those two lines with these lines (keep the `### sem.unreachable` heading above and the blank line and the C example below unchanged):

```text
The first statement after a `break`, a `continue`, or any statement that
returns on every path (a `return`, a block containing one, or an `if`/`else`
whose branches both return on every path; see `sem.return_paths`) in the same
block produces one warning. This is a teaching warning that gcc does not emit.
```

Why: the two paragraphs must agree. Once an `if`/`else` whose branches both return counts as returning on every path, the statement after it can never run, and the analyser's block walk warns there (Design decision 4). The paragraph still says one warning per block and still names gcc.

**Verify**:
- `grep -c "a block in which ANY" docs/language-spec.md` → `1`
- `grep -c "last statement is a" docs/language-spec.md` → `0`
- `grep -c 'returns on every path (a .return., a block containing one, or an .if./.else.' docs/language-spec.md` → `1`
- `grep -c 'The first statement after a .return., .break. or .continue.' docs/language-spec.md` → `0`
- `grep -c '^### sem.unreachable' docs/language-spec.md` → `1` and `grep -c '^### sem.return_paths' docs/language-spec.md` → `1`
- `grep -c '^A non-void function other than .main. should return on every path. A' docs/language-spec.md` → `1`
- `python -I tools/check_spec.py` → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`
- `git diff --stat` → only `docs/language-spec.md`, `1 file changed, 12 insertions(+), 6 deletions(-)`
- Commit `docs/language-spec.md` (both parts in one commit): `docs: sem.return_paths and sem.unreachable use the returns-on-every-path rule (plan 007 step 2)`.

### Step 3: The semantic analyser and its unit tests

Create `src/cea/semantic.py` with this exact content:

```python
"""Semantic analysis: the third compiler phase (PRD F1), plan 007.

``analyze(program, sink, stdio_include)`` walks the AST built by the parser once,
depth-first and left to right in source order (docs/error-recovery.md §6), and
reports every ``sem.*`` violation of docs/language-spec.md §4 through the
error sink. It never raises on a partial AST: ``ErrorStmt`` nodes are skipped,
``ErrorExpr`` nodes have the ``<error>`` type, and ``caused_by`` is set only by
rules R3-R8 (docs/error-recovery.md §7, as amended by plan 004).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cea import ast as A
from cea.diagnostics import ErrorSink
from cea.records import ErrorRecord, Position

# ---------------------------------------------------------------- types
# Scalar types are plain strings. Everything else is a small frozen dataclass.
INT, CHAR, FLOAT, DOUBLE, VOID = "int", "char", "float", "double", "void"
INTEGER_TYPES = frozenset({INT, CHAR})
FLOATING_TYPES = frozenset({FLOAT, DOUBLE})
ARITHMETIC_TYPES = INTEGER_TYPES | FLOATING_TYPES
STRING = "string literal"          # the type of a StringLit: no usable type (spec §3)


@dataclass(frozen=True)
class ArrayType:
    elem: str                      # int | char | float | double
    size: int | None               # None when the size expression was bad


@dataclass(frozen=True)
class FuncType:
    ret: str
    params: tuple[str, ...]


@dataclass(frozen=True)
class ErrorType:
    cause: str                     # id of the record that explains the unknown type


def type_name(t: object) -> str:
    """Human-readable type for messages and the ``found``/``expected`` fields."""
    if isinstance(t, ArrayType):
        return f"array {t.elem}[{t.size if t.size is not None else ''}]"
    if isinstance(t, FuncType):
        return f"function {sig_text('', t)}".replace("  ", " ")
    if isinstance(t, ErrorType):
        return "<error>"
    return str(t)


def sig_text(name: str, f: FuncType) -> str:
    params = ", ".join(f.params) if f.params else "void"
    return f"{f.ret} {name}({params})"


def is_arith(t: object) -> bool:
    return isinstance(t, str) and t in ARITHMETIC_TYPES


def is_err(t: object) -> bool:
    return isinstance(t, ErrorType)


def usual_arith(a: str, b: str) -> str:
    """Usual arithmetic conversions of spec §3 (char becomes int)."""
    if DOUBLE in (a, b):
        return DOUBLE
    if FLOAT in (a, b):
        return FLOAT
    return INT


# ---------------------------------------------------------------- symbols and scopes
@dataclass
class Symbol:
    name: str
    type: object
    pos: Position                  # name position of the (first) declaration
    kind: str                      # "var" | "param" | "global" | "func"
    decl: object = None            # VarDecl / Param / FunctionDecl (None for the printf builtin)
    read: bool = False
    defined: bool = False          # functions: a body has been seen
    err_mark: int = 0              # len(scope.error_nodes) when declared (R6)


@dataclass
class Scope:
    symbols: dict[str, Symbol] = field(default_factory=dict)
    order: list[Symbol] = field(default_factory=list)            # declaration order (WRN-UNUSED-VAR)
    error_nodes: list[tuple[str, set]] = field(default_factory=list)  # (error_id, idents) in source order (R6)


@dataclass
class FuncCtx:
    decl: A.FunctionDecl
    ret: str
    lost: list[tuple[str, str]] = field(default_factory=list)   # (name, error_id) for R5, source order
    first_error_stmt: str | None = None                         # R8


class Analyzer:
    def __init__(self, sink: ErrorSink, stdio_include: Position | None) -> None:
        self.sink = sink
        self.stdio = stdio_include
        self.printf_declared = False
        self.scopes: list[Scope] = [Scope()]           # [0] is file scope
        self.file_lost: list[tuple[str, str]] = []     # (name, error_id) at file scope, source order (R5)
        self.error_kinds: dict[str, str] = {}          # ErrorStmt.error_id -> kind_hint (R7)
        self.loop_stack: list[str | None] = []         # "loop" or an orphan error_id (R7)
        self.func: FuncCtx | None = None

    # ------------------------------------------------------------ reporting
    def report(self, code: str, pos: Position, *, found: str, end: Position | None = None,
               expected: tuple[str, ...] | list[str] = (), caused_by: str | None = None,
               **args: object) -> ErrorRecord:
        if end is None:
            end = Position(pos.line, pos.column + max(len(found), 1) - 1)
        return self.sink.report(code, pos.line, pos.column, found=found, expected=list(expected),
                                span_end=end, caused_by=caused_by, **args)

    # ------------------------------------------------------------ scope helpers
    def push(self) -> None:
        self.scopes.append(Scope())

    def pop(self) -> None:
        scope = self.scopes.pop()
        for sym in scope.order:                      # declaration order
            if sym.kind == "var" and not sym.read:
                self.report_unused(sym, scope)

    def report_unused(self, sym: Symbol, scope: Scope) -> None:
        decl = sym.decl
        cause = decl.error_id if isinstance(decl, A.VarDecl) and decl.error_id else None     # R4
        if cause is None:                                                                    # R6
            for eid, idents in scope.error_nodes[sym.err_mark:]:
                if sym.name in idents:
                    cause = eid
                    break
        self.report("WRN-UNUSED-VAR", sym.pos, found=sym.name, caused_by=cause, name=sym.name)

    def lookup(self, name: str) -> Symbol | None:
        for scope in reversed(self.scopes):
            if name in scope.symbols:
                return scope.symbols[name]
        return None

    def note_error_node(self, error_id: str, idents: set) -> None:
        """R6 bookkeeping: an ErrorStmt / broken declaration is visible to every open scope.

        R6 also names ErrorExpr, but an ErrorExpr only occurs inside a broken declaration
        (error-recovery §4.4 catch point (b)), whose idents_in_span already covers it.
        """
        for scope in self.scopes:
            scope.error_nodes.append((error_id, set(idents)))

    def note_lost(self, name: str, error_id: str) -> None:
        """R5 bookkeeping: a name that an error node failed to declare."""
        (self.func.lost if self.func else self.file_lost).append((name, error_id))

    def r5(self, name: str) -> str | None:
        """Nearest earlier ErrorStmt/broken declaration (current function body, then file scope) naming ``name``."""
        lists = ([self.func.lost] if self.func else []) + [self.file_lost]
        for lost in lists:
            for n, eid in reversed(lost):
                if n == name:
                    return eid
        return None

    def declare(self, name: str, typ: object, pos: Position, kind: str, decl: object) -> Symbol | None:
        scope = self.scopes[-1]
        prev = scope.symbols.get(name)
        if prev is not None:
            self.report("SEM-REDECLARED", pos, found=name, name=name, prev_line=prev.pos.line)
            return None
        sym = Symbol(name, typ, pos, kind, decl, err_mark=len(scope.error_nodes))
        scope.symbols[name] = sym
        scope.order.append(sym)
        return sym

    def ensure_printf(self, at: Position) -> None:
        """sem.builtins: printf exists only after an accepted #include <stdio.h>."""
        if self.printf_declared or self.stdio is None:
            return
        if (self.stdio.line, self.stdio.column) < (at.line, at.column):
            self.printf_declared = True
            file_scope = self.scopes[0]
            if "printf" not in file_scope.symbols:
                sym = Symbol("printf", FuncType(INT, ()), self.stdio, "func", None, defined=True)
                file_scope.symbols["printf"] = sym

    # ------------------------------------------------------------ program
    def program(self, prog: A.Program) -> None:
        for d in prog.decls:
            start = Position(d.span.start_line, d.span.start_col)
            self.ensure_printf(start)
            if isinstance(d, A.FunctionDecl):
                self.function(d)
            elif isinstance(d, A.VarDeclStmt):
                for vd in d.decls:
                    self.global_var(vd)
            elif isinstance(d, A.ErrorStmt):
                self.error_stmt(d)
        self.check_main(prog)

    def check_main(self, prog: A.Program) -> None:
        sym = self.scopes[0].symbols.get("main")
        ok = (sym is not None and isinstance(sym.type, FuncType) and sym.defined
              and sym.type.ret == INT and sym.type.params == ())
        if not ok:
            eof = eof_position(prog)
            self.report("SEM-MISSING-MAIN", eof, found="EOF", end=eof, caused_by=self.r5("main"))

    def error_stmt(self, s: A.ErrorStmt) -> None:
        """docs/error-recovery.md §6: do nothing except remember it for R5/R6/R7/R8."""
        self.error_kinds[s.error_id] = s.kind_hint
        for name, _type in s.declared_names:
            self.note_lost(name, s.error_id)
        if len(self.scopes) > 1:
            self.note_error_node(s.error_id, s.idents_in_span)
        if self.func is not None and self.func.first_error_stmt is None:
            self.func.first_error_stmt = s.error_id

    # ------------------------------------------------------------ declarations
    def var_type(self, vd: A.VarDecl) -> object:
        if vd.array_size is None:
            return vd.type_name
        size = vd.array_size.value if isinstance(vd.array_size, A.IntLit) else None
        return ArrayType(vd.type_name, size if size and size > 0 else None)

    def check_array_size(self, vd: A.VarDecl) -> None:
        size = vd.array_size
        if size is None:
            return
        if isinstance(size, A.IntLit) and size.value > 0:
            return
        cause = size.error_id if isinstance(size, A.ErrorExpr) else None                       # R3
        self.report("SEM-BAD-ARRAY-SIZE", self.start(size), found=unparse(size), end=self.end(size),
                    caused_by=cause)
        if not isinstance(size, A.ErrorExpr):
            self.expr(size)                       # still analysed: names inside are reads / undeclared

    def global_var(self, vd: A.VarDecl) -> None:
        typ = self.declare_var(vd, "global")
        self.check_array_size(vd)
        if vd.error_id:
            self.note_lost(vd.name, vd.error_id)
        if vd.init is None:
            return
        init = vd.init
        shape_ok = (isinstance(init, (A.IntLit, A.FloatLit, A.CharLit, A.StringLit))
                    or (isinstance(init, A.Unary) and init.op == "-" and not init.postfix
                        and isinstance(init.operand, (A.IntLit, A.FloatLit, A.CharLit))))
        if not shape_ok:
            bad = init.operand if isinstance(init, A.Unary) and init.op == "-" else init
            cause = bad.error_id if isinstance(bad, A.ErrorExpr) else None                       # R3
            self.report("SEM-NONCONST-GLOBAL-INIT", self.start(init), found=unparse(init), end=self.end(init),
                        caused_by=cause)
            if not isinstance(init, A.ErrorExpr):
                self.expr(init)
            return
        t = self.expr(init)
        self.convert(t, typ, init, at=vd.name_pos, ctx="init", name=vd.name)

    def declare_var(self, vd: A.VarDecl, kind: str) -> object:
        typ = self.var_type(vd)
        if vd.type_name == VOID:
            rec = self.report("SEM-VOID-VALUE", vd.name_pos, found=vd.name)
            typ = ErrorType(rec.id)
        # a void variable already has SEM-VOID-VALUE; it is not also tracked for WRN-UNUSED-VAR
        self.declare(vd.name, typ, vd.name_pos, "void" if vd.type_name == VOID else kind, vd)
        return typ

    def local_var(self, vd: A.VarDecl) -> None:
        typ = self.declare_var(vd, "var")
        self.check_array_size(vd)
        if vd.error_id:
            self.note_lost(vd.name, vd.error_id)
            self.note_error_node(vd.error_id, vd.idents_in_span)
        if vd.init is None:
            return
        t = self.expr(vd.init)
        if isinstance(typ, ArrayType):
            if not is_err(t):
                self.report("SEM-TYPE-MISMATCH", vd.name_pos, found=type_name(t), expected=[type_name(typ)],
                            end=self.name_end(vd.name_pos, vd.name))
            return
        self.convert(t, typ, vd.init, at=vd.name_pos, ctx="init", name=vd.name)

    def signature(self, f: A.FunctionDecl) -> FuncType:
        return FuncType(f.ret_type, tuple(p.type_name for p in f.params))

    def function(self, f: A.FunctionDecl) -> None:
        sig = self.signature(f)
        file_scope = self.scopes[0]
        prev = file_scope.symbols.get(f.name)
        if f.error_id:
            self.note_lost(f.name, f.error_id)
        if prev is None:
            sym = Symbol(f.name, sig, f.name_pos, "func", f, defined=f.body is not None)
            file_scope.symbols[f.name] = sym
            file_scope.order.append(sym)
        elif not isinstance(prev.type, FuncType) or (prev.decl is None and f.name == "printf"):
            self.report("SEM-REDECLARED", f.name_pos, found=f.name, name=f.name, prev_line=prev.pos.line)
        elif prev.type != sig:
            self.report("SEM-CONFLICTING-TYPES", f.name_pos, found=f.name, name=f.name,
                        prev_sig=sig_text(f.name, prev.type), sig=sig_text(f.name, sig))
            prev.defined = prev.defined or f.body is not None
        elif prev.defined and f.body is not None:
            self.report("SEM-REDECLARED", f.name_pos, found=f.name, name=f.name, prev_line=prev.pos.line)
        else:
            prev.defined = prev.defined or f.body is not None
        # parameters live in the body's outermost scope (sem.unique_in_scope)
        self.push()
        for p in f.params:
            ptype: object = p.type_name
            if p.type_name == VOID:
                ptype = ErrorType(self.report("SEM-VOID-VALUE", p.name_pos, found=p.name).id)
            self.declare(p.name, ptype, p.name_pos, "param", p)
        if f.body is None:
            self.scopes.pop()                  # prototype: no unused check
            return
        self.func = FuncCtx(f, f.ret_type)
        self.stmts(f.body.stmts)               # the body Block shares the parameter scope
        self.pop()                             # WRN-UNUSED-VAR for the outermost scope
        if f.ret_type != VOID and f.name != "main" and not returns(f.body):
            cause = self.func.first_error_stmt or f.body.closed_by_repair                    # R8
            self.report("WRN-MISSING-RETURN", f.name_pos, found=f.name, caused_by=cause, name=f.name)
        self.func = None

    # ------------------------------------------------------------ statements
    def stmts(self, stmts: list) -> None:
        terminated = warned = False
        for s in stmts:
            if terminated and not warned:
                warned = True                  # one warning per block, at the first statement after
                if not isinstance(s, A.ErrorStmt):
                    self.report("WRN-UNREACHABLE-CODE", self.start(s), found=first_token(s))
            self.stmt(s)
            if isinstance(s, (A.Break, A.Continue)) or returns(s):
                terminated = True          # a return, break or continue, or anything that returns on every path

    def stmt(self, s: object) -> None:
        if isinstance(s, A.VarDeclStmt):
            for vd in s.decls:
                self.local_var(vd)
        elif isinstance(s, A.Block):
            pushed_orphan = s.orphan_of is not None and self.error_kinds.get(s.orphan_of) in ("while", "for", "unsupported")
            if pushed_orphan:
                self.loop_stack.append(s.orphan_of)
            self.push()
            self.stmts(s.stmts)
            self.pop()
            if pushed_orphan:
                self.loop_stack.pop()
        elif isinstance(s, A.ExprStmt):
            self.expr(s.expr)
        elif isinstance(s, A.If):
            self.condition(s.cond)
            self.stmt(s.then)
            if s.els is not None:
                self.stmt(s.els)
        elif isinstance(s, A.While):
            self.condition(s.cond)
            self.loop_body(s.body)
        elif isinstance(s, A.For):
            self.push()                        # the for-init scope (C99 6.8.5p5)
            if isinstance(s.init, A.VarDeclStmt):
                for vd in s.init.decls:
                    self.local_var(vd)
            elif s.init is not None:
                self.expr(s.init)
            if s.cond is not None:
                self.condition(s.cond)
            if s.step is not None:
                self.expr(s.step)
            self.loop_body(s.body)
            self.pop()
        elif isinstance(s, A.Return):
            self.return_stmt(s)
        elif isinstance(s, (A.Break, A.Continue)):
            self.loop_control(s)
        elif isinstance(s, A.ErrorStmt):
            self.error_stmt(s)
        # EmptyStmt: nothing

    def loop_body(self, body: object) -> None:
        self.loop_stack.append("loop")
        self.stmt(body)
        self.loop_stack.pop()

    def loop_control(self, s: object) -> None:
        if "loop" in self.loop_stack:
            return
        word = "break" if isinstance(s, A.Break) else "continue"
        cause = self.loop_stack[-1] if self.loop_stack else None                                # R7
        self.report("SEM-BREAK-OUTSIDE-LOOP", self.start(s), found=word, caused_by=cause)

    def condition(self, cond: object) -> None:
        t = self.expr(cond)
        self.require_value(t, cond, expected="an arithmetic value")
        if isinstance(cond, A.Assign) and cond.op == "=":
            self.report("WRN-ASSIGN-IN-CONDITION", cond.op_pos, found="=", end=cond.op_pos)

    def return_stmt(self, s: A.Return) -> None:
        fn = self.func
        at = self.start(s)
        name = fn.decl.name
        if s.value is None:
            if fn.ret != VOID:
                self.report("SEM-RETURN-TYPE", at, found="nothing", end=Position(at.line, at.column + 5),
                            expected=[fn.ret], name=name)
            return
        t = self.expr(s.value)
        if fn.ret == VOID:
            if not is_err(t):
                self.report("SEM-RETURN-TYPE", at, found=type_name(t), end=Position(at.line, at.column + 5),
                            expected=[VOID], name=name)
            return
        self.convert(t, fn.ret, s.value, at=at, ctx="return", name=name)

    # ------------------------------------------------------------ conversions
    def require_value(self, t: object, node: object, expected: str, integer: bool = False,
                      at: Position | None = None, op: str = "") -> object:
        """Check that an operand is a usable (arithmetic / integer) value. Returns the type to continue with."""
        if is_err(t):
            return t
        if t == VOID:
            return ErrorType(self.void_value(node).id)
        if not is_arith(t) or (integer and t not in INTEGER_TYPES):
            loc = at or self.start(node)
            end = op_end(at, op) if at else self.end(node)
            rec = self.report("SEM-TYPE-MISMATCH", loc, found=type_name(t), expected=[expected], end=end)
            return ErrorType(rec.id)
        return t

    def void_value(self, node: object) -> ErrorRecord:
        if isinstance(node, A.Call) and isinstance(node.callee, A.Name):
            return self.report("SEM-VOID-VALUE", self.start(node.callee), found=node.callee.name)
        return self.report("SEM-VOID-VALUE", self.start(node), found=unparse(node), end=self.end(node))

    def convert(self, t: object, target: object, node: object, *, at: Position, ctx: str, name: str,
                index: int = 0) -> None:
        """Assignment / initialisation / argument / return conversion (spec §3)."""
        if is_err(t) or is_err(target):
            return
        if t == VOID:
            self.void_value(node)
            return
        if not is_arith(t):
            if ctx == "arg":
                self.report("SEM-ARG-TYPE", at, found=type_name(t), expected=[type_name(target)],
                            end=self.name_end(at, name), name=name, index=index)
            elif ctx == "return":
                self.report("SEM-RETURN-TYPE", at, found=type_name(t), expected=[type_name(target)],
                            end=Position(at.line, at.column + 5), name=name)
            else:
                end = self.name_end(at, name) if ctx == "init" else at
                self.report("SEM-TYPE-MISMATCH", at, found=type_name(t), expected=[type_name(target)], end=end)
            return
        if t in FLOATING_TYPES and target in INTEGER_TYPES:
            end = (self.name_end(at, name) if ctx in ("init", "arg") else
                   Position(at.line, at.column + 5) if ctx == "return" else at)
            self.report("WRN-IMPLICIT-NARROWING", at, found=t, expected=[target], end=end)

    # ------------------------------------------------------------ expressions
    def expr(self, e: object, *, write: bool = False) -> object:
        """Analyse an expression and return its type. ``write`` marks a plain '=' target (not a read)."""
        if isinstance(e, A.IntLit):
            return INT
        if isinstance(e, A.FloatLit):
            return DOUBLE
        if isinstance(e, A.CharLit):
            return CHAR
        if isinstance(e, A.StringLit):
            return STRING
        if isinstance(e, A.ErrorExpr):
            return ErrorType(e.error_id)
        if isinstance(e, A.Name):
            return self.name(e, write=write)
        if isinstance(e, A.Index):
            return self.index(e, write=write)
        if isinstance(e, A.Call):
            return self.call(e)
        if isinstance(e, A.Assign):
            return self.assign(e)
        if isinstance(e, A.Unary):
            return self.unary(e)
        if isinstance(e, A.Binary):
            return self.binary(e)
        raise TypeError(f"unknown expression node {e!r}")

    def name(self, e: A.Name, *, write: bool = False) -> object:
        sym = self.lookup(e.name)
        if sym is None:
            rec = self.report("SEM-UNDECLARED-VAR", self.start(e), found=e.name, caused_by=self.r5(e.name),
                              name=e.name)
            return ErrorType(rec.id)
        if not write:
            sym.read = True
        return sym.type

    def index(self, e: A.Index, *, write: bool = False) -> object:
        base_t = self.expr(e.base, write=write)
        result: object
        if is_err(base_t):
            result = base_t
        elif isinstance(base_t, ArrayType):
            result = base_t.elem
        else:
            label = e.base.name if isinstance(e.base, A.Name) else unparse(e.base)
            rec = self.report("SEM-NOT-ARRAY", self.start(e.base), found=label, end=self.end(e.base), name=label)
            result = ErrorType(rec.id)
        idx_t = self.expr(e.index)
        if not is_err(idx_t):
            if idx_t == VOID:
                self.void_value(e.index)
            elif idx_t not in INTEGER_TYPES:
                self.report("SEM-INDEX-NOT-INT", self.start(e.index), found=type_name(idx_t), end=self.end(e.index))
        return result

    def call(self, e: A.Call) -> object:
        callee = e.callee
        if not isinstance(callee, A.Name):
            t = self.expr(callee)
            for a in e.args:
                self.expr(a)
            if is_err(t):
                return t
            label = unparse(callee)
            return ErrorType(self.report("SEM-NOT-CALLABLE", self.start(callee), found=label, end=self.end(callee),
                                         name=label).id)
        name = callee.name
        at = self.start(callee)
        if name == "printf":
            self.ensure_printf(at)
        sym = self.lookup(name)
        if sym is None:
            rec = self.report("SEM-UNDECLARED-FUNC", at, found=name, caused_by=self.r5(name), name=name)
            for a in e.args:
                self.expr(a)
            return ErrorType(rec.id)
        if not isinstance(sym.type, FuncType):
            sym.read = True
            if is_err(sym.type):
                for a in e.args:
                    self.expr(a)
                return sym.type
            rec = self.report("SEM-NOT-CALLABLE", at, found=name, name=name)
            for a in e.args:
                self.expr(a)
            return ErrorType(rec.id)
        ftype: FuncType = sym.type
        if sym.decl is None and name == "printf":                  # the builtin
            first = e.args[0] if e.args else None
            if not isinstance(first, A.StringLit):
                cause = first.error_id if isinstance(first, A.ErrorExpr) else None                   # R3
                self.report("SEM-PRINTF-FORMAT", at, found=name, caused_by=cause)
            types = [self.expr(a) for a in e.args]
            for i, (a, t) in enumerate(zip(e.args, types), start=1):
                if i == 1:
                    continue                    # the format: checked above by shape (SEM-PRINTF-FORMAT)
                if t == VOID:
                    self.void_value(a)
                elif not is_err(t) and not is_arith(t):
                    self.report("SEM-ARG-TYPE", at, found=type_name(t), expected=["an arithmetic value"],
                                name=name, index=i)
            return INT
        if len(e.args) != len(ftype.params):
            self.report("SEM-ARG-COUNT", at, found=str(len(e.args)), expected=[str(len(ftype.params))],
                        end=self.name_end(at, name), name=name)
            for a in e.args:
                self.expr(a)
            return ftype.ret
        types = [self.expr(a) for a in e.args]
        for i, (a, t, p) in enumerate(zip(e.args, types, ftype.params), start=1):
            self.convert(t, p, a, at=at, ctx="arg", name=name, index=i)
        return ftype.ret

    def assign(self, e: A.Assign) -> object:
        plain = e.op == "="
        tt = self.expr(e.target, write=plain)              # '=' writes; compound ops read and write (plan 004)
        vt = self.expr(e.value)
        if is_err(tt):
            return tt
        if not is_arith(tt):                               # array name, function name, void...
            rec = self.report("SEM-TYPE-MISMATCH", e.op_pos, found=type_name(tt),
                              expected=["a variable or array element"], end=op_end(e.op_pos, e.op))
            return ErrorType(rec.id)
        if plain:
            self.convert(vt, tt, e.value, at=e.op_pos, ctx="assign", name="")
            return tt
        integer = e.op == "%="
        vt = self.require_value(vt, e.value, "an integer" if integer else "an arithmetic value", integer=integer,
                                at=e.op_pos, op=e.op)
        if integer and tt not in INTEGER_TYPES:
            self.report("SEM-TYPE-MISMATCH", e.op_pos, found=tt, expected=["an integer"], end=op_end(e.op_pos, e.op))
            return tt
        if is_err(vt):
            return tt
        result = usual_arith(tt, vt)
        if result in FLOATING_TYPES and tt in INTEGER_TYPES:
            self.report("WRN-IMPLICIT-NARROWING", e.op_pos, found=result, expected=[tt], end=op_end(e.op_pos, e.op))
        return tt

    def unary(self, e: A.Unary) -> object:
        if e.op in ("++", "--"):
            t = self.expr(e.operand)                       # read and write (plan 004)
            op_at = Position(e.span.end_line, e.span.end_col - 1) if e.postfix else self.start(e)
            return self.require_value(t, e.operand, "an arithmetic value", at=op_at, op=e.op)
        t = self.expr(e.operand)
        t = self.require_value(t, e.operand, "an arithmetic value", at=self.start(e), op=e.op)
        if is_err(t):
            return t
        if e.op == "!":
            return INT
        return INT if t == CHAR else t

    def binary(self, e: A.Binary) -> object:
        lt = self.expr(e.left)
        rt = self.expr(e.right)
        integer = e.op == "%"
        want = "an integer" if integer else "an arithmetic value"
        lt = self.require_value(lt, e.left, want, integer=integer, at=e.op_pos, op=e.op)
        if is_err(lt):
            return lt
        rt = self.require_value(rt, e.right, want, integer=integer, at=e.op_pos, op=e.op)
        if is_err(rt):
            return rt
        if e.op in ("+", "-", "*", "/"):
            return usual_arith(lt, rt)
        return INT                                        # %, comparisons, equality, && and ||

    # ------------------------------------------------------------ positions
    @staticmethod
    def start(node: object) -> Position:
        return Position(node.span.start_line, node.span.start_col)

    @staticmethod
    def end(node: object) -> Position:
        return Position(node.span.end_line, node.span.end_col)

    @staticmethod
    def name_end(at: Position, name: str) -> Position:
        return Position(at.line, at.column + max(len(name), 1) - 1)


# ---------------------------------------------------------------- pure helpers
def eof_position(prog: A.Program) -> Position:
    """The EOF token's position (docs/error-recovery.md §8); contract §4: Program.span ends at it."""
    return Position(prog.span.end_line, prog.span.end_col)


def op_end(at: Position, op: str) -> Position:
    """Inclusive end of an operator token that starts at ``at``."""
    return Position(at.line, at.column + max(len(op), 1) - 1)


def returns(s: object) -> bool:
    """sem.return_paths: does ``s`` return on every path?

    A ``return`` does; a block does if ANY of its statements does (what follows is
    unreachable, sem.unreachable); an ``if`` does if it has an ``else`` and both
    branches do. Loops never count.
    """
    if isinstance(s, A.Return):
        return True
    if isinstance(s, A.Block):
        return any(returns(x) for x in s.stmts)
    if isinstance(s, A.If):
        return s.els is not None and returns(s.then) and returns(s.els)
    return False                                          # loops never count (spec)


def unparse(e: object) -> str:
    """Source-like text of an expression, for ``found`` fields."""
    if isinstance(e, A.IntLit):
        return str(e.value)
    if isinstance(e, A.FloatLit):
        return repr(e.value)
    if isinstance(e, A.CharLit):
        return repr(e.value)
    if isinstance(e, A.StringLit):
        return '"' + e.value.replace("\n", "\\n") + '"'
    if isinstance(e, A.Name):
        return e.name
    if isinstance(e, A.ErrorExpr):
        return "<error>"
    if isinstance(e, A.Unary):
        return f"{unparse(e.operand)}{e.op}" if e.postfix else f"{e.op}{unparse(e.operand)}"
    if isinstance(e, A.Binary):
        return f"{unparse(e.left)} {e.op} {unparse(e.right)}"
    if isinstance(e, A.Assign):
        return f"{unparse(e.target)} {e.op} {unparse(e.value)}"
    if isinstance(e, A.Call):
        return f"{unparse(e.callee)}({', '.join(unparse(a) for a in e.args)})"
    if isinstance(e, A.Index):
        return f"{unparse(e.base)}[{unparse(e.index)}]"
    return "?"


def first_token(s: object) -> str:
    """Text of the first token of a statement (``found`` of WRN-UNREACHABLE-CODE)."""
    words = {A.Return: "return", A.Break: "break", A.Continue: "continue", A.If: "if", A.While: "while",
             A.For: "for", A.Block: "{", A.EmptyStmt: ";"}
    for cls, w in words.items():
        if isinstance(s, cls):
            return w
    if isinstance(s, A.VarDeclStmt):
        return s.decls[0].type_name
    if isinstance(s, A.ExprStmt):
        e = s.expr
        while True:
            if isinstance(e, A.Assign):
                e = e.target
            elif isinstance(e, A.Binary):
                e = e.left
            elif isinstance(e, A.Call):
                e = e.callee
            elif isinstance(e, A.Index):
                e = e.base
            elif isinstance(e, A.Unary):
                if not e.postfix:
                    return e.op
                e = e.operand
            else:
                return unparse(e)
    return "?"


def analyze(program: A.Program, sink: ErrorSink, stdio_include: Position | None) -> None:
    """Run the semantic phase on ``program`` and report through ``sink``. Never raises on a partial AST."""
    Analyzer(sink, stdio_include).program(program)
```

Create `tests/unit/test_semantic.py` with this exact content (it calls `lex`, `parse` and `analyze` directly, because `cea.pipeline` must not exist yet):

```python
"""Unit tests for the semantic phase (plan 007).

One table row per SEM/WRN code (the catalog's example trigger), then scopes,
reads and writes, types, control flow, and the caused_by rules R3-R8.
"""
import pytest

from cea import ast as A
from cea.catalog import load_catalog
from cea.diagnostics import ErrorSink
from cea.lexer import lex
from cea.parser import parse
from cea.records import Position
from cea.semantic import analyze


def records(src):
    """All records of the three phases (the same steps as cea.pipeline.compile_source)."""
    sink = ErrorSink(src)
    lr = lex(src, sink)
    analyze(parse(lr, sink), sink, lr.stdio_include)
    return sink.records


def table(src):
    return [(r.code, r.line, r.column) for r in records(src)]


MAIN0 = "int main(void) {\n    return 0;\n}\n"

# (code, source, full expected [(code, line, col)] list, message of the first record)
# -- the catalog's "Example trigger" placed in a minimal program
CODE_CASES = [
    ("SEM-UNDECLARED-VAR", "int main(void) {\n    y = 3;\n    return 0;\n}\n",
     [("SEM-UNDECLARED-VAR", 2, 5)],
     "Variable 'y' is used before it is declared"),
    ("SEM-UNDECLARED-FUNC", "int main(void) {\n    foo(1);\n    return 0;\n}\n",
     [("SEM-UNDECLARED-FUNC", 2, 5)],
     "Function 'foo' is not declared before this call"),
    ("SEM-REDECLARED", "int main(void) {\n    int x;\n    int x;\n    x = 1;\n    return x;\n}\n",
     [("SEM-REDECLARED", 3, 9)],
     "'x' is already declared in this scope (line 2)"),
    ("SEM-CONFLICTING-TYPES", "int f(int a);\nfloat f(int a) {\n    return 1.0;\n}\n" + MAIN0,
     [("SEM-CONFLICTING-TYPES", 2, 7)],
     "Declarations of 'f' disagree: int f(int) vs float f(int)"),
    ("SEM-TYPE-MISMATCH", "int main(void) {\n    int x = \"hi\";\n    return x;\n}\n",
     [("SEM-TYPE-MISMATCH", 2, 9)],
     'Cannot use string literal where int is required'),
    ("SEM-TYPE-MISMATCH", "int main(void) {\n    int r = 7.5 % 2;\n    return r;\n}\n",
     [("SEM-TYPE-MISMATCH", 2, 17)],
     'Cannot use double where an integer is required'),
    ("SEM-VOID-VALUE", "void log_it(void) {\n}\nint main(void) {\n    int x = log_it();\n    return x;\n}\n",
     [("SEM-VOID-VALUE", 4, 13)],
     'A void value cannot be stored or used in an expression'),
    ("SEM-NOT-CALLABLE", "int main(void) {\n    int x = 0;\n    x(1);\n    return x;\n}\n",
     [("SEM-NOT-CALLABLE", 3, 5)],
     "'x' is not a function"),
    ("SEM-ARG-COUNT", "int add(int a, int b) {\n    return a + b;\n}\nint main(void) {\n    return add(1);\n}\n",
     [("SEM-ARG-COUNT", 5, 12)],
     "'add' expects 2 argument(s) but got 1"),
    ("SEM-ARG-TYPE", "int add(int a, int b) {\n    return a + b;\n}\nint main(void) {\n    return add(1, \"two\");\n}\n",
     [("SEM-ARG-TYPE", 5, 12)],
     "Argument 2 of 'add' must be int but is string literal"),
    ("SEM-RETURN-TYPE", "void f(void) {\n    return 5;\n}\n" + MAIN0,
     [("SEM-RETURN-TYPE", 2, 5)],
     "Function 'f' returns void but this returns int"),
    ("SEM-RETURN-TYPE", "int g(void) {\n    return;\n}\n" + MAIN0,
     [("SEM-RETURN-TYPE", 2, 5)],
     "Function 'g' returns int but this returns nothing"),
    ("SEM-NOT-ARRAY", "int main(void) {\n    int x = 1;\n    x[0] = 1;\n    return x;\n}\n",
     [("SEM-NOT-ARRAY", 3, 5)],
     "'x' is not an array and cannot be indexed"),
    ("SEM-INDEX-NOT-INT", "int main(void) {\n    int a[3];\n    a[1.5] = 2;\n    return a[0];\n}\n",
     [("SEM-INDEX-NOT-INT", 3, 7)],
     'Array index must be an integer but has type double'),
    ("SEM-BAD-ARRAY-SIZE", "int main(void) {\n    int n = 3;\n    int a[n];\n    a[0] = n;\n    return a[0];\n}\n",
     [("SEM-BAD-ARRAY-SIZE", 3, 11)],
     'Array size must be an integer literal greater than 0'),
    ("SEM-BREAK-OUTSIDE-LOOP", "int main(void) {\n    if (1) {\n        break;\n    }\n    return 0;\n}\n",
     [("SEM-BREAK-OUTSIDE-LOOP", 3, 9)],
     "'break' can only be used inside a loop"),
    ("SEM-NONCONST-GLOBAL-INIT", "int x = 4;\nint y = x + 1;\nint main(void) {\n    return y;\n}\n",
     [("SEM-NONCONST-GLOBAL-INIT", 2, 9)],
     'A global variable must be initialised with a literal'),
    ("SEM-PRINTF-FORMAT", "#include <stdio.h>\nint main(void) {\n    int x = 1;\n    printf(x);\n    return 0;\n}\n",
     [("SEM-PRINTF-FORMAT", 4, 5)],
     'The first argument of printf must be a string literal'),
    ("SEM-MISSING-MAIN", "void g(void) {\n}\n",
     [("SEM-MISSING-MAIN", 2, 2)],
     "Program has no 'int main()' function"),
    ("WRN-UNUSED-VAR", "int main(void) {\n    int t = 1;\n    return 0;\n}\n",
     [("WRN-UNUSED-VAR", 2, 9)],
     "Variable 't' is declared but never used"),
    ("WRN-UNREACHABLE-CODE", "int main(void) {\n    return 0;\n    return 1;\n}\n",
     [("WRN-UNREACHABLE-CODE", 3, 5)],
     'This statement can never run'),
    ("WRN-IMPLICIT-NARROWING", "int main(void) {\n    int n = 2.5;\n    return n;\n}\n",
     [("WRN-IMPLICIT-NARROWING", 2, 9)],
     'double value converted to int; the fractional part is lost'),
    ("WRN-MISSING-RETURN", "int f(int b) {\n    if (b) {\n        return 1;\n    }\n}\nint main(void) {\n    return f(1);\n}\n",
     [("WRN-MISSING-RETURN", 1, 5)],
     "Function 'f' may end without returning a value"),
    ("WRN-ASSIGN-IN-CONDITION", "int main(void) {\n    int x = 0;\n    if (x = 5) {\n        x = 1;\n    }\n    return x;\n}\n",
     [("WRN-ASSIGN-IN-CONDITION", 3, 11)],
     "Assignment used as a condition; did you mean '=='?"),
]


@pytest.mark.parametrize("code,src,expected,message", CODE_CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CODE_CASES)])
def test_catalog_example_trigger(code, src, expected, message):
    recs = records(src)
    assert [(r.code, r.line, r.column) for r in recs] == expected
    rec = recs[0]
    entry = load_catalog()[code]
    assert (rec.phase, rec.severity, rec.rule_ref) == ("semantic", entry.severity, entry.rule_ref)
    assert rec.caused_by is None and rec.root_id == rec.id
    assert rec.message == message


def test_every_sem_and_wrn_code_has_a_table_row():
    codes = {c for c in load_catalog() if c.startswith(("SEM-", "WRN-"))}
    assert codes == {c[0] for c in CODE_CASES}


# ---------------------------------------------------------------- printf builtin
def test_printf_without_include_is_undeclared():
    assert table("int main(void) {\n    printf(\"hi\");\n    return 0;\n}\n") == [("SEM-UNDECLARED-FUNC", 2, 5)]


def test_printf_include_after_first_use_is_undeclared():
    src = "int main(void) {\n    printf(\"a\");\n    return 0;\n}\n#include <stdio.h>\nint f(void) {\n    printf(\"b\");\n    return 1;\n}\n"
    assert table(src) == [("SEM-UNDECLARED-FUNC", 2, 5)]


def test_printf_redeclared_after_include():
    src = "#include <stdio.h>\nint printf(int x);\n" + MAIN0
    assert table(src) == [("SEM-REDECLARED", 2, 5)]


def test_printf_extra_arguments_must_be_arithmetic():
    src = "#include <stdio.h>\nint main(void) {\n    printf(\"%d %s\", 1, \"x\");\n    return 0;\n}\n"
    assert table(src) == [("SEM-ARG-TYPE", 3, 5)]


# ---------------------------------------------------------------- scopes
def test_shadowing_an_outer_scope_is_allowed():
    src = "int x = 1;\nint main(void) {\n    int x = 2;\n    {\n        int x = 3;\n        x = x + 1;\n    }\n    return x;\n}\n"
    assert table(src) == []


def test_parameters_share_the_body_scope():
    assert table("int f(int a) {\n    int a = 1;\n    return a;\n}\n" + MAIN0) == [("SEM-REDECLARED", 2, 9)]


def test_for_init_has_its_own_scope():
    src = ("int main(void) {\n    int s = 0;\n    for (int i = 0; i < 3; i++) {\n        int i = 5;\n        s += i;\n    }\n"
           "    return i;\n}\n")
    assert table(src) == [("SEM-UNDECLARED-VAR", 7, 12)]


def test_function_defined_twice_is_redeclared():
    assert table("int f(void) {\n    return 1;\n}\nint f(void) {\n    return 2;\n}\n" + MAIN0) == [("SEM-REDECLARED", 4, 5)]


def test_prototype_then_definition_then_recursion_is_clean():
    src = "int f(int n);\nint f(int n) {\n    if (n < 1) {\n        return 0;\n    }\n    return f(n - 1);\n}\n" + MAIN0
    assert table(src) == []


# ---------------------------------------------------------------- reads and writes (sem.unused_declaration, plan 004)
@pytest.mark.parametrize("stmt,unused", [
    ("s = 1;", True), ("s += 1;", False), ("s -= 1;", False), ("s *= 2;", False), ("s /= 2;", False),
    ("s %= 2;", False), ("s++;", False), ("++s;", False), ("s--;", False), ("--s;", False), ("s = s;", False),
])
def test_compound_assignment_and_increment_are_reads(stmt, unused):
    src = f"int main(void) {{\n    int s = 0;\n    {stmt}\n    return 0;\n}}\n"
    assert table(src) == ([("WRN-UNUSED-VAR", 2, 9)] if unused else [])


def test_array_element_target_writes_the_array_and_reads_the_index():
    src = "int main(void) {\n    int a[2];\n    int i = 1;\n    a[i] = 3;\n    return 0;\n}\n"
    assert table(src) == [("WRN-UNUSED-VAR", 2, 9)]


def test_unused_warnings_come_at_scope_exit_in_declaration_order():
    src = "int main(void) {\n    int a = 1;\n    {\n        int b = 2;\n    }\n    int c = 3;\n    return 0;\n}\n"
    assert table(src) == [("WRN-UNUSED-VAR", 4, 13), ("WRN-UNUSED-VAR", 2, 9), ("WRN-UNUSED-VAR", 6, 9)]


def test_parameters_and_globals_are_exempt():
    assert table("int g = 1;\nint f(int a) {\n    return 0;\n}\n" + MAIN0) == []


# ---------------------------------------------------------------- types
@pytest.mark.parametrize("decl,expected", [
    ("int n = 2.5;", [("WRN-IMPLICIT-NARROWING", 2, 9)]),
    ("char c = 2.5;", [("WRN-IMPLICIT-NARROWING", 2, 10)]),
    ("float f = 2.5;", []),
    ("char c = 300;", []),
    ("double d = 'a';", []),
])
def test_conversions(decl, expected):
    name_used = decl.split()[1]
    src = f"int main(void) {{\n    {decl}\n    return {name_used};\n}}\n"
    got = [t for t in table(src) if t[0] != "WRN-IMPLICIT-NARROWING" or t[1] == 2]
    assert [t for t in got if t[1] == 2] == expected


def test_narrowing_on_assignment_compound_return_and_argument():
    src = ("int h(int v) {\n    return v;\n}\nint k(void) {\n    return 1.5;\n}\nint main(void) {\n    int x = 0;\n"
           "    x = 1.5;\n    x += 0.5;\n    x = h(2.5);\n    return x;\n}\n")
    assert table(src) == [("WRN-IMPLICIT-NARROWING", 5, 5), ("WRN-IMPLICIT-NARROWING", 9, 7),
                          ("WRN-IMPLICIT-NARROWING", 10, 7), ("WRN-IMPLICIT-NARROWING", 11, 9)]


def test_string_condition_is_a_type_mismatch():
    assert table("int main(void) {\n    if (\"yes\") {\n        return 1;\n    }\n    return 0;\n}\n") == [("SEM-TYPE-MISMATCH", 2, 9)]


def test_void_variable_and_void_operand():
    src = "void v(void) {\n}\nint main(void) {\n    void x;\n    int y = v() + 1;\n    return y + x;\n}\n"
    assert table(src) == [("SEM-VOID-VALUE", 4, 10), ("SEM-VOID-VALUE", 5, 13)]


def test_unused_void_variable_gets_only_void_value():
    assert table("int main(void) {\n    void x;\n    return 0;\n}\n") == [("SEM-VOID-VALUE", 2, 10)]


def test_array_name_is_not_a_value():
    src = "int main(void) {\n    int a[2];\n    int b = 0;\n    a = 1;\n    b = a + 1;\n    return b;\n}\n"
    assert [t[0] for t in table(src)] == ["SEM-TYPE-MISMATCH", "SEM-TYPE-MISMATCH"]


def test_error_type_absorbs_type_checks():
    src = "int main(void) {\n    int x = 0;\n    x = nope + 1.5;\n    x = nope[2];\n    return nope(x);\n}\n"
    assert [t[0] for t in table(src)] == ["SEM-UNDECLARED-VAR", "SEM-UNDECLARED-VAR", "SEM-UNDECLARED-FUNC"]


# ---------------------------------------------------------------- control flow
def test_unreachable_is_reported_once_per_block():
    src = "int main(void) {\n    return 0;\n    return 1;\n    return 2;\n}\n"
    assert table(src) == [("WRN-UNREACHABLE-CODE", 3, 5)]


@pytest.mark.parametrize("body,warn", [
    ("    if (b) {\n        return 1;\n    } else {\n        return 2;\n    }\n", False),
    ("    while (b) {\n        return 1;\n    }\n", True),
    ("    {\n        return 1;\n    }\n", False),
    ("    if (b) {\n        return 1;\n    } else if (b > 1) {\n        return 2;\n    }\n", True),
])
def test_return_paths(body, warn):
    src = "int f(int b) {\n" + body + "}\n" + MAIN0
    assert table(src) == ([("WRN-MISSING-RETURN", 1, 5)] if warn else [])


def test_code_after_a_return_is_unreachable_not_a_missing_return():
    src = "void f(void) {\n}\nint g(void) {\n    return 1;\n    f();\n}\n" + MAIN0
    assert table(src) == [("WRN-UNREACHABLE-CODE", 5, 5)]


def test_statement_after_an_if_else_that_returns_is_unreachable():
    src = ("int f(int b) {\n    if (b) {\n        return 1;\n    } else {\n        return 2;\n    }\n    b = 3;\n}\n"
           + MAIN0)
    assert table(src) == [("WRN-UNREACHABLE-CODE", 7, 5)]


def test_main_and_void_functions_need_no_return():
    assert table("void p(void) {\n}\nint main(void) {\n    p();\n}\n") == []


def test_break_inside_nested_loop_block_is_fine():
    assert table("int main(void) {\n    while (1) {\n        if (1) {\n            break;\n        }\n    }\n    return 0;\n}\n") == []


# ---------------------------------------------------------------- caused_by rules R3-R8 on real source
def test_r3_global_initializer_error_expr():
    recs = records("int g = ;\n" + MAIN0)
    assert [(r.code, r.caused_by) for r in recs] == [("SYN-EXPECTED-EXPRESSION", None),
                                                    ("SEM-NONCONST-GLOBAL-INIT", "E-0001")]


def test_r3_array_size_error_expr():
    recs = records("int main(void) {\n    int a[];\n    return 0;\n}\n")
    assert [(r.code, r.caused_by) for r in recs][:2] == [("SYN-EXPECTED-EXPRESSION", None),
                                                        ("SEM-BAD-ARRAY-SIZE", "E-0001")]


def test_r5_missing_main_after_broken_main_header():
    recs = records("int main(void {\n    return 0;\n}\n")
    assert [(r.code, r.caused_by) for r in recs] == [(recs[0].code, None), ("SEM-MISSING-MAIN", "E-0001")]
    assert recs[0].phase == "syntax"


# ---------------------------------------------------------------- caused_by rules on hand-built ASTs (parser-independent)
def S(l1, c1, l2=None, c2=None):
    return A.Span(l1, c1, l2 or l1, c2 or c1)


def _sink_with_syntax_records(n):
    sink = ErrorSink("x\n" * 10)
    recs = [sink.report("SYN-EXPECTED-EXPRESSION", 2, 5, found=";", rule_ref="primary") for _ in range(n)]
    return sink, recs


def test_r3_printf_first_argument_error_expr():
    sink, (syn,) = _sink_with_syntax_records(1)
    call = A.ExprStmt(A.Call(A.Name("printf", S(3, 5, 3, 10)), [A.ErrorExpr(S(3, 12), syn.id)], S(3, 5, 3, 13)),
                      S(3, 5, 3, 14))
    body = A.Block([call, A.Return(A.IntLit(0, S(4, 12)), S(4, 5, 4, 13))], S(2, 16, 5, 1))
    prog = A.Program([A.FunctionDecl("int", "main", Position(2, 5), [], body, S(2, 1, 5, 1))], S(1, 1, 5, 2))
    analyze(prog, sink, Position(1, 1))
    assert [(r.code, r.caused_by) for r in sink.records] == [("SYN-EXPECTED-EXPRESSION", None),
                                                            ("SEM-PRINTF-FORMAT", syn.id)]


def test_r4_r6_r7_r8_on_hand_built_ast():
    sink, (syn1, syn2) = _sink_with_syntax_records(2)
    broken = A.VarDecl("int", "b", Position(3, 9), None, A.ErrorExpr(S(3, 13), syn1.id), False, S(3, 9, 3, 13),
                       error_id=syn1.id, idents_in_span={"b"})
    keep = A.VarDecl("int", "k", Position(4, 9), None, A.IntLit(1, S(4, 13)), False, S(4, 9, 4, 13))
    lost = A.ErrorStmt(S(5, 5, 5, 20), syn2.id, "while", [], {"k"}, "{")
    orphan = A.Block([A.Break(S(6, 9, 6, 14))], S(5, 21, 7, 5), orphan_of=syn2.id)
    body = A.Block([A.VarDeclStmt([broken], S(3, 5, 3, 14)), A.VarDeclStmt([keep], S(4, 5, 4, 14)), lost, orphan],
                   S(2, 14, 8, 1))
    f = A.FunctionDecl("int", "f", Position(2, 5), [], body, S(2, 1, 8, 1))
    main_body = A.Block([A.Return(A.IntLit(0, S(9, 25)), S(9, 18, 9, 26))], S(9, 16, 9, 28))
    main = A.FunctionDecl("int", "main", Position(9, 5), [], main_body, S(9, 1, 9, 28))
    analyze(A.Program([f, main], S(1, 1, 9, 29)), sink, None)
    got = [(r.code, r.line, r.caused_by) for r in sink.records[2:]]
    assert got == [("SEM-BREAK-OUTSIDE-LOOP", 6, syn2.id),     # R7: orphan of a 'while' ErrorStmt
                   ("WRN-UNUSED-VAR", 3, syn1.id),             # R4: broken declaration
                   ("WRN-UNUSED-VAR", 4, syn2.id),             # R6: 'k' is in the ErrorStmt's idents_in_span
                   ("WRN-MISSING-RETURN", 2, syn2.id)]         # R8: first ErrorStmt in the body


def test_analyze_never_raises_on_empty_program():
    sink = ErrorSink("")
    analyze(A.Program([], S(1, 1)), sink, None)
    assert [(r.code, r.line) for r in sink.records] == [("SEM-MISSING-MAIN", 1)]
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_semantic.py` → `74 passed`
- `test -e src/cea/pipeline.py && echo EXISTS || echo absent` → `absent`
- `grep -nE "\bprint\s*\(|sys\.std(out|err)" src/cea/semantic.py` → no output
- Commit `src/cea/semantic.py` and `tests/unit/test_semantic.py`: `cea: add semantic analyser (plan 007 step 3)`.

### Step 4: The pipeline and the trace tests (switches on the corpus test)

Create `src/cea/pipeline.py` with this exact content:

```python
"""The compiler pipeline: lexical, syntax and semantic phases on one source text (plan 007).

``compile_source`` is the interface the corpus test (tests/test_corpus_compile.py)
and every later milestone call. It never raises on bad input: each phase
reports through one ErrorSink (PRD F1) and the next phase always runs
(docs/error-recovery.md §1, invariant 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cea import ast as A
from cea.diagnostics import ErrorSink
from cea.lexer import lex
from cea.parser import parse
from cea.records import ErrorRecord
from cea.semantic import analyze
from cea.tokens import Token


@dataclass
class CompileResult:
    errors: list[ErrorRecord]       # sink.records, creation order
    program: A.Program
    tokens: list[Token]
    _sink: ErrorSink | None = field(default=None, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        """True iff no record is fatal (PRD F4: a file with only warnings still compiles)."""
        return not any(r.severity == "fatal" for r in self.errors)

    def summary(self) -> str:
        """PRD F4 summary line, e.g. "2 fatal, 3 warnings"; delegates to ErrorSink.summary()."""
        assert self._sink is not None, "CompileResult was not built by compile_source()"
        return self._sink.summary()


def compile_source(source: str, filename: str) -> CompileResult:
    """Run all three phases. ``filename`` is for display only. root_id stays == id until F2 (milestone 2)."""
    sink = ErrorSink(source)
    lr = lex(source, sink)
    program = parse(lr, sink)
    analyze(program, sink, lr.stdio_include)
    return CompileResult(errors=sink.records, program=program, tokens=lr.tokens, _sink=sink)
```

`_sink` is a private field: the contract's `CompileResult` has no sink, but `summary()` must "delegate to `ErrorSink.summary()`" (contract §5), so the result keeps a reference to it.

Create `tests/test_recovery_traces.py` with this exact content. The ten record tables and the summary rows are copied from `docs/error-recovery.md` §9; the sources are the traces' code blocks.

```python
"""Exact-match tests for the traced examples of docs/error-recovery.md §9 (plan 007).

Each trace is compiled with ``cea.pipeline.compile_source`` and the full record
table is compared: id, code, line:col, found, caused_by, plus the provisional
F2 root (docs/error-recovery.md §7, "Provisional F2 root rule"), which this
test computes itself because ``root_id`` stays equal to ``id`` until milestone 2.
"""
import pytest

from cea.pipeline import compile_source

# (name, source, [(id, code, "line:col", found, caused_by or None, provisional root)])
TRACES = [
    ("T1", "int main(void) {\n    int a = 1;\n    int b = 2\n    a = a + b;\n    return a;\n}\n", [
        ("E-0001", "SYN-MISSING-SEMICOLON", "3:14", "a", None, "E-0001"),
    ]),
    ("T1b", "int main(void) {\n    int a = 1;\n    int b = 2 a = a + b;\n    return a;\n}\n", [
        ("E-0001", "SYN-MISSING-SEMICOLON", "3:14", "a", None, "E-0001"),
        ("E-0002", "WRN-UNUSED-VAR", "3:9", "b", "E-0001", "E-0001"),
    ]),
    ("T2", "int f(int a) {\n    if (a > 0) {\n        a = a - 1;\n    return a;\n}\n"
           "int main(void) {\n    return f(3);\n}\n", [
        ("E-0001", "SYN-UNBALANCED-BRACKET", "6:1", "int", None, "E-0001"),
        ("E-0002", "WRN-MISSING-RETURN", "1:5", "f", "E-0001", "E-0001"),
    ]),
    ("T3", "int main(void) {\n    int x = 1;\n    if x > 0) {\n        x = 2;\n    }\n    return 0;\n}\n", [
        ("E-0001", "SYN-EXPECTED-TOKEN", "3:8", "x", None, "E-0001"),
        ("E-0002", "WRN-UNUSED-VAR", "2:9", "x", "E-0001", "E-0001"),
    ]),
    ("T4", "int main(void) {\n    int total = 0;\n    count = 1;\n    total = total + count;\n"
           "    count = count + 1;\n    total = total + count;\n    return total;\n}\n", [
        ("E-0001", "SEM-UNDECLARED-VAR", "3:5", "count", None, "E-0001"),
        ("E-0002", "SEM-UNDECLARED-VAR", "4:21", "count", None, "E-0001"),
        ("E-0003", "SEM-UNDECLARED-VAR", "5:5", "count", None, "E-0001"),
        ("E-0004", "SEM-UNDECLARED-VAR", "5:13", "count", None, "E-0001"),
        ("E-0005", "SEM-UNDECLARED-VAR", "6:21", "count", None, "E-0001"),
    ]),
    ("T5", "int main(void) {\n    int x = 5 @ 2;\n    return x;\n}\n", [
        ("E-0001", "LEX-INVALID-CHAR", "2:15", "@", None, "E-0001"),
        ("E-0002", "SYN-MISSING-SEMICOLON", "2:14", "2", "E-0001", "E-0001"),
    ]),
    ("T6", "#include <stdio.h>\nint main(void) {\n    int count = 0;\n    printf(\"total\\q\\n\", count);\n"
           "    count = count + 1\n    result = count;\n    return 0;\n}\n", [
        ("E-0001", "LEX-INVALID-ESCAPE", "4:18", "\\q", None, "E-0001"),
        ("E-0002", "SYN-MISSING-SEMICOLON", "5:22", "result", None, "E-0002"),
        ("E-0003", "SEM-UNDECLARED-VAR", "6:5", "result", None, "E-0003"),
    ]),
    ("T7", "int main(void) {\n    int i = 0;\n    while (i < 10 {\n        i = i + 1;\n        if (i == 5) {\n"
           "            break;\n        }\n    }\n    return i;\n}\n", [
        ("E-0001", "SYN-UNBALANCED-BRACKET", "3:19", "{", None, "E-0001"),
    ]),
    ("T8", "int main(void) {\n    int n = 2;\n    switch (n) {\n        case 1:\n            n = 5;\n"
           "            break;\n        default:\n            n = 0;\n    }\n    return n;\n}\n", [
        ("E-0001", "SYN-UNSUPPORTED-FEATURE", "3:5", "switch", None, "E-0001"),
        ("E-0002", "SYN-UNSUPPORTED-FEATURE", "4:9", "case", "E-0001", "E-0001"),
        ("E-0003", "SYN-UNSUPPORTED-FEATURE", "7:9", "default", "E-0001", "E-0001"),
        ("E-0004", "SEM-BREAK-OUTSIDE-LOOP", "6:13", "break", "E-0001", "E-0001"),
    ]),
    ("T9", "int main(void) {\n    int *p;\n    p = 0;\n    return p;\n}\n", [
        ("E-0001", "SYN-UNSUPPORTED-FEATURE", "2:9", "*", None, "E-0001"),
        ("E-0002", "SEM-UNDECLARED-VAR", "3:5", "p", "E-0001", "E-0001"),
        ("E-0003", "SEM-UNDECLARED-VAR", "4:12", "p", "E-0001", "E-0001"),
    ]),
]

# Summary table of docs/error-recovery.md §9: (raw, displayed, fatal, warning)
SUMMARY = {
    "T1": (1, 1, 1, 0), "T1b": (2, 1, 1, 1), "T2": (2, 1, 1, 1), "T3": (2, 1, 1, 1), "T4": (5, 1, 5, 0),
    "T5": (2, 1, 2, 0), "T6": (3, 3, 3, 0), "T7": (1, 1, 1, 0), "T8": (4, 1, 4, 0), "T9": (3, 1, 3, 0),
}


def _function_of(rec, program):
    """Name of the function whose span contains the record's line, or None at file scope."""
    for d in program.decls:
        body = getattr(d, "body", None)
        if body is not None and d.span.start_line <= rec.line <= d.span.end_line:
            return d.name
    return None


def provisional_roots(result):
    """docs/error-recovery.md §7 'Provisional F2 root rule', as a test helper (F2 is milestone 2)."""
    roots, first_use = {}, {}
    for rec in result.errors:
        if rec.caused_by:
            roots[rec.id] = roots[rec.caused_by]
            continue
        if rec.code in ("SEM-UNDECLARED-VAR", "SEM-UNDECLARED-FUNC"):
            key = (rec.code, rec.found, _function_of(rec, result.program))
            if key in first_use:
                roots[rec.id] = roots[first_use[key]]
                continue
            first_use[key] = rec.id
        roots[rec.id] = rec.id
    return roots


@pytest.mark.parametrize("name,source,expected", TRACES, ids=[t[0] for t in TRACES])
def test_trace_record_table(name, source, expected):
    result = compile_source(source, f"{name}.c")
    roots = provisional_roots(result)
    got = [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by, roots[r.id]) for r in result.errors]
    assert got == expected


@pytest.mark.parametrize("name,source,expected", TRACES, ids=[t[0] for t in TRACES])
def test_trace_summary_row(name, source, expected):
    result = compile_source(source, f"{name}.c")
    roots = provisional_roots(result)
    raw = len(result.errors)
    displayed = len(set(roots.values()))
    fatal = sum(r.severity == "fatal" for r in result.errors)
    warning = sum(r.severity == "warning" for r in result.errors)
    assert (raw, displayed, fatal, warning) == SUMMARY[name]


@pytest.mark.parametrize("name,source,expected", TRACES, ids=[t[0] for t in TRACES])
def test_trace_root_id_is_own_id_until_f2(name, source, expected):
    result = compile_source(source, f"{name}.c")
    assert all(r.root_id == r.id for r in result.errors)
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/test_recovery_traces.py` → `30 passed`
- `.venv/Scripts/python -m pytest -q tests/test_corpus_compile.py` → `66 passed, 20 deselected` (54 dev + 12 valid programs; the 20 held-out cases stay deselected).
- Commit `src/cea/pipeline.py` and `tests/test_recovery_traces.py`: `cea: add compile pipeline and trace tests (plan 007 step 4)`.

If a trace fails, print its records with `.venv/Scripts/python -m pytest -q tests/test_recovery_traces.py -k T3 -vv` and compare with the table. If the difference is in a lexical or syntax record, it comes from plan 005/006 code: STOP and report. If it is in a semantic record and your `semantic.py` matches the plan exactly, STOP and report.

### Step 5: The command line

Create `src/cea/cli.py` with this exact content:

```python
"""Command-line interface: ``python -m cea FILE.c [--json]`` (plan 007).

This is the only module allowed to print (plans/m1-architecture.md §1, PRD F1).
Exit status: 0 when the file compiles (no fatal record, PRD F4), 1 when at
least one record is fatal, 2 for a usage error or an unreadable file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cea.pipeline import compile_source
from cea.records import ErrorRecord


def format_record(filename: str, rec: ErrorRecord) -> str:
    """One human-readable line, e.g. ``E-0002 t.c:5:22: fatal [SYN-MISSING-SEMICOLON] Expected ';' ...``."""
    text = f"{rec.id} {filename}:{rec.line}:{rec.column}: {rec.severity} [{rec.code}] {rec.message}"
    if rec.caused_by:
        text += f" (caused by {rec.caused_by})"
    return text


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # never crash on a console that cannot show a character
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(prog="python -m cea", description="Compile a C-subset file and report its errors.")
    ap.add_argument("file", help="path to a .c file")
    ap.add_argument("--json", action="store_true", help="print the error records as JSON")
    args = ap.parse_args(argv)
    path = Path(args.file)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    result = compile_source(source, path.name)
    if args.json:
        payload = {"file": path.name, "ok": result.ok, "summary": result.summary(),
                   "errors": [r.to_dict() for r in result.errors]}
        print(json.dumps(payload, indent=2))
    else:
        for rec in result.errors:
            print(format_record(path.name, rec))
        print(result.summary())
    return 0 if result.ok else 1
```

Create `src/cea/__main__.py` with this exact content (contract §1: only the import and `raise SystemExit(main())`, plus the module docstring every file has):

```python
"""Entry point for ``python -m cea``."""
from cea.cli import main

raise SystemExit(main())
```

Create `tests/unit/test_pipeline_cli.py` with this exact content. It covers PRD F1 acceptance (the T6 file gives exactly 3 records, one per phase), PRD F4 acceptance (`valid/011` has only a warning, `ok` is `True`, summary `0 fatal, 1 warning`), never-raises inputs, determinism over every dev and valid program, exact records for every valid program, and the CLI via `subprocess`. It never reads `heldout/`.

```python
"""Pipeline, PRD acceptance (F1, F4), determinism and CLI tests (plan 007)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cea.pipeline import CompileResult, compile_source

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "corpus"


def _c_files(split):
    """(split, path) for every .c file of one corpus split. Never called with "heldout" (held-out rule)."""
    return [(split, p) for p in sorted((CORPUS / split).glob("*.c"))]


def _sidecar(c_path):
    return json.loads(c_path.with_name(c_path.stem + ".expected.json").read_text(encoding="utf-8"))
T6 = ("#include <stdio.h>\nint main(void) {\n    int count = 0;\n    printf(\"total\\q\\n\", count);\n"
      "    count = count + 1\n    result = count;\n    return 0;\n}\n")


def test_f1_acceptance_one_record_per_phase():
    result = compile_source(T6, "t6.c")
    assert [(r.phase, r.code, r.line, r.column) for r in result.errors] == [
        ("lexical", "LEX-INVALID-ESCAPE", 4, 18),
        ("syntax", "SYN-MISSING-SEMICOLON", 5, 22),
        ("semantic", "SEM-UNDECLARED-VAR", 6, 5),
    ]
    assert not result.ok
    assert result.summary() == "3 fatal, 0 warnings"


def test_f4_acceptance_warnings_only_file_still_compiles():
    path = CORPUS / "valid" / "011-narrowing-warning.c"
    result = compile_source(path.read_text(encoding="utf-8"), path.name)
    assert [(r.code, r.severity) for r in result.errors] == [("WRN-IMPLICIT-NARROWING", "warning")]
    assert result.ok is True
    assert result.summary() == "0 fatal, 1 warning"


def test_compile_result_shape():
    result = compile_source("int main(void) {\n    return 0;\n}\n", "ok.c")
    assert isinstance(result, CompileResult)
    assert result.errors == [] and result.ok and result.summary() == "0 fatal, 0 warnings"
    assert result.tokens[-1].text == "EOF" and result.program.decls


@pytest.mark.parametrize("source", ["", "\n", "}", "int", "int main(", "@@@", "/*", "\"", "int main(void) { {{{ ",
                                    "int x = ;", "void main(void) { return 1; }", "for while if ; ) ] }"])
def test_compile_source_never_raises(source):
    result = compile_source(source, "junk.c")
    assert all(r.root_id == r.id for r in result.errors)
    ids = [r.id for r in result.errors]
    assert ids == [f"E-{n:04d}" for n in range(1, len(ids) + 1)]
    assert all(r.caused_by is None or r.caused_by < r.id for r in result.errors)


DEV_AND_VALID = _c_files("dev") + _c_files("valid")


@pytest.mark.parametrize("split,c_path", DEV_AND_VALID, ids=[f"{s}/{p.name}" for s, p in DEV_AND_VALID])
def test_records_are_deterministic(split, c_path):
    text = c_path.read_text(encoding="utf-8")
    first = [r.to_dict() for r in compile_source(text, c_path.name).errors]
    second = [r.to_dict() for r in compile_source(text, c_path.name).errors]
    assert first == second


@pytest.mark.parametrize("split,c_path", _c_files("valid"), ids=[p.name for _, p in _c_files("valid")])
def test_valid_programs_report_exactly_their_expected_warnings(split, c_path):
    side = _sidecar(c_path)
    result = compile_source(c_path.read_text(encoding="utf-8"), c_path.name)
    assert sorted((r.code, r.line) for r in result.errors) == sorted((w["code"], w["line"]) for w in side["warnings"])


def _run_cli(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "cea", *args], capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=ROOT)


def test_cli_json_with_fatal_error_exits_1():
    path = CORPUS / "dev" / "060-one-per-phase.c"
    proc = _run_cli(str(path), "--json")
    assert proc.returncode == 1, proc.stderr
    data = json.loads(proc.stdout)
    assert data["file"] == path.name and data["ok"] is False and data["summary"] == "3 fatal, 0 warnings"
    assert [e["phase"] for e in data["errors"]] == ["lexical", "syntax", "semantic"]
    first = data["errors"][0]
    for key in ("id", "phase", "code", "severity", "line", "column", "found", "expected", "snippet", "root_id",
                "rule_ref", "language", "caused_by", "span_end", "message"):
        assert key in first
    assert first["span_end"].keys() == {"line", "column"}


def test_cli_warnings_only_exits_0():
    proc = _run_cli(str(CORPUS / "valid" / "011-narrowing-warning.c"))
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert "WRN-IMPLICIT-NARROWING" in lines[0] and ":7:" in lines[0]
    assert lines[-1] == "0 fatal, 1 warning"


def test_cli_clean_file_exits_0_with_json():
    proc = _run_cli(str(CORPUS / "valid" / "001-sum-of-marks.c"), "--json")
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["errors"] == []


def test_cli_missing_file_exits_2():
    proc = _run_cli("does-not-exist.c")
    assert proc.returncode == 2
    assert "cannot read" in proc.stderr
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_pipeline_cli.py` → `97 passed`
- `PYTHONPATH=src .venv/Scripts/python -m cea tests/corpus/dev/060-one-per-phase.c; echo "exit=$?"` → three record lines (`LEX-INVALID-CHAR`, `SYN-MISSING-SEMICOLON`, `SEM-UNDECLARED-VAR`), then `3 fatal, 0 warnings`, then `exit=1`
- `PYTHONPATH=src .venv/Scripts/python -m cea tests/corpus/valid/011-narrowing-warning.c --json | .venv/Scripts/python -c "import json,sys; d=json.load(sys.stdin); print(d['ok'], d['summary'], [e['code'] for e in d['errors']])"` → `True 0 fatal, 1 warning ['WRN-IMPLICIT-NARROWING']`
- `.venv/Scripts/python -m pytest -q tests/unit/test_no_print.py` → all pass (plan 005's no-print rule still holds)
- Commit `src/cea/cli.py`, `src/cea/__main__.py` and `tests/unit/test_pipeline_cli.py`: `cea: add command-line interface and pipeline tests (plan 007 step 5)`.

### Step 6: Full suite, mutation checks and the index

1. `.venv/Scripts/python -m pytest -q` → exit 0, last line `<B+267> passed, 20 deselected in …` with **no** `skipped` (B is from Step 0; 267 = 74 + 30 + 97 + 66).
2. `python -I tools/check_spec.py` → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`.
3. Mutation checks (each must FAIL the suite, then be reverted with `git checkout -- src/cea/semantic.py`):
   - In `semantic.py`, change `in ("while", "for", "unsupported")` to `in ("while", "for")`. `.venv/Scripts/python -m pytest -q tests/test_recovery_traces.py tests/test_corpus_compile.py` → at least 1 failure (T8 loses its R7 link). Revert.
   - Change `tt = self.expr(e.target, write=plain)` to `tt = self.expr(e.target, write=True)`. `.venv/Scripts/python -m pytest -q tests/unit/test_semantic.py tests/test_corpus_compile.py` → at least 1 failure (compound assignment stops counting as a read). Revert.
   - `git status --short src` → no output after reverting.
4. `git diff --name-only main..HEAD` → exactly the 8 files in Scope (`docs/language-spec.md` plus the 7 new files).
5. Update the 007 row of `plans/README.md` to `DONE (on branch advisor/007-m1-semantic)` unless a reviewer told you they maintain the index, and commit it: `plans: mark plan 007 done (plan 007 step 6)`.

## Test plan

New tests (267 in total, all written above):

- `tests/unit/test_semantic.py` (74): one row per SEM/WRN code using the catalog's "Example trigger" in a minimal program, asserting the full record list, the exact message, phase, severity and `rule_ref`, plus a completeness check that every SEM/WRN code has a row; the printf builtin (no include, include after use, redeclaration, extra-argument types); scopes (shadowing, parameters share the body scope, `for`-init scope, double definition, prototype + recursion); reads and writes (`=` vs every compound operator and `++`/`--`, array element targets, scope-exit order, exemptions); conversions and narrowing in all four contexts; string conditions; void values (an unused void variable gets only SEM-VOID-VALUE); array names as values; `<error>` absorption; unreachable once per block; return paths (if/else, loop, block, else-if), `return 1; f();` giving only WRN-UNREACHABLE-CODE, and a statement after a returning if/else giving WRN-UNREACHABLE-CODE and no WRN-MISSING-RETURN; `break` in a nested loop; R3 on real source (global initialiser, array size) and R5 for a broken `main` header; R3 (printf), R4, R6, R7 and R8 on hand-built ASTs, so they do not depend on parser details; an empty program.
- `tests/test_recovery_traces.py` (30): the record tables of T1, T1b and T2–T9 (id, code, line:col, found, caused_by, provisional root), the summary rows (raw, displayed, fatal, warning), and `root_id == id`.
- `tests/unit/test_pipeline_cli.py` (97): PRD F1 and F4 acceptance, `CompileResult` shape, 12 never-raises inputs, determinism for all 54 dev and 12 valid programs, exact (code, line) equality for the 12 valid programs, and four CLI cases (JSON + exit 1, warnings-only exit 0, clean JSON exit 0, missing file exit 2).
- `tests/test_corpus_compile.py` (existing, 66 cases now active): every expected root and warning of every dev and valid sidecar is reported as `(code, line)`, and valid programs have no fatal record.

Pattern: `tests/test_corpus_schema.py`. Verification: Step 6 item 1.

## Advisor's verification (observed while writing this plan)

The seven files above were run in a scratch copy outside the repo, with a throwaway lexer and parser written to the contract (they are not plan 005/006 code), against the repo at `d72f58d` (code) and `efeb049` (Step 2), with both Step 2 paragraphs applied to a copy of `docs/language-spec.md` (`tools/check_spec.py` on that copy printed `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`):

- Traces: T1, T1b, T2, T3, T4, T5, T6, T7, T8 and T9 each reproduced the §9 record table **exactly** (ids, codes, positions, `found`, `caused_by`, provisional roots) and their summary rows.
- `tests/test_corpus_compile.py`: **54/54 dev and 12/12 valid pass**. Beyond the subset check, the full record list of every dev program matched the `Expected under plan 00x: raw N …` list in its sidecar `notes` (codes, lines, and whether `caused_by` is set), and every valid program produced exactly its expected warnings.
- Determinism: two compilations of every dev and valid program gave identical `to_dict()` lists.
- Robustness: 6,000 randomly mutated corpus programs went through `analyze` with no exception, and every `caused_by` pointed to an earlier id.
- The two mutation checks of Step 6 each made tests fail.
- Total: 267 new or newly active tests passed (74 + 30 + 97 + 66). The code blocks were extracted from this plan's text into a fresh copy before the final run.

## Done criteria

- [ ] Drift check and the Step 1 probes passed
- [ ] `grep -c "a block in which ANY" docs/language-spec.md` → `1`, `grep -c 'returns on every path (a .return., a block containing one' docs/language-spec.md` → `1`, and `python -I tools/check_spec.py` → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`
- [ ] `.venv/Scripts/python -m pytest -q` exits 0 with `<B+267> passed, 20 deselected` and nothing skipped
- [ ] `.venv/Scripts/python -m pytest -q tests/test_corpus_compile.py` → `66 passed, 20 deselected`
- [ ] `.venv/Scripts/python -m pytest -q tests/test_recovery_traces.py` → `30 passed`
- [ ] `PYTHONPATH=src .venv/Scripts/python -m cea tests/corpus/valid/011-narrowing-warning.c; echo $?` ends with `0 fatal, 1 warning` and `0`
- [ ] `grep -rnE "\bprint\s*\(|sys\.std(out|err)" src/cea/ | grep -v "src/cea/cli.py"` → no output
- [ ] `git diff --name-only main..HEAD` lists only the in-scope files; `git status --short` is clean
- [ ] Nothing under `tests/corpus/heldout/` was opened or run
- [ ] `plans/README.md` 007 row updated (unless a reviewer maintains it)
- [ ] Final report ends with a **Viva notes** list

## STOP conditions

Stop and report (do not improvise) if:

- A drift check or a Step 1 probe fails.
- In Step 2 the old `sem.return_paths` or `sem.unreachable` paragraph is not found exactly once, or `tools/check_spec.py` stops printing the OK line.
- A trace cannot be reproduced without contradicting a rule of `docs/error-recovery.md` or `docs/language-spec.md`, or a lexical/syntax record of a trace differs from the table (that is plan 005/006 code).
- A dev or valid corpus program fails the subset check and your files match the plan exactly. Report the program, the records it produced and the sidecar entry; say whether the cause is a sidecar or spec inconsistency or an upstream (005/006) behaviour. Never edit a sidecar or a spec to make a test pass.
- The contract in `plans/m1-architecture.md` is insufficient: an AST field the analyser uses is missing or has a different name or type, `ErrorSink.report` rejects a call the analyser makes, or `CompileResult` cannot be built as specified.
- A verification fails twice after you have compared your file with the plan.
- Any change seems to need an out-of-scope file.

## Maintenance notes

- **F2 (milestone 2)** replaces the test helper `provisional_roots` with real clustering and sets `root_id`. `test_trace_root_id_is_own_id_until_f2` must then be removed and the corpus test tightened from a subset check to exact roots.
- The ordering rules in "Design decisions" item 4 are part of the record ids. Any change to them changes ids and must update the trace tests and the sidecar notes together.
- `semantic.py` relies on `Program.span` ending at the EOF token (`eof_position`, contract §4). If that changes, SEM-MISSING-MAIN moves.
- `returns()` decides both WRN-MISSING-RETURN and when a block becomes unreachable; the two must stay in step with the rewritten `sem.return_paths` paragraph.
- A reviewer should scrutinise: R5's search order, R6's per-scope `err_mark`, the decision that an `ErrorStmt` right after a `return` gets no unreachable warning, and the decision that a void variable is declared with `ErrorType` (so its uses are silent).
- Deferred: format-string checking for printf (spec says not checked); constant-index range checks (spec says not checked); exact location of an initialiser's `=` (the AST has no position for it, so initialisation records use the declarator name, which is on the same line).

## Viva notes the executor must report (at least these)

- One pass in source order, justified by C99's declare-before-use; how prototype → definition → conflict is handled.
- The `<error>` type with a `cause`, and that it silences only type checks, never shape checks (R3).
- The record-order rules and why T8 requires "no unreachable warning on an `ErrorStmt`".
- Which reads count for "unused" (compound assignment and `++`/`--`; not `=`).
- Where each SEM/WRN record is located, and the `found` convention for type-valued templates.
- `root_id == id` until F2; provisional roots computed only in the trace test.
- The `sem.return_paths` and `sem.unreachable` rewrites (ANY statement that returns on every path ends the paths; code after it is unreachable, not a missing return) and why they were approved.
- Any deviation from this plan.
