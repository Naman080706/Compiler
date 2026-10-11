"""Error nodes and broken declarations (plan 006 step 7): error-recovery
section 5 including the plan-004 'unsupported' kind_hint and declarator names."""
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


# ---------------------------------------------------------------- 5 error nodes
def test_broken_declarations_keep_their_names():
    prog, recs = parse_src(main("int a = 1, b = ;", "double c[2;", "int d = 1, 5;", "return a;"))
    s = body(prog)
    assert [(r.code, f"{r.line}:{r.column}") for r in recs] == [
        ("SYN-EXPECTED-EXPRESSION", "2:20"), ("SYN-UNBALANCED-BRACKET", "3:15"), ("SYN-EXPECTED-TOKEN", "4:16")]
    a, b = s[0].decls
    assert a.error_id is None and isinstance(a.init, A.IntLit)
    assert b.error_id == "E-0001" and b.init == A.ErrorExpr(A.Span(2, 20, 2, 20), "E-0001")
    assert b.idents_in_span == {"b"}
    (c,) = s[1].decls
    assert c.error_id == "E-0002" and isinstance(c.array_size, A.IntLit) and c.init is None
    (d,) = s[2].decls
    assert d.error_id == "E-0003" and d.name == "d"


def test_broken_global_and_broken_function():
    prog, recs = parse_src("int g = ;\nint f(void) x\nint main(void) { return 0; }\n")
    assert [(r.code, f"{r.line}:{r.column}") for r in recs] == [
        ("SYN-EXPECTED-EXPRESSION", "1:9"), ("SYN-MISSING-SEMICOLON", "2:12")]
    g, f, m = prog.decls
    assert g.decls[0].is_global and g.decls[0].error_id == "E-0001" and isinstance(g.decls[0].init, A.ErrorExpr)
    assert isinstance(f, A.FunctionDecl) and f.error_id == "E-0002" and f.body is None
    assert f.idents_in_span == {"f", "x"} and m.name == "main"


def test_unsupported_kind_hint_and_declarator_names():
    src = ("register int N = 5;\n"
           "int k;\n"
           "typedef struct { int a : 2; } Bits;\n"
           "int main(void) {\n"
           "    volatile int u = 1;\n"
           "    int (*fp)(int), t;\n"
           "    int x = 1;\n"
           "    return N;\n"
           "}\n")
    prog, recs = parse_src(src)
    assert [(r.code, f"{r.line}:{r.column}", r.found) for r in recs] == [
        ("SYN-UNSUPPORTED-FEATURE", "1:1", "register"), ("SYN-UNSUPPORTED-FEATURE", "3:24", ":"),
        ("SYN-UNSUPPORTED-FEATURE", "5:5", "volatile"), ("SYN-UNSUPPORTED-FEATURE", "6:9", "(")]
    e1, e2 = prog.decls[0], prog.decls[2]
    assert e1.kind_hint == "unsupported"
    assert (e2.kind_hint, e2.declared_names) == ("top", [("Bits", "<unsupported>")])   # the typedef name is not lost
    s = body(prog, 3)
    assert s[0].kind_hint == "unsupported" and s[0].declared_names == [] and s[0].stopped_before == "int"
    assert isinstance(s[1], A.VarDeclStmt) and s[1].decls[0].name == "u"      # 'int u = 1;' parses normally
    assert (s[2].kind_hint, s[2].declared_names) == ("decl", [("fp", "<unsupported>")])
    assert isinstance(s[3], A.VarDeclStmt) and s[3].decls[0].name == "x"


def test_declarator_names_only_for_unsupported_errors():
    prog, _ = parse_src(main("int 5 x = 1;", "return 0;"))
    err = body(prog)[0]
    assert err.kind_hint == "decl" and err.declared_names == []         # SYN-EXPECTED-TOKEN, not unsupported


def test_for_header_error_stmt_declares_loop_variable():
    prog, _ = parse_src(main("int n = 3;", "for (int i = 0, j = 1 i < n; i++) { n = i; }", "return n;"))
    assert body(prog)[1].declared_names == [("i", "int"), ("j", "int")]


def test_array_initialiser_list_parses():
    prog, recs = parse_src(main("int a[3] = {1, 2};", "return 0;"))
    assert rows(recs) == []
    init = body(prog)[0].decls[0].init
    assert isinstance(init, A.InitList) and [i.value for i in init.items] == [1, 2]


def test_broken_initialiser_list_keeps_the_declaration():
    prog, recs = parse_src(main("int a[3] = {1, ;", "return 0;"))
    assert rows(recs)[0][1:4] == ("SYN-EXPECTED-EXPRESSION", "2:20", ";")
    decl = body(prog)[0]
    assert decl.decls[0].error_id == "E-0001" and isinstance(decl.decls[0].init, A.ErrorExpr)
