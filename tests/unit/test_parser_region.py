"""Uncertain region and caused_by for syntax records (plan 006 step 6):
error-recovery 4.5 and rules R2, then R1, then R9 (section 7, plan 004)."""
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


# ---------------------------------------------------------------- 4.5 region, R1/R2/R9
def test_region_links_follow_on_errors_until_semicolon():
    prog, recs = parse_src(main("int x = 1;", "if x > 0) { x = ; }", "x = ;", "return x;"))
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-TOKEN", "3:8", "x", None),
                          ("E-0002", "SYN-EXPECTED-EXPRESSION", "3:21", ";", "E-0001"),
                          ("E-0003", "SYN-EXPECTED-EXPRESSION", "4:9", ";", None)]


def test_r1_lex_gap_links_syntax_record():
    prog, recs = parse_src(main("int x = 1;", "x = @;", "return x;"))
    assert [(r.code, f"{r.line}:{r.column}", r.caused_by) for r in recs] == [
        ("LEX-INVALID-CHAR", "3:9", None), ("SYN-EXPECTED-EXPRESSION", "3:10", "E-0001")]


def test_r9_links_errors_in_unsupported_orphan_body_only():
    src = main("int n = 1;", "register {", "n = 2;", "goto a;", "{ goto b; }", "}", "goto c;", "return n;")
    prog, recs = parse_src(src)
    assert rows(recs) == [
        ("E-0001", "SYN-UNSUPPORTED-FEATURE", "3:5", "register", None),
        ("E-0002", "SYN-UNSUPPORTED-FEATURE", "5:5", "goto", "E-0001"),    # R9 (region closed by 'n = 2;')
        ("E-0003", "SYN-UNSUPPORTED-FEATURE", "6:7", "goto", None),        # inner block is not the orphan
        ("E-0004", "SYN-UNSUPPORTED-FEATURE", "8:5", "goto", None)]        # outside the orphan body
    assert body(prog)[1].kind_hint == "unsupported" and body(prog)[2].orphan_of == "E-0001"


def test_top_level_panic_closes_region_at_sync_keyword():
    prog, recs = parse_src("int f(a) { return 0; }\nint main(void) { int x = ; return 0; }\n")
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-TYPE", "1:7", "a", None),
                          ("E-0002", "SYN-EXPECTED-EXPRESSION", "2:26", ";", None)]


def test_orphan_block_after_panic():
    prog, recs = parse_src(main("int n = 3;", "for (int i = 0 i < n; i++) {", "n = n + i;", "}",
                                "while n) { n = 1; }", "{ n = 2; }", "return n;"))
    assert [r.id for r in recs] == ["E-0001", "E-0002"]
    s = body(prog)
    assert s[2].orphan_of == "E-0001" and s[4].orphan_of == "E-0002"
    assert s[5].orphan_of is None                       # not preceded by a panic stop
