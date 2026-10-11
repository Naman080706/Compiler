"""Exact-match tests for the traced examples of docs/error-recovery.md §9 (plan 007).

Each trace is compiled with ``cea.pipeline.compile_source`` and the full record
table is compared: id, code, line:col, found, caused_by and root_id. Since
plan 009, ``root_id`` is filled by F2 clustering (``cea.cluster``), which
implements the root rule of docs/error-recovery.md §7.
"""
import pytest

from cea.pipeline import compile_source

# (name, source, [(id, code, "line:col", found, caused_by or None, root_id)])
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
