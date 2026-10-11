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
