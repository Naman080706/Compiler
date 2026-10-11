"""Phrase-level repairs (plan 006 step 4): missing ';' (error-recovery 4.2),
missing ')' before '{' (4.3) and missing '}' (4.7), plus EOF inside blocks (4.4)."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, sink.records


def rows(records):
    return [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
            for r in records if r.phase == "syntax"]


def body(prog, i=0):
    return prog.decls[i].body.stmts


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


# ---------------------------------------------------------------- 4.2 / 4.3 / 4.7
def test_missing_semicolon_repair_at_every_site():
    src = ("int p(void)\n"                    # S1 prototype
           "int g = 1\n"                      # S2 global
           "int main(void) {\n"
           "    int a = 1\n"                  # S3
           "    for (a = 0\n"                 # S4
           "         a < 3\n"                 # S5
           "         a++) { }\n"
           "    a = 2\n"                      # S9
           "    while (a) { break\n"          # S7
           "    continue\n"                   # S8
           "    }\n"
           "    return a\n"                   # S6
           "}\n")
    prog, recs = parse_src(src)
    assert [(c, lc) for _, c, lc, _, _ in rows(recs)] == [("SYN-MISSING-SEMICOLON", lc) for lc in (
        "1:12", "2:10", "4:14", "5:15", "6:15", "8:10", "9:22", "10:13", "12:13")]
    assert all(cb is None for *_, cb in rows(recs))                    # repairs never open a region
    assert not any(isinstance(s, A.ErrorStmt) for s in body(prog, 2))
    assert isinstance(body(prog, 2)[1], A.For)


def test_missing_paren_before_brace_keeps_if_while_for():
    prog, recs = parse_src(main("int i = 0;", "if (i < 3 { i = 1; }", "while (i {", "break;", "}",
                                "for (i = 0; i < 2; i++ { continue; }", "return i;"))
    assert [(c, lc, f) for _, c, lc, f, _ in rows(recs)] == [
        ("SYN-UNBALANCED-BRACKET", "3:15", "{"), ("SYN-UNBALANCED-BRACKET", "4:14", "{"),
        ("SYN-UNBALANCED-BRACKET", "7:28", "{")]
    assert recs[0].message == "Unbalanced bracket at '{': expected ')' to close '(' from line 3"
    assert [type(s).__name__ for s in body(prog)] == ["VarDeclStmt", "If", "While", "For", "Return"]


def test_missing_brace_repair_closes_every_open_block():
    src = ("int f(int a) {\n"
           "    while (a) {\n"
           "        if (a > 2) {\n"
           "            a = a - 1;\n"
           "int main(void) {\n"
           "    return f(3);\n"
           "}\n")
    prog, recs = parse_src(src)
    assert rows(recs) == [("E-0001", "SYN-UNBALANCED-BRACKET", "5:1", "int", None)]
    assert recs[0].expected == ["}"] and recs[0].rule_ref == "statement"
    assert recs[0].message == "Unbalanced bracket at 'int': expected '}' to close '{' from line 3"
    f, m = prog.decls
    assert f.name == "f" and m.name == "main" and f.error_id is None
    assert f.body.closed_by_repair == "E-0001" and f.body.span == A.Span(1, 14, 4, 22)
    loop = f.body.stmts[0]
    assert isinstance(loop, A.While) and loop.body.closed_by_repair == "E-0001"
    inner_if = loop.body.stmts[0]
    assert isinstance(inner_if, A.If) and inner_if.then.closed_by_repair == "E-0001"
    assert isinstance(inner_if.then.stmts[0], A.ExprStmt)


def test_missing_brace_in_last_function_reports_eof_per_block():
    prog, recs = parse_src("int main(void) {\n    while (1) {\n        return 0;\n")
    assert rows(recs) == [("E-0001", "SYN-UNEXPECTED-EOF", "3:18", "EOF", None),
                          ("E-0002", "SYN-UNEXPECTED-EOF", "3:18", "EOF", "E-0001")]
    assert recs[0].expected == ["}"] and recs[0].span_end.column == 18
    assert isinstance(prog.decls[0].body.stmts[0], A.While)
