"""Progress guarantee (plan 006 step 8): the loop guard of error-recovery 4.6."""
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


# ---------------------------------------------------------------- 4.6 progress guard
def test_progress_guard_raises_in_strict_mode():
    class Stuck(P.Parser):
        def top_decl(self):                       # consumes nothing: a deliberately broken production
            return A.ErrorStmt(A.Span(1, 1, 1, 1), "E-0000", "top", [], set(), None)

    sink = ErrorSink("int x;")
    stuck = Stuck(lex("int x;", sink).tokens, sink)
    with pytest.raises(P.ProgressError):
        stuck.program()


def test_progress_guard_skips_a_token_when_not_strict(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", False)

    class Stuck(P.Parser):
        def top_decl(self):
            return A.ErrorStmt(A.Span(1, 1, 1, 1), "E-0000", "top", [], set(), None)

    sink = ErrorSink("int x;")
    stuck = Stuck(lex("int x;", sink).tokens, sink)
    assert len(stuck.program().decls) == 3                 # one forced skip per token: int, x, ;


def test_parse_never_raises_on_token_soup():
    src = "} ) ] ; , else = + int ( [ { if while for return 1 x \"s\" 'c' 2.5 & switch"
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    assert isinstance(prog, A.Program) and all(r.phase == "syntax" for r in sink.records)
