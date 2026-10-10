"""Syntax-record subsets of the reference traces T1-T9 (docs/error-recovery.md
section 9). Lexical records come first in the same sink, so they take the
first ids (T5, T6). Semantic records are asserted later by plan 007."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex

TRACES = {
    "T1": "int main(void) {\n    int a = 1;\n    int b = 2\n    a = a + b;\n    return a;\n}\n",
    "T1b": "int main(void) {\n    int a = 1;\n    int b = 2 a = a + b;\n    return a;\n}\n",
    "T2": ("int f(int a) {\n    if (a > 0) {\n        a = a - 1;\n    return a;\n}\n"
           "int main(void) {\n    return f(3);\n}\n"),
    "T3": "int main(void) {\n    int x = 1;\n    if x > 0) {\n        x = 2;\n    }\n    return 0;\n}\n",
    "T5": "int main(void) {\n    int x = 5 @ 2;\n    return x;\n}\n",
    "T6": ("#include <stdio.h>\nint main(void) {\n    int count = 0;\n    printf(\"total\\q\\n\", count);\n"
           "    count = count + 1\n    result = count;\n    return 0;\n}\n"),
    "T7": ("int main(void) {\n    int i = 0;\n    while (i < 10 {\n        i = i + 1;\n        if (i == 5) {\n"
           "            break;\n        }\n    }\n    return i;\n}\n"),
    "T8": ("int main(void) {\n    int n = 2;\n    switch (n) {\n        case 1:\n            n = 5;\n"
           "            break;\n        default:\n            n = 0;\n    }\n    return n;\n}\n"),
    "T9": "int main(void) {\n    int *p;\n    p = 0;\n    return p;\n}\n",
}

# (id, code, line:col, found, expected, caused_by) for every lexical + syntax record
EXPECTED = {
    "T1": [("E-0001", "SYN-MISSING-SEMICOLON", "3:14", "a", [";"], None)],
    "T1b": [("E-0001", "SYN-MISSING-SEMICOLON", "3:14", "a", [";"], None)],
    "T2": [("E-0001", "SYN-UNBALANCED-BRACKET", "6:1", "int", ["}"], None)],
    "T3": [("E-0001", "SYN-EXPECTED-TOKEN", "3:8", "x", ["("], None)],
    "T5": [("E-0001", "LEX-INVALID-CHAR", "2:15", "@", [], None),
           ("E-0002", "SYN-MISSING-SEMICOLON", "2:14", "2", [";"], "E-0001")],
    "T6": [("E-0001", "LEX-INVALID-ESCAPE", "4:18", "\\q", [], None),
           ("E-0002", "SYN-MISSING-SEMICOLON", "5:22", "result", [";"], None)],
    "T7": [("E-0001", "SYN-UNBALANCED-BRACKET", "3:19", "{", [")"], None)],
    "T8": [("E-0001", "SYN-UNSUPPORTED-FEATURE", "3:5", "switch", [], None),
           ("E-0002", "SYN-UNSUPPORTED-FEATURE", "4:9", "case", [], "E-0001"),
           ("E-0003", "SYN-UNSUPPORTED-FEATURE", "7:9", "default", [], "E-0001")],
    "T9": [("E-0001", "SYN-UNSUPPORTED-FEATURE", "2:9", "*", [P.IDENT], None)],
}


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


def run(name):
    src = TRACES[name]
    sink = ErrorSink(src)
    return P.parse(lex(src, sink), sink), sink.records


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_trace_records(name):
    _, recs = run(name)
    got = [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.expected, r.caused_by) for r in recs]
    assert got == EXPECTED[name]


def test_t1b_broken_declaration():
    prog, _ = run("T1b")
    b = prog.decls[0].body.stmts[1].decls[0]
    assert (b.name, b.type_name, b.error_id, b.idents_in_span) == ("b", "int", "E-0001", {"a", "b"})


def test_t2_body_closed_by_repair():
    prog, _ = run("T2")
    f, m = prog.decls
    assert f.body.closed_by_repair == "E-0001" and m.name == "main" and m.body.closed_by_repair is None


def test_t3_error_stmt_and_orphan_block():
    prog, _ = run("T3")
    err, orphan = prog.decls[0].body.stmts[1:3]
    assert err == A.ErrorStmt(A.Span(3, 5, 3, 13), "E-0001", "if", [], {"x"}, "{")
    assert isinstance(orphan, A.Block) and orphan.orphan_of == "E-0001"


def test_t7_while_kept_with_condition_and_body():
    prog, _ = run("T7")
    loop = prog.decls[0].body.stmts[1]
    assert isinstance(loop, A.While) and loop.cond.op == "<"
    assert isinstance(loop.body.stmts[1].then.stmts[0], A.Break)


def test_t8_unsupported_orphan_body():
    prog, _ = run("T8")
    err, orphan = prog.decls[0].body.stmts[1:3]
    assert (err.kind_hint, err.stopped_before, err.declared_names) == ("unsupported", "{", [])
    assert orphan.orphan_of == "E-0001"
    assert [type(s).__name__ for s in orphan.stmts] == ["ErrorStmt", "Break", "ErrorStmt"]


def test_t9_declarator_name_recovered():
    prog, _ = run("T9")
    err = prog.decls[0].body.stmts[0]
    assert (err.kind_hint, err.declared_names) == ("decl", [("p", "<unsupported>")])


# The catalog's 'Example trigger' column, one row per SYN code, plus the two language-spec 6 cases.
# ---------------------------------------------------------------- catalog example triggers
@pytest.mark.parametrize("src,want", [
    (main("int x = 5", "return x;"), ("SYN-MISSING-SEMICOLON", "2:14", "return")),
    (main("int x = 2;", "if (x > 1 { }", "return 0;"), ("SYN-UNBALANCED-BRACKET", "3:15", "{")),
    (main("int x = 2;", "while x > 1) { }", "return 0;"), ("SYN-EXPECTED-TOKEN", "3:11", "x")),
    (main("int x = ;", "return 0;"), ("SYN-EXPECTED-EXPRESSION", "2:13", ";")),
    ("int f(a) { }\n", ("SYN-EXPECTED-TYPE", "1:7", "a")),
    ("int main() { return 0;", ("SYN-UNEXPECTED-EOF", "1:23", "EOF")),
    (main("int x = 1;", "5 = x;", "return 0;"), ("SYN-INVALID-ASSIGN-TARGET", "3:7", "=")),
    (main("int *p;", "return 0;"), ("SYN-UNSUPPORTED-FEATURE", "2:9", "*")),
    # language-spec 6: no special case; ordinary selection rules
    (main("int a[3] = {1, 2};", "return 0;"), ("SYN-EXPECTED-EXPRESSION", "2:16", "{")),
    ("int f(int a[]) { return 0; }\n", ("SYN-EXPECTED-TOKEN", "1:12", "[")),
])
def test_catalog_example_triggers(src, want):
    sink = ErrorSink(src)
    P.parse(lex(src, sink), sink)
    first = [r for r in sink.records if r.phase == "syntax"][0]
    assert (first.code, f"{first.line}:{first.column}", first.found) == want
