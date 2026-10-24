"""Tests for the three AST tools (cea.transform): format, constant folding, structural diff."""
from cea.pipeline import compile_source
from cea.transform import ast_diff, fold_constants, format_source

PROGRAMS = [
    "int main(void){int x=2*60*60; return x;}",
    "#include <stdio.h>\nint add(int a,int b){return a+b;}\n"
    "int main(void){for(int i=0;i<3;i++){printf(\"%d\",i);} if(add(1,2)>2){return 1;}else{return 0;}}",
    "struct P{int x;int y;};\ntypedef struct P P;\nint main(void){P p; p.x=3; int a[2]={1,2}; return a[0]+p.x;}",
]


def _fatals(src: str) -> int:
    r = compile_source(src, "input.c", engine="cea")
    return sum(1 for e in r.errors if e.severity == "fatal")


def test_format_is_valid_and_idempotent():
    for src in PROGRAMS:
        first = format_source(src)
        assert first["ok"], first["reason"]
        assert _fatals(first["formatted"]) == 0           # the reformatted program still compiles cleanly
        again = format_source(first["formatted"])
        assert again["formatted"] == first["formatted"]   # formatting is a fixed point


def test_format_preserves_preprocessor_and_typedef():
    out = format_source(PROGRAMS[1])["formatted"]
    assert "#include <stdio.h>" in out
    assert "typedef struct P P;" in format_source(PROGRAMS[2])["formatted"]


def test_format_refuses_a_broken_program():
    out = format_source("int main(void){ return }")  # missing expression / ';'
    assert out["ok"] is False and out["formatted"] == "" and out["reason"]


def test_fold_computes_maximal_constant_expressions():
    folds = fold_constants("int main(void){int a=2*60*60; int b=(5+3)*2; int c=10%3; return a+b+c;}")["folds"]
    by_text = {f["text"]: f["value"] for f in folds}
    assert by_text["2 * 60 * 60"] == "7200"
    assert by_text["(5 + 3) * 2"] == "16"
    assert by_text["10 % 3"] == "1"
    # a+b+c is not constant (names), so it is not reported
    assert all("a" not in f["text"] for f in folds)


def test_fold_skips_division_by_zero():
    assert fold_constants("int main(void){return 1/0;}")["folds"] == []


def test_astdiff_ignores_formatting_but_shows_structure():
    same = ast_diff("int main(void){return 1+2;}", "int   main ( void ) {\n  return 1+2 ;\n}")
    assert same["changed"] is False
    diff = ast_diff("int main(void){return 1;}", "int main(void){int x=5; return x;}")
    assert diff["changed"] is True
    assert any(r["tag"] == "add" and "VarDecl" in r["text"] for r in diff["rows"])
