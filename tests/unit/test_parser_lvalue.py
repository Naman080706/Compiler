"""SYN-INVALID-ASSIGN-TARGET (plan 006 step 9): the lvalue rule of language-spec 2."""
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


# ---------------------------------------------------------------- lvalues
@pytest.mark.parametrize("stmt,col,found", [
    ("5 = x;", 7, "="), ("x + 1 = 2;", 11, "="), ("(x) = 1;", 9, "="), ("a[1][2] = 3;", 13, "="),
    ("f(x) += 1;", 10, "+="), ("5++;", 6, "++"), ("--(x);", 5, "--"), ("x = 3++;", 10, "++"),
])
def test_invalid_assign_target(stmt, col, found):
    prog, recs = parse_src(main("int x = 1;", stmt, "return x;"))
    assert rows(recs) == [("E-0001", "SYN-INVALID-ASSIGN-TARGET", f"3:{col}", found, None)]
    assert recs[0].rule_ref == "assignment" and recs[0].expected == []
    assert isinstance(body(prog)[1], A.ErrorStmt)


@pytest.mark.parametrize("stmt", ["x = 1;", "a[x] = 2;", "x++;", "--a[0];", "x += a[1] = 3;"])
def test_valid_assign_targets(stmt):
    _, recs = parse_src(main("int x = 1;", "int a[2];", stmt, "return x;"))
    assert rows(recs) == []
