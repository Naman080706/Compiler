# Plan 009: Cluster errors under root causes (PRD F2), test exact roots on the corpus, and measure F2

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md` (the "Milestone 2" table, row 009), unless a reviewer
> dispatched you and told you they maintain the index. End your final report
> with a **Viva notes** list: the decisions, trade-offs or deviations an
> examiner might ask about (see `plans/README.md`, "Viva notes convention").
> Do not edit `VIVA.md`; the advisor folds your notes into it.
>
> Every code block marked "exact content" is the whole file to write; copy it
> verbatim. Blocks marked "replace … with" are exact edits. Do not reformat or
> "improve" them. The advisor ran exactly this code on a copy of the repo
> (`231049a` plus plan 008) and got every number quoted below. If a
> verification fails and your file is identical to the plan, STOP and report.
>
> **Never open, read, list or run anything under `tests/corpus/heldout/`.**
> (`pytest` deselects held-out tests by default; keep it that way. Do not run
> `pytest -m heldout` and do not pass `--i-am-milestone-5`.)
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat 231049a..HEAD -- src/cea/pipeline.py src/cea/cli.py src/cea/records.py tests/test_corpus_compile.py tests/test_recovery_traces.py tests/unit/test_pipeline_cli.py tests/corpus/README.md` must print **nothing**.
> 2. `ls src/cea/cluster.py tests/unit/test_cluster.py tools/metrics_f2.py tests/unit/test_metrics_f2.py 2>&1 | grep -c "No such file"` must print `4`.
> 3. `grep -c "Unbalanced bracket at '{found}': {detail}" docs/error-catalog.md` must print `1` (plan 008 has landed).
> 4. `.venv/Scripts/python -m pytest -q` must end with `861 passed, 20 deselected`.
>
> If any check fails, STOP and report which one.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (it changes `root_id` on every record, which two existing test files assumed was always `== id`)
- **Depends on**: `plans/008-fix-stray-closer-message.md` (merged)
- **Category**: direction (milestone 2, PRD F2)
- **Planned at**: commit `231049a`, 2026-10-10

## Why this matters

The project is a course compiler for a strict C99 subset (Python, `src/cea/`). Milestone 1 already links cascading errors to their cause through `caused_by`, but every record is still its own root (`root_id == id`), so a student sees every symptom. PRD F2 asks the compiler to group symptoms under the root cause and display one entry per root. This plan adds `src/cea/cluster.py` (the binding interface from `plans/m2-architecture.md` §2), wires it into `compile_source`, shows roots with a "+N related" count in the CLI, tightens the corpus test from "roots are reported" to "the displayed fatal roots are EXACTLY the expected roots", and adds `tools/metrics_f2.py`, which measures the raw-vs-displayed reduction over the cascade set. The F3 agent (plan 011) and the API/UI (012/013) build on `CompileResult.clusters`.

## Current state

- `plans/m2-architecture.md` §2 (binding contract), quoted:
  ```python
  # cluster.py (plan 009)
  def assign_roots(records: list[ErrorRecord]) -> None: ...
      # sets r.root_id in place, in id order:
      #   1. caused_by set          -> root_id = root_id of caused_by
      #   2. SEM-UNDECLARED-VAR/FUNC whose name matches an earlier record with the same code in the
      #      same function body (or both at file scope) -> that record's root_id  (PRD: "an undeclared
      #      variable groups all its later uses"; "name" = record.found)
      #   3. otherwise              -> root_id = id
      # This is exactly the provisional rule of docs/error-recovery.md §7. The PRD's "same statement or
      # block" rule is applied ONLY through caused_by (R1/R2/R9); do not add block-wide merging.
  def roots(records) -> list[ErrorRecord]: ...          # records with root_id == id, in (line, column) order
  def cluster_view(records) -> list[Cluster]: ...
  @dataclass
  class Cluster:
      root: ErrorRecord
      symptoms: list[ErrorRecord]                       # same root_id, excluding the root, id order
  ```
  "`pipeline.compile_source` calls `assign_roots` last … `CompileResult` gains `clusters: list[Cluster]`." §3 (plan 012) will serialise clusters as `{root_id, symptom_ids}`; this plan's `--json` uses the same shape.
- **One necessary addition to the contract signature** (advisor decision, listed under Open questions): records carry no function name, so rule 2 ("same function body") cannot be decided from records alone. `assign_roots` therefore takes an optional keyword `program: A.Program | None = None`. `compile_source` passes it. Calling `assign_roots(records)` without it still works (every record then counts as file scope). Nothing else in the contract changes.
- `src/cea/pipeline.py` (45 lines) today:
  ```python
  @dataclass
  class CompileResult:
      errors: list[ErrorRecord]       # sink.records, creation order
      program: A.Program
      tokens: list[Token]
      _sink: ErrorSink | None = field(default=None, repr=False, compare=False)
      ...
  def compile_source(source: str, filename: str) -> CompileResult:
      """Run all three phases. ``filename`` is for display only. root_id stays == id until F2 (milestone 2)."""
      sink = ErrorSink(source)
      lr = lex(source, sink)
      program = parse(lr, sink)
      analyze(program, sink, lr.stdio_include)
      return CompileResult(errors=sink.records, program=program, tokens=lr.tokens, _sink=sink)
  ```
  `sink.records` returns a new list holding the SAME record objects, so mutating `root_id` on them is visible everywhere.
- `src/cea/records.py:26`: `    root_id: str            # == id until F2 (milestone 2) assigns clusters` (comment only changes).
- `src/cea/cli.py` (51 lines): prints `format_record(...)` for every record, then `result.summary()`; `--json` prints `{"file", "ok", "summary", "errors"}`. It is the only module allowed to `print` (`tests/unit/test_no_print.py` greps `src/cea/*.py`; `tools/` is not checked).
- `src/cea/ast.py`: `Program.decls` holds `FunctionDecl | VarDeclStmt | ErrorStmt`; `FunctionDecl` has `name`, `body` (`None` for a prototype) and `span: Span(start_line, start_col, end_line, end_col)`, inclusive.
- Two existing tests assume `root_id == id` and must change in Step 1:
  - `tests/test_recovery_traces.py`: the helper `provisional_roots()` recomputes the §7 rule itself, and `test_trace_root_id_is_own_id_until_f2` asserts `root_id == id` (10 cases; 7 fail once clustering is on: T1b, T2, T3, T4, T5, T8, T9).
  - `tests/unit/test_pipeline_cli.py::test_compile_source_never_raises` asserts `root_id == id` (3 of 12 cases fail: `int main(`, `int main(void) { {{{ `, `int x = ;`).
- `tests/test_corpus_compile.py` today does only a SUBSET check, with the comment "Exact equality between the expected roots and the records the compiler marks as roots (root_id == id) is deferred to the F2 clustering milestone, which will tighten this test." `tests/corpus/README.md` §6 (lines 183–187) says the same.
- Sidecar schema (`tests/corpus/README.md` §3): `roots` = fatal codes only, one per injected fatal fault, `{code, line}`; `warnings` = `WRN-*` the compiler must report; `cascading` = true if one fault gives several records; `injected_faults` = one entry per fault (1 for single-fault and cascading programs, 2–3 for `dev/060`–`063`).
- F2 metric decision (`plans/README.md`, "Follow-ups noted in review"): "The cascade set is the programs with `cascading: true` … 15 dev and 8 heldout. For part (b) of plan 002 §10 (displayed = 1), only single-fault files count. Multi-fault files (`dev/060`–`063`, …) count in the part (c) raw-vs-displayed sum, with expected displayed = their number of roots." Plan 002 §10 (`docs/error-recovery.md` §10) part (c): "the clustering metric is reported as raw vs displayed counts summed over the cascade set, together with the per-file table."
- Repo conventions: module docstring on every file, type hints, `@dataclass`, stdlib only in `src/cea/`, unit tests in `tests/unit/test_<module>.py` with plain `assert` and `pytest.mark.parametrize` (model: `tests/unit/test_pipeline_cli.py`).

## Advisor's verification (what you should reproduce)

Run on a scratch copy at `231049a` + plan 008 + exactly this plan's code (Python 3.13.1, gcc 12.4 on PATH):

- Full suite after each step: 877 → 877 → 881 → 883 passed, 20 deselected.
- Exact-root corpus check: **all 54 dev and all 12 valid programs pass** (66 passed). Compared as sorted lists (multiset), not only as sets; no failures. No sidecar disagrees with the clustering rule.
- All 10 trace tables of `docs/error-recovery.md` §9 match with the real `root_id` (the provisional rule and `cea.cluster` agree on every record).
- `python tools/metrics_f2.py` (dev cascade set):
  ```
  F2 metric, split=dev, cascade set = 15 programs
  program                                           raw shown want  check
  002-unclosed-printf-string.c                        2     1    1  ok
  003-two-char-literal.c                              2     1    1  ok
  005-number-with-letters.c                           2     1    1  ok
  012-param-without-type.c                            2     1    1  ok
  041-missing-brace-before-next-function.c            2     1    1  ok
  043-loop-counter-never-declared.c                   9     1    1  ok
  046-unclosed-string-mid-function.c                  2     1    1  ok
  047-helper-called-before-defined.c                  4     1    1  ok
  049-pointer-declaration-uses.c                      6     1    1  ok
  051-for-header-missing-semicolon.c                  3     1    1  ok
  052-switch-grade-menu.c                             6     1    1  ok
  060-one-per-phase.c                                 3     3    3  ok
  061-two-semantic-faults.c                           2     2    2  ok
  062-syntax-and-semantic.c                           3     2    2  ok
  063-fault-plus-warning.c                            2     2    2  ok
  TOTAL raw=50 displayed=20 reduction=60.0%
  SINGLE-FAULT raw=40 displayed=11 reduction=72.5%
  part (b): 11/11 single-fault programs display exactly 1 root
  mismatches: 0
  ```

Without `gcc` on PATH, one gcc test is skipped: read every "N passed" as "N-1 passed, 1 skipped".

## Commands you will need

| Purpose | Command (project root, Git Bash) | Expected on success |
|---|---|---|
| venv (once, if missing) | `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt` | exit 0 |
| Tests | `.venv/Scripts/python -m pytest -q` | see each step |
| One file | `.venv/Scripts/python -m pytest -q tests/unit/test_cluster.py` | see each step |
| Spec check | `.venv/Scripts/python tools/check_spec.py` | `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules` |
| CLI | `PYTHONPATH=src .venv/Scripts/python -m cea tests/corpus/dev/043-loop-counter-never-declared.c` | see Step 3 |
| Metric | `.venv/Scripts/python tools/metrics_f2.py` | see Step 4 |

## Scope

**In scope** (the only files you may create or modify):
- `src/cea/cluster.py` (create), `src/cea/pipeline.py`, `src/cea/cli.py`, `src/cea/records.py` (one comment)
- `tests/unit/test_cluster.py` (create), `tests/unit/test_metrics_f2.py` (create), `tests/test_recovery_traces.py`, `tests/unit/test_pipeline_cli.py`, `tests/test_corpus_compile.py`
- `tools/metrics_f2.py` (create)
- `tests/corpus/README.md` (§6, one bullet)
- `plans/README.md` (status row 009 only)

**Out of scope** (do NOT touch):
- Every `*.expected.json` sidecar and every `.c` file under `tests/corpus/`. If a sidecar seems wrong, STOP and report; never edit it to make a test pass.
- `tests/corpus/heldout/**`: never read it (held-out rule, `tests/corpus/README.md` §5).
- `src/cea/lexer.py`, `parser.py`, `semantic.py`, `diagnostics.py`, `catalog.py`: clustering reads records, it does not change how they are created or linked.
- `docs/**`: no doc change. (`docs/error-recovery.md` §7 still calls the rule "provisional"; the advisor updates the docs when reviewing.)
- `VIVA.md`, `plans/m2-architecture.md`.
- Any block-wide merging rule ("errors after a syntax error in the same block") — explicitly forbidden by the contract.

## Git workflow

- Branch: `advisor/009-f2-clustering` from `main` (after 008 is merged).
- One commit per step. Stage by explicit path (never `git add -A` / `git add .`). Message style: `cea: ... (plan 009 step N)` / `tests: ...` / `tools: ...`, as in `git log`. Every commit message ends with a blank line and then:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
- Do NOT push (no remote). Do NOT merge; the owner reviews first.

## Steps

### Step 1: `cluster.py`, wire it into the pipeline, and update the tests that assumed `root_id == id`

1a. Create `src/cea/cluster.py`, exact content:

```python
"""F2 error clustering: assign each record's root_id and group symptoms under roots (plan 009).

The rule is the provisional root rule of docs/error-recovery.md section 7, made
final by plans/m2-architecture.md section 2. In id order:

1. ``caused_by`` is set -> ``root_id`` = the ``root_id`` of ``caused_by``.
2. SEM-UNDECLARED-VAR / SEM-UNDECLARED-FUNC whose name (``found``) matches an
   earlier record with the same code in the same function body (or both at
   file scope) -> that record's ``root_id`` (PRD: "an undeclared variable
   groups all its later uses").
3. Otherwise -> ``root_id`` = ``id``.

The PRD's "same statement or block" rule is applied ONLY through caused_by
(R1/R2/R9); there is deliberately no block-wide merging. Nothing here prints.
"""
from __future__ import annotations

from dataclasses import dataclass

from cea import ast as A
from cea.records import ErrorRecord

UNDECLARED_CODES = ("SEM-UNDECLARED-VAR", "SEM-UNDECLARED-FUNC")


@dataclass
class Cluster:
    root: ErrorRecord
    symptoms: list[ErrorRecord]          # same root_id, excluding the root, id order


def _id_order(rec: ErrorRecord) -> int:
    """Numeric part of "E-0012" (ids are numbered in creation order)."""
    return int(rec.id.split("-")[1])


def _function_spans(program: A.Program | None) -> list[tuple[str, A.Span]]:
    """(name, span) of every function definition that has a body, in source order."""
    if program is None:
        return []
    return [(d.name, d.span) for d in program.decls
            if isinstance(d, A.FunctionDecl) and d.body is not None]


def _scope_of(rec: ErrorRecord, spans: list[tuple[str, A.Span]]) -> int | None:
    """Index of the function body containing the record's position, or None for file scope."""
    pos = (rec.line, rec.column)
    for i, (_, s) in enumerate(spans):
        if (s.start_line, s.start_col) <= pos <= (s.end_line, s.end_col):
            return i
    return None


def assign_roots(records: list[ErrorRecord], program: A.Program | None = None) -> None:
    """Set ``root_id`` on every record in place, in id order (rules 1-3 above).

    ``program`` locates function bodies for rule 2. Without it every record
    counts as file scope, so rule 2 groups same-code same-name records file-wide.
    """
    spans = _function_spans(program)
    by_id: dict[str, ErrorRecord] = {}
    first_use: dict[tuple[str, str, int | None], str] = {}
    for rec in sorted(records, key=_id_order):
        key = None
        if rec.code in UNDECLARED_CODES:
            key = (rec.code, rec.found, _scope_of(rec, spans))
        if rec.caused_by is not None and rec.caused_by in by_id:
            rec.root_id = by_id[rec.caused_by].root_id                               # rule 1
        elif key is not None and key in first_use:
            rec.root_id = by_id[first_use[key]].root_id                              # rule 2
        else:
            rec.root_id = rec.id                                                     # rule 3
        if key is not None and key not in first_use:
            first_use[key] = rec.id
        by_id[rec.id] = rec


def roots(records: list[ErrorRecord]) -> list[ErrorRecord]:
    """Records with ``root_id == id``, in (line, column) order (ties by id)."""
    return sorted((r for r in records if r.root_id == r.id), key=lambda r: (r.line, r.column, _id_order(r)))


def cluster_view(records: list[ErrorRecord]) -> list[Cluster]:
    """One Cluster per root, in ``roots()`` order; symptoms in id order."""
    clusters = {r.id: Cluster(root=r, symptoms=[]) for r in roots(records)}
    for rec in sorted(records, key=_id_order):
        if rec.root_id != rec.id and rec.root_id in clusters:
            clusters[rec.root_id].symptoms.append(rec)
    return list(clusters.values())
```

Design notes (do not change the code because of them): an undeclared record that went through rule 1 (e.g. R5-linked, trace T9) still registers as the "first use" of its name, because the contract says "an earlier record with the same code", whatever its own root. `_id_order` sorts numerically so `E-10000` would sort after `E-9999`.

1b. Replace `src/cea/pipeline.py` with this exact content:

```python
"""The compiler pipeline: lexical, syntax and semantic phases on one source text (plan 007).

``compile_source`` is the interface the corpus test (tests/test_corpus_compile.py)
and every later milestone call. It never raises on bad input: each phase
reports through one ErrorSink (PRD F1) and the next phase always runs
(docs/error-recovery.md §1, invariant 1). After the three phases, F2
clustering (plan 009, ``cea.cluster``) fills every record's ``root_id``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cea import ast as A
from cea.cluster import Cluster, assign_roots, cluster_view
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
    clusters: list[Cluster] = field(default_factory=list)   # F2: one per root, roots in (line, column) order
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
    """Run all three phases, then F2 clustering. ``filename`` is for display only."""
    sink = ErrorSink(source)
    lr = lex(source, sink)
    program = parse(lr, sink)
    analyze(program, sink, lr.stdio_include)
    errors = sink.records
    assign_roots(errors, program)                       # F2 (plan 009): last, after every phase
    return CompileResult(errors=errors, program=program, tokens=lr.tokens,
                         clusters=cluster_view(errors), _sink=sink)
```

1c. `src/cea/records.py`: replace the line
`    root_id: str            # == id until F2 (milestone 2) assigns clusters`
with
`    root_id: str            # id of the cluster root; set by cea.cluster.assign_roots (F2, plan 009)`

1d. `tests/test_recovery_traces.py`:
- Replace the module docstring's last three lines
  ```
  table is compared: id, code, line:col, found, caused_by, plus the provisional
  F2 root (docs/error-recovery.md §7, "Provisional F2 root rule"), which this
  test computes itself because ``root_id`` stays equal to ``id`` until milestone 2.
  """
  ```
  with
  ```
  table is compared: id, code, line:col, found, caused_by and root_id. Since
  plan 009, ``root_id`` is filled by F2 clustering (``cea.cluster``), which
  implements the root rule of docs/error-recovery.md §7.
  """
  ```
- Replace the comment `# (name, source, [(id, code, "line:col", found, caused_by or None, provisional root)])` with `# (name, source, [(id, code, "line:col", found, caused_by or None, root_id)])`.
- Leave `TRACES` and `SUMMARY` unchanged. Delete everything from the line `def _function_of(rec, program):` to the end of the file, and put this in its place (exact content):

```python
@pytest.mark.parametrize("name,source,expected", TRACES, ids=[t[0] for t in TRACES])
def test_trace_record_table(name, source, expected):
    result = compile_source(source, f"{name}.c")
    got = [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by, r.root_id) for r in result.errors]
    assert got == expected


@pytest.mark.parametrize("name,source,expected", TRACES, ids=[t[0] for t in TRACES])
def test_trace_summary_row(name, source, expected):
    result = compile_source(source, f"{name}.c")
    raw = len(result.errors)
    displayed = len(result.clusters)
    fatal = sum(r.severity == "fatal" for r in result.errors)
    warning = sum(r.severity == "warning" for r in result.errors)
    assert (raw, displayed, fatal, warning) == SUMMARY[name]


@pytest.mark.parametrize("name,source,expected", TRACES, ids=[t[0] for t in TRACES])
def test_trace_clusters_partition_the_records(name, source, expected):
    result = compile_source(source, f"{name}.c")
    ids = [r.id for c in result.clusters for r in [c.root, *c.symptoms]]
    assert sorted(ids) == [r.id for r in result.errors]
    assert all(c.root.root_id == c.root.id and c.root.caused_by is None for c in result.clusters)
    assert all(s.root_id == c.root.id for c in result.clusters for s in c.symptoms)
```

1e. `tests/unit/test_pipeline_cli.py`, in `test_compile_source_never_raises`, replace the line
```python
    assert all(r.root_id == r.id for r in result.errors)
```
with
```python
    by_id = {r.id: r for r in result.errors}
    assert all(by_id[r.root_id].root_id == r.root_id and r.root_id <= r.id for r in result.errors)
```

1f. Create `tests/unit/test_cluster.py`, exact content:

```python
"""F2 clustering (plan 009): cea.cluster.assign_roots, roots, cluster_view.

The rule is docs/error-recovery.md §7 (provisional root rule), made final by
plans/m2-architecture.md §2: caused_by first, then same-name undeclared
grouping within one function body (or file scope), otherwise its own root.
"""
import pytest

from cea import cluster as C
from cea.pipeline import compile_source
from cea.records import ErrorRecord, Position


def rec(n, code="SEM-UNDECLARED-VAR", line=1, column=1, found="x", caused_by=None):
    """A hand-made record; root_id starts equal to id, as ErrorSink creates it."""
    rid = f"E-{n:04d}"
    return ErrorRecord(id=rid, phase="semantic", code=code, severity="fatal", line=line, column=column,
                       found=found, expected=[], snippet="", root_id=rid, rule_ref="sem.declare_before_use",
                       language="c", caused_by=caused_by, span_end=Position(line, column), message="m")


def root_ids(records):
    return [r.root_id for r in records]


# ---------------------------------------------------------------- traces of docs/error-recovery.md §9
T2 = ("int f(int a) {\n    if (a > 0) {\n        a = a - 1;\n    return a;\n}\n"
      "int main(void) {\n    return f(3);\n}\n")
T4 = ("int main(void) {\n    int total = 0;\n    count = 1;\n    total = total + count;\n"
      "    count = count + 1;\n    total = total + count;\n    return total;\n}\n")
T5 = "int main(void) {\n    int x = 5 @ 2;\n    return x;\n}\n"
T6 = ("#include <stdio.h>\nint main(void) {\n    int count = 0;\n    printf(\"total\\q\\n\", count);\n"
      "    count = count + 1\n    result = count;\n    return 0;\n}\n")
T8 = ("int main(void) {\n    int n = 2;\n    switch (n) {\n        case 1:\n            n = 5;\n"
      "            break;\n        default:\n            n = 0;\n    }\n    return n;\n}\n")
T9 = "int main(void) {\n    int *p;\n    p = 0;\n    return p;\n}\n"


@pytest.mark.parametrize("source,expected_roots,displayed", [
    (T2, ["E-0001", "E-0001"], 1),                                  # R8 link: warning under the bracket
    (T4, ["E-0001"] * 5, 1),                                        # rule 2: 5 uses of `count`
    (T5, ["E-0001", "E-0001"], 1),                                  # R1 link: lex error is the root
    (T6, ["E-0001", "E-0002", "E-0003"], 3),                        # three independent faults
    (T8, ["E-0001"] * 4, 1),                                        # R2, R9, R7 chain to `switch`
    (T9, ["E-0001"] * 3, 1),                                        # R5: rule 1 wins over rule 2
], ids=["T2", "T4", "T5", "T6", "T8", "T9"])
def test_trace_roots(source, expected_roots, displayed):
    result = compile_source(source, "t.c")
    assert root_ids(result.errors) == expected_roots
    assert len(C.roots(result.errors)) == len(result.clusters) == displayed


def test_t5_cluster_has_lexical_root_and_syntax_symptom():
    result = compile_source(T5, "t5.c")
    (cl,) = result.clusters
    assert cl.root.code == "LEX-INVALID-CHAR" and [s.code for s in cl.symptoms] == ["SYN-MISSING-SEMICOLON"]


# ---------------------------------------------------------------- rule 2: same-name undeclared grouping
SAME_NAME_TWO_FUNCS = ("int f(void) {\n    y = 1;\n    return foo(y);\n}\n"
                       "int main(void) {\n    y = 2;\n    foo(y);\n    return y;\n}\n")


def test_undeclared_same_name_groups_within_one_function_only():
    result = compile_source(SAME_NAME_TWO_FUNCS, "two.c")
    got = [(r.id, r.code, r.found, r.root_id) for r in result.errors]
    assert got == [
        ("E-0001", "SEM-UNDECLARED-VAR", "y", "E-0001"),      # f: first y
        ("E-0002", "SEM-UNDECLARED-FUNC", "foo", "E-0002"),   # f: first foo
        ("E-0003", "SEM-UNDECLARED-VAR", "y", "E-0001"),      # f: same function -> grouped
        ("E-0004", "SEM-UNDECLARED-VAR", "y", "E-0004"),      # main: different function -> new root
        ("E-0005", "SEM-UNDECLARED-FUNC", "foo", "E-0005"),
        ("E-0006", "SEM-UNDECLARED-VAR", "y", "E-0004"),
        ("E-0007", "SEM-UNDECLARED-VAR", "y", "E-0004"),
    ]
    assert [(c.root.id, [s.id for s in c.symptoms]) for c in result.clusters] == [
        ("E-0001", ["E-0003"]), ("E-0002", []), ("E-0004", ["E-0006", "E-0007"]), ("E-0005", [])]


def test_undeclared_same_name_at_file_scope_groups():
    result = compile_source("int g = x;\nint h = x;\nint main(void) {\n    return 0;\n}\n", "g.c")
    undeclared = [(r.id, r.root_id) for r in result.errors if r.code == "SEM-UNDECLARED-VAR"]
    assert undeclared == [("E-0002", "E-0002"), ("E-0004", "E-0002")]


def test_rule2_needs_same_code_and_same_name():
    records = [rec(1, found="x"), rec(2, found="y"), rec(3, code="SEM-UNDECLARED-FUNC", found="x"),
               rec(4, found="x")]
    C.assign_roots(records)
    assert root_ids(records) == ["E-0001", "E-0002", "E-0003", "E-0001"]


def test_rule2_is_not_applied_to_other_codes():
    records = [rec(1, code="SEM-REDECLARED", found="x"), rec(2, code="SEM-REDECLARED", found="x")]
    C.assign_roots(records)
    assert root_ids(records) == ["E-0001", "E-0002"]


# ---------------------------------------------------------------- rule 1 and the views
def test_caused_by_chain_takes_the_root_of_the_cause():
    records = [rec(1, code="LEX-INVALID-CHAR"), rec(2, code="SYN-MISSING-SEMICOLON", caused_by="E-0001"),
               rec(3, code="WRN-UNUSED-VAR", caused_by="E-0002"), rec(4, code="SEM-NOT-ARRAY")]
    C.assign_roots(records)
    assert root_ids(records) == ["E-0001", "E-0001", "E-0001", "E-0004"]


def test_caused_by_beats_rule2():
    records = [rec(1, found="p"), rec(2, code="SYN-UNSUPPORTED-FEATURE", found="*"),
               rec(3, found="p", caused_by="E-0002")]
    C.assign_roots(records)
    assert root_ids(records) == ["E-0001", "E-0002", "E-0002"]


def test_assign_roots_is_idempotent():
    result = compile_source(T4, "t4.c")
    before = root_ids(result.errors)
    C.assign_roots(result.errors, result.program)
    assert root_ids(result.errors) == before


def test_roots_sorted_by_position_and_cluster_view_partitions():
    records = [rec(1, line=5, column=3), rec(2, code="SEM-NOT-ARRAY", line=2, column=9),
               rec(3, line=7, column=1, found="x"), rec(4, code="SEM-NOT-ARRAY", line=2, column=1)]
    C.assign_roots(records)
    assert [r.id for r in C.roots(records)] == ["E-0004", "E-0002", "E-0001"]
    view = C.cluster_view(records)
    assert [(c.root.id, [s.id for s in c.symptoms]) for c in view] == [
        ("E-0004", []), ("E-0002", []), ("E-0001", ["E-0003"])]


def test_empty_input():
    C.assign_roots([])
    assert C.roots([]) == [] and C.cluster_view([]) == []
```

(In the `T6` string, `\"`, `\\q` and `\\n` are Python escapes exactly as shown; they match `TRACES` in `tests/test_recovery_traces.py`.)

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_cluster.py` → `16 passed`
- `.venv/Scripts/python -m pytest -q tests/test_recovery_traces.py` → `30 passed`
- `.venv/Scripts/python -m pytest -q` → `877 passed, 20 deselected`
- `grep -n "provisional_roots\|until_f2" tests/test_recovery_traces.py` → no output

Commit: `cea: F2 clustering module wired into the pipeline (plan 009 step 1)`, staging `src/cea/cluster.py src/cea/pipeline.py src/cea/records.py tests/test_recovery_traces.py tests/unit/test_pipeline_cli.py tests/unit/test_cluster.py`.

### Step 2: Exact-root corpus check for dev and valid

2a. Replace `tests/test_corpus_compile.py` with this exact content:

```python
"""Corpus-versus-compiler contract test (plans 003, 009).

The full interface contract is written in tests/corpus/README.md §6.
Since plan 009 (F2 clustering), dev and valid programs are checked EXACTLY:
the (code, line) list of fatal roots (records with root_id == id) must equal
the sidecar's ``roots``. Warnings keep the subset check.
"""
import pytest

pipeline = pytest.importorskip("cea.pipeline")

import corpus_lib as cl  # noqa: E402

RECORD_ATTRS = ("id", "code", "line", "column", "severity", "phase", "root_id", "caused_by")
EXACT_ROOT_SPLITS = ("dev", "valid")   # heldout keeps the subset check until milestone 5


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
    # Every expected root and warning must be reported with the same (code, line).
    missing = [e for e in side["roots"] + side["warnings"] if (e["code"], e["line"]) not in got]
    assert not missing, f"not reported as (code, line): {missing}; got {sorted(got)}"
    if side["split"] in EXACT_ROOT_SPLITS:
        # F2 (plan 009): the fatal roots the compiler displays are exactly the sidecar roots.
        # Compared as sorted lists, so a duplicated (code, line) root would also be caught.
        fatal_roots = sorted((r.code, r.line) for r in result.errors if r.root_id == r.id and r.severity == "fatal")
        expected = sorted((e["code"], e["line"]) for e in side["roots"])
        detail = [(r.id, r.code, r.line, r.found, r.caused_by, r.root_id) for r in result.errors]
        assert fatal_roots == expected, f"fatal roots {fatal_roots} != sidecar roots {expected}; records {detail}"
    if side["split"] == "valid":
        fatal = [(r.code, r.line) for r in result.errors if r.severity == "fatal"]
        assert not fatal, f"valid program produced fatal errors: {fatal}"
```

2b. `tests/corpus/README.md` §6: replace the bullet
```
- Today `tests/test_corpus_compile.py` checks only that every expected root and
  warning appears as a record with the same `(code, line)`, and that `valid/`
  programs have no fatal records. Exact equality between expected roots and
  reported roots is deferred to the F2 clustering milestone. The test is
  skipped until `cea.pipeline` exists.
```
with
```
- `tests/test_corpus_compile.py` checks that every expected root and warning
  appears as a record with the same `(code, line)`, and that `valid/` programs
  have no fatal records. Since plan 009 (F2 clustering) it also checks, for
  `dev/` and `valid/`, that the `(code, line)` list of fatal roots (records
  with `root_id == id` and severity `fatal`) equals the sidecar `roots`
  exactly. Warnings keep the subset check, and `heldout/` keeps only the
  subset check until milestone 5.
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/test_corpus_compile.py` → `66 passed, 20 deselected` (54 dev + 12 valid)
- `.venv/Scripts/python -m pytest -q` → `877 passed, 20 deselected`

If any dev or valid program fails here, **STOP** (see STOP conditions); paste the assertion message (it lists every record with its `caused_by` and `root_id`).

Commit: `tests: exact F2 root check on dev and valid corpus (plan 009 step 2)`, staging `tests/test_corpus_compile.py tests/corpus/README.md`.

### Step 3: CLI shows one line per root with "+N related"; `--json` gains `clusters`

3a. Replace `src/cea/cli.py` with this exact content:

```python
"""Command-line interface: ``python -m cea FILE.c [--json] [--all]`` (plans 007, 009).

This is the only module allowed to print (plans/m1-architecture.md §1, PRD F1).
By default it shows one line per F2 root cause, with a "+N related" count of
the symptoms grouped under it (plan 009). ``--all`` lists every record.
``--json`` prints every record plus a ``clusters`` array.
Exit status: 0 when the file compiles (no fatal record, PRD F4), 1 when at
least one record is fatal, 2 for a usage error or an unreadable file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cea.cluster import Cluster
from cea.pipeline import compile_source
from cea.records import ErrorRecord


def format_record(filename: str, rec: ErrorRecord) -> str:
    """One human-readable line, e.g. ``E-0002 t.c:5:22: fatal [SYN-MISSING-SEMICOLON] Expected ';' ...``."""
    text = f"{rec.id} {filename}:{rec.line}:{rec.column}: {rec.severity} [{rec.code}] {rec.message}"
    if rec.caused_by:
        text += f" (caused by {rec.caused_by})"
    return text


def format_cluster(filename: str, cluster: Cluster) -> str:
    """The root's line, plus `` (+N related)`` when the cluster has symptoms."""
    text = format_record(filename, cluster.root)
    if cluster.symptoms:
        text += f" (+{len(cluster.symptoms)} related)"
    return text


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # never crash on a console that cannot show a character
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(prog="python -m cea", description="Compile a C-subset file and report its errors.")
    ap.add_argument("file", help="path to a .c file")
    ap.add_argument("--json", action="store_true", help="print the error records and clusters as JSON")
    ap.add_argument("--all", action="store_true", help="list every record, not just one root per cluster")
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
                   "errors": [r.to_dict() for r in result.errors],
                   "clusters": [{"root_id": c.root.id, "symptom_ids": [s.id for s in c.symptoms]}
                                for c in result.clusters]}
        print(json.dumps(payload, indent=2))
    else:
        if args.all:
            for rec in result.errors:
                print(format_record(path.name, rec))
        else:
            for cluster in result.clusters:
                print(format_cluster(path.name, cluster))
        print(result.summary())
    return 0 if result.ok else 1
```

The summary line stays the raw F4 count ("9 fatal, 0 warnings"): F4 counts every record; F2 changes what is listed, not what is counted.

3b. `tests/unit/test_pipeline_cli.py`: insert these four tests directly ABOVE `def test_cli_warnings_only_exits_0():` (two blank lines between functions):

```python
def test_cli_json_has_clusters_array():
    proc = _run_cli(str(CORPUS / "dev" / "043-loop-counter-never-declared.c"), "--json")
    assert proc.returncode == 1, proc.stderr
    data = json.loads(proc.stdout)
    assert len(data["errors"]) == 9                                    # --json stays complete
    assert data["clusters"] == [{"root_id": "E-0001",
                                 "symptom_ids": [f"E-{n:04d}" for n in range(2, 10)]}]


def test_cli_text_shows_roots_with_related_count():
    proc = _run_cli(str(CORPUS / "dev" / "043-loop-counter-never-declared.c"))
    assert proc.returncode == 1, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("E-0001 043-loop-counter-never-declared.c:6:10: fatal [SEM-UNDECLARED-VAR]")
    assert lines[0].endswith("(+8 related)")
    assert lines[-1] == "9 fatal, 0 warnings"


def test_cli_all_lists_every_record():
    proc = _run_cli(str(CORPUS / "dev" / "043-loop-counter-never-declared.c"), "--all")
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 10 and not any("related" in ln for ln in lines)


def test_cli_root_without_symptoms_has_no_count():
    proc = _run_cli(str(CORPUS / "dev" / "063-fault-plus-warning.c"))
    lines = proc.stdout.strip().splitlines()
    assert [ln.split()[0] for ln in lines[:-1]] == ["E-0001", "E-0002"]
    assert not any("related" in ln for ln in lines)
```

**Verify**:
- `PYTHONPATH=src .venv/Scripts/python -m cea tests/corpus/dev/043-loop-counter-never-declared.c` prints exactly two lines:
  ```
  E-0001 043-loop-counter-never-declared.c:6:10: fatal [SEM-UNDECLARED-VAR] Variable 'i' is used before it is declared (+8 related)
  9 fatal, 0 warnings
  ```
  and exits 1.
- `.venv/Scripts/python -m pytest -q tests/unit/test_pipeline_cli.py` → `101 passed`
- `.venv/Scripts/python -m pytest -q` → `881 passed, 20 deselected`
- `.venv/Scripts/python -m pytest -q tests/unit/test_no_print.py` → `3 passed`

Commit: `cea: CLI shows F2 roots with related counts; JSON clusters (plan 009 step 3)`, staging `src/cea/cli.py tests/unit/test_pipeline_cli.py`.

### Step 4: `tools/metrics_f2.py` and its tests

4a. Create `tools/metrics_f2.py`, exact content:

```python
"""F2 clustering metric: raw vs displayed error counts over the cascade set (plan 009).

The cascade set is the corpus programs whose sidecar has ``"cascading": true``
(plans/README.md, "F2 metric definition"). For each one this prints the raw
record count, the displayed count (number of F2 roots = clusters) and the
expected displayed count, then the totals and the reduction. Expected
displayed is 1 for a single-fault file (plan 002 section 10, part (b)); for a
multi-fault file it is every expected F2 root: the sidecar ``roots`` plus the
sidecar ``warnings`` (a warning with no cause is its own root). Stdlib only.

Usage (from the project root):
    python tools/metrics_f2.py                       # dev split (default)
    python tools/metrics_f2.py --split heldout --i-am-milestone-5

The held-out split is evaluation-only (tests/corpus/README.md section 5): without
``--i-am-milestone-5`` this script refuses before reading any held-out file.
Exit status: 0 on success, 2 on refusal or a usage error.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cea.pipeline import compile_source  # noqa: E402

CORPUS = ROOT / "tests" / "corpus"


def measure(split):
    """Rows (name, raw, displayed, expected_displayed, single_fault) for the cascade set of one split."""
    rows = []
    for c_path in sorted((CORPUS / split).glob("*.c")):
        side = json.loads(c_path.with_name(c_path.stem + ".expected.json").read_text(encoding="utf-8"))
        if not side["cascading"]:
            continue
        result = compile_source(c_path.read_text(encoding="utf-8"), c_path.name)
        single = len(side["injected_faults"]) == 1
        expected = 1 if single else len(side["roots"]) + len(side["warnings"])
        rows.append((c_path.name, len(result.errors), len(result.clusters), expected, single))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python tools/metrics_f2.py", description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=("dev", "heldout"), default="dev")
    ap.add_argument("--i-am-milestone-5", dest="milestone5", action="store_true",
                    help="required for --split heldout (evaluation only)")
    args = ap.parse_args(argv)
    if args.split == "heldout" and not args.milestone5:
        print("REFUSED: the heldout split is evaluation-only (tests/corpus/README.md section 5); "
              "pass --i-am-milestone-5 at milestone 5", file=sys.stderr)
        return 2
    rows = measure(args.split)
    print(f"F2 metric, split={args.split}, cascade set = {len(rows)} programs")
    print(f"{'program':<48} {'raw':>4} {'shown':>5} {'want':>4}  check")
    for name, raw, shown, want, single in rows:
        print(f"{name:<48} {raw:>4} {shown:>5} {want:>4}  {'ok' if shown == want else 'MISMATCH'}")
    raw_total = sum(r[1] for r in rows)
    shown_total = sum(r[2] for r in rows)
    single_rows = [r for r in rows if r[4]]
    single_ok = sum(1 for r in single_rows if r[2] == 1)
    reduction = 100.0 * (raw_total - shown_total) / raw_total if raw_total else 0.0
    print(f"TOTAL raw={raw_total} displayed={shown_total} reduction={reduction:.1f}%")
    single_raw = sum(r[1] for r in single_rows)
    single_shown = sum(r[2] for r in single_rows)
    single_red = 100.0 * (single_raw - single_shown) / single_raw if single_raw else 0.0
    print(f"SINGLE-FAULT raw={single_raw} displayed={single_shown} reduction={single_red:.1f}%")
    print(f"part (b): {single_ok}/{len(single_rows)} single-fault programs display exactly 1 root")
    mismatches = sum(1 for r in rows if r[2] != r[3])
    print(f"mismatches: {mismatches}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

4b. Create `tests/unit/test_metrics_f2.py`, exact content:

```python
"""tools/metrics_f2.py (plan 009): the F2 metric over the dev cascade set, and the held-out guard."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "metrics_f2.py"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=ROOT)


def test_dev_metrics_totals():
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.splitlines()
    assert out[0] == "F2 metric, split=dev, cascade set = 15 programs"
    assert "TOTAL raw=50 displayed=20 reduction=60.0%" in out
    assert "SINGLE-FAULT raw=40 displayed=11 reduction=72.5%" in out
    assert "part (b): 11/11 single-fault programs display exactly 1 root" in out
    assert out[-1] == "mismatches: 0"


def test_heldout_is_refused_without_the_flag():
    proc = _run("--split", "heldout")
    assert proc.returncode == 2
    assert "REFUSED" in proc.stderr and proc.stdout == ""
```

**Verify**:
- `.venv/Scripts/python tools/metrics_f2.py` → exactly the 21-line table in "Advisor's verification"; exit 0.
- `.venv/Scripts/python tools/metrics_f2.py --split heldout; echo "exit=$?"` → `REFUSED: ...` on stderr, then `exit=2`. (This reads no held-out file; the refusal happens before any file access.)
- `.venv/Scripts/python -m pytest -q` → `883 passed, 20 deselected`
- `.venv/Scripts/python tools/check_spec.py` → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`

Commit: `tools: F2 metric script over the cascade set (plan 009 step 4)`, staging `tools/metrics_f2.py tests/unit/test_metrics_f2.py`.

### Step 5: Status row

In `plans/README.md`, "Milestone 2" table, set row 009's Status to `DONE (883 passed; dev cascade 50 raw -> 20 displayed)`. Commit `plans: 009 done`, staging `plans/README.md`.

## Test plan

- `tests/unit/test_cluster.py` (16 tests): the trace roots of `docs/error-recovery.md` §9 for T2, T4, T5, T6, T8, T9 (covering rule 1 via R1/R2/R5/R7/R8/R9, rule 2, rule 3); same-name undeclared grouping within one function vs across two functions; file-scope grouping; rule 2 needs the same code AND name; rule 2 never applies to other codes; caused_by chains; caused_by beats rule 2; idempotence; `roots()` order and `cluster_view()` partition; empty input.
- `tests/test_recovery_traces.py`: all 10 traces now compare the real `root_id`, the displayed count from `result.clusters`, and that clusters partition the records.
- `tests/test_corpus_compile.py`: exact fatal-root equality for 54 dev + 12 valid.
- `tests/unit/test_pipeline_cli.py`: 4 new CLI tests (JSON clusters, "+N related", `--all`, no count for a lone root).
- `tests/unit/test_metrics_f2.py`: dev totals and the held-out refusal.
- Final: `883 passed, 20 deselected` (861 + 16 + 4 + 2).

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` → `883 passed, 20 deselected`
- [ ] `.venv/Scripts/python -m pytest -q tests/test_corpus_compile.py` → `66 passed, 20 deselected`
- [ ] `.venv/Scripts/python tools/metrics_f2.py | tail -4` → `TOTAL raw=50 displayed=20 reduction=60.0%`, `SINGLE-FAULT raw=40 displayed=11 reduction=72.5%`, `part (b): 11/11 ...`, `mismatches: 0`
- [ ] `.venv/Scripts/python tools/metrics_f2.py --split heldout` exits 2
- [ ] `.venv/Scripts/python tools/check_spec.py` → `OK: 37 codes, ...`
- [ ] `git diff --name-only main..HEAD` lists only the 12 in-scope paths; `git diff main..HEAD -- tests/corpus/dev tests/corpus/valid tests/corpus/heldout` is empty
- [ ] `plans/README.md` row 009 updated

## STOP conditions

Stop and report (do not improvise) if:
- Any drift check fails.
- **Any dev or valid program fails the exact-root check in Step 2.** Do NOT edit the sidecar and do NOT add a clustering rule. Report the program, the sidecar `roots`, and the full record list from the assertion message (id, code, line, found, caused_by, root_id). The advisor decides whether the sidecar, a `caused_by` rule or the clustering rule is wrong.
- `tools/metrics_f2.py` output differs from the advisor's table (any row, the totals, or `mismatches` not 0).
- A trace in `tests/test_recovery_traces.py` fails with the real `root_id`: the clustering disagrees with `docs/error-recovery.md` §9.
- Making a test pass seems to need a change to `lexer.py`, `parser.py`, `semantic.py`, any doc in `docs/`, or a sidecar.
- You are tempted to merge errors "in the same block" or "same statement" beyond `caused_by`: the contract forbids it.
- Anything would require reading `tests/corpus/heldout/`.

## Maintenance notes

- `assign_roots` is the only writer of `root_id` after the sink creates a record. The sink still initialises `root_id = id`; clustering overwrites it. Code that builds records by hand (tests) must call `assign_roots` itself.
- Plan 012's `POST /api/compile` should serialise `result.clusters` exactly as the CLI's `--json` does (`{root_id, symptom_ids}`); reuse the same comprehension.
- The F2 total over the dev cascade set is 60.0%, below the PRD's "at least 70% fewer displayed errors on cascading test files". The single-fault subset reaches 72.5%. The gap comes from the 4 multi-fault files (raw 10, displayed 9), where every fault is a genuine root. This is the measurement plan 002 §10 asked for; the PRD target wording is an owner decision (see Open questions).
- `docs/error-recovery.md` §7 still calls the root rule "provisional" and §11 says "F2: reads `caused_by` and assigns `root_id` (provisional rule in §7)". The advisor should update both when merging.
- A reviewer should check `_scope_of`: it uses each function's full span (header included) and compares `(line, column)` tuples, so a record on a function's header line still belongs to that function.

## Open questions (advisor → owner)

1. **Contract signature.** `plans/m2-architecture.md` §2 says `assign_roots(records)`. Rule 2 needs function boundaries, which records do not carry, so this plan adds an optional keyword `program=None`. Approve, or amend the contract text to match.
2. **PRD target.** Dev cascade set: 50 raw → 20 displayed (60.0%); single-fault files only: 40 → 11 (72.5%, 11/11 show exactly one root). Should the PRD's "70% fewer" be measured on single-fault cascade files only (plan 002 §10 part (b)), or on the full set?
3. **Expected displayed for multi-fault files** is taken as sidecar `roots` + `warnings` (so `dev/063`, one fatal + one independent warning, expects 2, matching its sidecar note "2 raw, 2 displayed"). The README decision says "their number of roots"; confirm that warning roots count.
4. **`--all` flag** was added to the CLI so the full list stays reachable in text mode (JSON is always complete). Keep or drop.
5. No dev sidecar disagreed with the clustering rule, so nothing is blocked.

## Viva notes (ask the executor to report)

End your report with a **Viva notes** list covering at least: why clustering runs after all phases and only reads `caused_by` + the undeclared-name rule (deterministic, explainable, no block-wide merging that would hide independent faults); why rule 2 is scoped per function; the `program=` keyword deviation; why the F4 summary still counts raw records; the exact-root test result (66/66); and the metric numbers (60.0% overall, 72.5% single-fault, 11/11 part (b)).
