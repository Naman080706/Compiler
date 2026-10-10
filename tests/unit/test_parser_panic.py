"""Panic modes and sync sets (plan 006 step 5): statement-level, for-header
and top-level panic (error-recovery 4.4) and the ErrorStmt they produce."""
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


def test_missing_semicolon_same_line_panics():
    prog, recs = parse_src(main("int a = 1;", "a = 2 a = 3;", "return a;"))
    assert rows(recs) == [("E-0001", "SYN-MISSING-SEMICOLON", "3:10", "a", None)]
    st = body(prog)[1]
    assert isinstance(st, A.ErrorStmt) and st.kind_hint == "expr" and st.stopped_before is None
    assert st.span == A.Span(3, 5, 3, 16) and st.idents_in_span == {"a"}


def test_missing_paren_before_non_brace_is_ordinary_error():
    prog, recs = parse_src(main("int i = 0;", "if (i < 3 i = 1;", "return i;"))
    assert rows(recs) == [("E-0001", "SYN-UNBALANCED-BRACKET", "3:15", "i", None)]
    assert isinstance(body(prog)[1], A.ErrorStmt)


# ---------------------------------------------------------------- 4.4 panic modes
def test_statement_panic_stops_before_sync_token():
    prog, recs = parse_src(main("int x = 1;", "x = x + ) if (x) { x = 2; }", "return x;"))
    assert rows(recs) == [("E-0001", "SYN-UNBALANCED-BRACKET", "3:13", ")", None)]
    err, nxt = body(prog)[1], body(prog)[2]
    assert isinstance(err, A.ErrorStmt) and err.stopped_before == "if" and err.kind_hint == "expr"
    assert isinstance(nxt, A.If)


def test_for_header_panic_consumes_header_close_paren():
    prog, recs = parse_src(main("int n = 3;", "for (int i = 0 i < n; i++) {", "n = n + i;", "}", "return n;"))
    assert rows(recs) == [("E-0001", "SYN-MISSING-SEMICOLON", "3:19", "i", None)]
    err, block = body(prog)[1], body(prog)[2]
    assert isinstance(err, A.ErrorStmt) and err.kind_hint == "for" and err.stopped_before == "{"
    assert err.idents_in_span == {"i", "n"} and err.span == A.Span(3, 5, 3, 30)
    assert isinstance(block, A.Block)


def test_for_header_panic_counts_nested_parens():
    prog, recs = parse_src(main("int n = 3;", "for (n = (1 + ; (n)); n++) n = 1;", "return n;"))
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-EXPRESSION", "3:19", ";", None)]
    assert body(prog)[1].stopped_before == "n"                # stopped after the header's own ')'
    assert isinstance(body(prog)[2], A.ExprStmt)


def test_top_level_panic_resyncs_at_type_keyword_first_on_line():
    src = ("int f(a, int b) {\n"
           "    int c = b;\n"                    # indented 'int' at depth 1: not a sync point
           "    return c;\n"
           "}\n"
           "int main(void) { return 0; }\n")
    prog, recs = parse_src(src)
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-TYPE", "1:7", "a", None)]
    err, m = prog.decls
    assert isinstance(err, A.ErrorStmt) and err.kind_hint == "top"
    assert err.declared_names == [("f", "function")] and err.stopped_before == "int"
    assert err.span == A.Span(1, 1, 4, 1) and m.name == "main"


def test_stray_closing_brace_at_top_level():
    prog, recs = parse_src("int main(void) { return 0; }\n}\nint g;\n")
    assert rows(recs) == [("E-0001", "SYN-UNBALANCED-BRACKET", "2:1", "}", None)]
    assert recs[0].rule_ref == "type_spec"
    assert [type(d).__name__ for d in prog.decls] == ["FunctionDecl", "ErrorStmt", "VarDeclStmt"]


def test_brackets_opened_in_a_failed_statement_are_forgotten():
    prog, recs = parse_src(main("int x = 1;", "x = (1 + ;", ");", "return x;"))
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-EXPRESSION", "3:14", ";", None),
                          ("E-0002", "SYN-UNBALANCED-BRACKET", "4:5", ")", None)]   # stray: its '(' was dropped
