"""Happy-path grammar (plan 006 step 3): docs/language-spec.md section 2 on
valid input. Every tests/corpus/valid program must parse with zero syntax
records and the expected top-level structure."""
import re
from pathlib import Path

import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex

ROOT = Path(__file__).resolve().parents[2]
VALID = sorted((ROOT / "tests" / "corpus" / "valid").glob("*.c"))
FUNC_HEADER = re.compile(r"^(?:int|float|double|char|void)\s+([A-Za-z_]\w*)\s*\(", re.M)


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, [r for r in sink.records if r.phase == "syntax"]


def sx(e):
    """Compact s-expression of an expression, for precedence checks."""
    if isinstance(e, (A.IntLit, A.FloatLit)):
        return str(e.value)
    if isinstance(e, A.CharLit):
        return repr(e.value)
    if isinstance(e, A.StringLit):
        return '"' + e.value + '"'
    if isinstance(e, A.Name):
        return e.name
    if isinstance(e, A.Unary):
        return f"({e.op}{'post' if e.postfix else ''} {sx(e.operand)})"
    if isinstance(e, (A.Binary, A.Assign)):
        left = e.left if isinstance(e, A.Binary) else e.target
        right = e.right if isinstance(e, A.Binary) else e.value
        return f"({e.op} {sx(left)} {sx(right)})"
    if isinstance(e, A.Call):
        return f"(call {sx(e.callee)}{''.join(' ' + sx(a) for a in e.args)})"
    if isinstance(e, A.Index):
        return f"(idx {sx(e.base)} {sx(e.index)})"
    return type(e).__name__


def expr_of(src_expr):
    prog, syn = parse_src(f"int main(void) {{ {src_expr}; }}")
    assert syn == []
    return prog.decls[0].body.stmts[0].expr


def walk(node):
    yield node
    if isinstance(node, list):
        for x in node:
            yield from walk(x)
    elif hasattr(node, "__dataclass_fields__"):
        for name in node.__dataclass_fields__:
            v = getattr(node, name)
            if isinstance(v, list) or hasattr(v, "__dataclass_fields__"):
                yield from walk(v)


@pytest.mark.parametrize("src,want", [
    ("a = b = c", "(= a (= b c))"),                       # assignment is right-associative
    ("a += b || c && d", "(+= a (|| b (&& c d)))"),
    ("a == b < c + d * e", "(== a (< b (+ c (* d e))))"),
    ("a - b - c", "(- (- a b) c)"),                       # binary levels are left-associative
    ("a != b == c", "(== (!= a b) c)"),
    ("-a * !b % c", "(% (* (- a) (! b)) c)"),
    ("++i + j--", "(+ (++ i) (--post j))"),
    ("f(1, x[2]) / (a + b)", "(/ (call f 1 (idx x 2)) (+ a b))"),
    ("printf(\"%d\\n\", n)", "(call printf \"%d\n\" n)"),
    ("x = 'c' + 2.5", "(= x (+ 'c' 2.5))"),
    ("a[i] = a[i - 1] % 2", "(= (idx a i) (% (idx a (- i 1)) 2))"),
])
def test_operator_precedence(src, want):
    assert sx(expr_of(src)) == want


def test_top_decl_disambiguation_and_params():
    prog, syn = parse_src("int g = 1, h[3];\nint f(void);\nint k();\n"
                          "double m(int a, char b) { return a; }\nvoid z(void) { }\n")
    assert syn == []
    g, f, k, m, z = prog.decls
    assert isinstance(g, A.VarDeclStmt) and [(d.name, d.is_global) for d in g.decls] == [("g", True), ("h", True)]
    assert isinstance(g.decls[1].array_size, A.IntLit) and isinstance(g.decls[0].init, A.IntLit)
    assert (f.name, f.params, f.body) == ("f", [], None)          # (void) -> [] ; prototype -> body None
    assert (k.name, k.params, k.body) == ("k", [], None)
    assert [(p.type_name, p.name) for p in m.params] == [("int", "a"), ("char", "b")]
    assert m.ret_type == "double" and isinstance(m.body, A.Block)
    assert (m.name_pos.line, m.name_pos.column) == (4, 8)
    assert z.body.stmts == []


def test_statements_and_dangling_else():
    src = ("int main(void) {\n"
           "    int i, a[4];\n"
           "    for (int j = 0; j < 4; j++) a[j] = j;\n"
           "    for (;;) { break; }\n"
           "    while (i) { continue; }\n"
           "    if (i) if (a[0]) i = 1; else i = 2;\n"
           "    { ; }\n"
           "    return;\n"
           "}\n")
    prog, syn = parse_src(src)
    assert syn == []
    s = prog.decls[0].body.stmts
    assert [type(x).__name__ for x in s] == ["VarDeclStmt", "For", "For", "While", "If", "Block", "Return"]
    assert isinstance(s[1].init, A.VarDeclStmt) and s[1].init.decls[0].name == "j"
    assert (s[2].init, s[2].cond, s[2].step) == (None, None, None)
    assert isinstance(s[2].body.stmts[0], A.Break) and isinstance(s[3].body.stmts[0], A.Continue)
    assert s[4].els is None and isinstance(s[4].then, A.If) and s[4].then.els is not None   # else binds nearest
    assert isinstance(s[5].stmts[0], A.EmptyStmt) and s[6].value is None


def test_spans_are_inclusive_and_one_based():
    prog, _ = parse_src("int main(void) {\n    return 42;\n}\n")
    fn = prog.decls[0]
    assert fn.span == A.Span(1, 1, 3, 1)
    assert fn.body.stmts[0].span == A.Span(2, 5, 2, 14)          # 'return' .. ';'
    assert fn.body.stmts[0].value.span == A.Span(2, 12, 2, 13)


def test_empty_file_gives_empty_program():
    prog, syn = parse_src("")
    assert prog.decls == [] and syn == [] and prog.span == A.Span(1, 1, 1, 1)


@pytest.mark.parametrize("path", VALID, ids=[p.name for p in VALID])
def test_valid_corpus_parses_cleanly(path):
    src = path.read_text(encoding="utf-8")
    prog, syn = parse_src(src)
    assert syn == [], [(r.code, r.line, r.column) for r in syn]
    nodes = list(walk(prog))
    assert not any(isinstance(n, (A.ErrorStmt, A.ErrorExpr)) for n in nodes)
    assert not any(isinstance(n, A.Block) and (n.orphan_of or n.closed_by_repair) for n in nodes)
    funcs = [d for d in prog.decls if isinstance(d, A.FunctionDecl)]
    assert [f.name for f in funcs] == FUNC_HEADER.findall(src)
    assert all(f.error_id is None for f in funcs) and any(f.name == "main" for f in funcs)
    assert all(isinstance(d, (A.FunctionDecl, A.VarDeclStmt)) for d in prog.decls)


def test_deep_nesting_does_not_hit_recursion_limit():
    import sys
    before = sys.getrecursionlimit()
    depth = 200
    e = expr_of("x = " + "(" * depth + "1" + ")" * depth)
    assert sx(e) == "(= x 1)" and sys.getrecursionlimit() == before


def test_program_span_ends_at_eof_position():
    prog, _ = parse_src("int main(void) { return 0; }")
    assert prog.span == A.Span(1, 1, 1, 29)                   # EOF is right after the final '}'
    prog, _ = parse_src("\n\nint main(void) {\n    return 0;\n}\n")
    assert prog.span == A.Span(1, 1, 5, 2)
