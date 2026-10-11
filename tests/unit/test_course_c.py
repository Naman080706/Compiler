"""Course-level C: types, pointers, structs, enums, typedefs, switch, do-while, operators, initialisers, headers."""
import pytest

from cea import ast as A
from cea.pipeline import compile_source


def run(src):
    return compile_source(src, "t.c", engine="cea")


def codes(src):
    return [(r.code, r.line) for r in run(src).errors]


def main(*lines, pre=""):
    return pre + "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "    return 0;\n}\n"


# ---------------------------------------------------------------- accepted programs
@pytest.mark.parametrize("body", [
    "long a = 1L; short b = 2; unsigned c = 3u; signed char d = 'x'; unsigned long long e = 5ull; long double f = 1.5;",
    "const int k = 3; static int s = 4; int v = k + s;",
    "int x = 1; int *p = &x; *p = 2; int y = *p + 1;",
    "int a[3] = {1, 2, 3}; int *p = a; p += 2; int d = p - a; int e = *(a + 1) + p[0];",
    "char *s = \"hi\"; const char *t = s; char u[] = \"abc\"; char v[8] = \"abc\";",
    "int m[2][3] = {{1, 2, 3}, {4, 5, 6}}; m[1][2] = m[0][1] * 2;",
    "int x = 5; int y = x > 3 ? 1 : 0; int z = (x << 2) | (x & 1) ^ ~x;",
    "int x = 5; x <<= 1; x >>= 1; x &= 3; x |= 4; x ^= 1; x %= 3;",
    "unsigned n = sizeof(int) + sizeof(long); int k = sizeof n;",
    "double d = (double)3 / 2; int i = (int)d; char c = (char)i;",
    "int i, j; for (i = 0, j = 10; i < j; i++, j--) { }",
    "int n = 0; do { n++; } while (n < 3);",
    "int n = 2; switch (n) { case 1: break; case 2: case 3: n = 0; break; default: n = 1; }",
    "int *p = 0; if (!p) { p = 0; }",
    "int a = 1, b = 2; int *p = &a, *q = &b; if (p != q && p < q || p == 0) { }",
    "enum Color { RED, GREEN = 4, BLUE }; enum Color c = BLUE; int a[BLUE]; switch (c) { case RED: break; case GREEN: break; }",
    "struct P { int x; int y; }; struct P p = {1, 2}; struct P *q = &p; q->x = p.y; struct P r = p; r = *q;",
    "union U { int i; char c; }; union U u; u.i = 65; char ch = u.c;",
    "typedef unsigned long ulong; typedef struct { int a; } Box; ulong n = 1; Box b; b.a = (int)n;",
    "struct N { int v; struct N *next; }; struct N n1; struct N n2; n1.next = &n2; n1.next->v = 3;",
    "char name[4]; char *q = name; q[0] = 'a'; *(q + 1) = 'b';",
    "double x = 0x1F + 017 + 1e1 + 2.5f;",
    "struct S { int a[2]; } s = {{1, 2}}; s.a[1] = 3;",
])
def test_accepts(body):
    assert all(c == "WRN-UNUSED-VAR" for c, _ in codes(main(body))), codes(main(body))


def test_define_constants_and_headers():
    src = ("#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <math.h>\n#include <ctype.h>\n"
           "#include <stdbool.h>\n#define N 4\n#define PI 3.14\n"
           "int main(void) {\n    int a[N];\n    double r = sqrt(PI) + pow(2, N) + fabs(-1.5);\n"
           "    char *s = malloc(N);\n    bool ok = true;\n    if (ok && isdigit('7') && strlen(s) < N) { s[0] = toupper('a'); }\n"
           "    printf(\"%f %s %d\\n\", r, s, abs(-3));\n    scanf(\"%d\", &a[0]);\n    free(s);\n    a[1] = EOF + RAND_MAX;\n    return 0;\n}\n")
    assert codes(src) == []


def test_function_forms():
    src = ("static int twice(int x) { return 2 * x; }\nint len(const char *s);\nint len(const char *s) { return 0; }\n"
           "void fill(int a[], int n) { a[0] = n; }\nint rows(int m[][3]) { return m[0][0]; }\n"
           "char *id(char *s) { return s; }\nint proto(int, char *);\n"
           "int main(int argc, char *argv[]) { int a[2]; fill(a, argc); return twice(len(argv[0])) + proto(1, 0); }\n")
    assert [c for c, _ in codes(src) if not c.startswith("WRN")] == []


# ---------------------------------------------------------------- semantic errors of the new constructs
@pytest.mark.parametrize("body,code", [
    ("int x = 1; int y = *x;", "SEM-DEREF-NON-POINTER"),
    ("int x = 1; int *p = &(x + 1);", "SEM-ADDR-OF-NON-LVALUE"),
    ("int *p = &5;", "SEM-ADDR-OF-NON-LVALUE"),
    ("double d = 1; int *p = &d;", "WRN-INCOMPATIBLE-POINTER"),
    ("int a[2]; char *p = a;", "WRN-INCOMPATIBLE-POINTER"),
    ("struct P { int x; }; struct P p; p.y = 1;", "SEM-NO-SUCH-MEMBER"),
    ("struct P { int x; }; struct P *p = 0; p->y = 1;", "SEM-NO-SUCH-MEMBER"),
    ("int n = 0; n.x = 1;", "SEM-MEMBER-ON-NON-STRUCT"),
    ("struct P { int x; }; struct P *p = 0; p.x = 1;", "SEM-MEMBER-ON-NON-STRUCT"),
    ("int n = 0; n->x = 1;", "SEM-ARROW-ON-NON-POINTER"),
    ("struct P { int x; }; struct P p; p->x = 1;", "SEM-ARROW-ON-NON-POINTER"),
    ("const int n = 1; n = 2;", "SEM-ASSIGN-TO-CONST"),
    ("const int n = 1; n++;", "SEM-ASSIGN-TO-CONST"),
    ("const char *s = \"a\"; *s = 'b';", "SEM-ASSIGN-TO-CONST"),
    ("const int a[2] = {1, 2}; a[0] = 3;", "SEM-ASSIGN-TO-CONST"),
    ("char *const p = 0; char c = 'a'; p = &c;", "SEM-ASSIGN-TO-CONST"),
    ("int n = 1; switch (n) { case 1: break; case 1: break; }", "SEM-DUPLICATE-CASE"),
    ("int n = 1; switch (n) { default: break; default: break; }", "SEM-DUPLICATE-CASE"),
    ("int n = 1; switch (n) { case 'a': break; case 97: break; }", "SEM-DUPLICATE-CASE"),
    ("int n = 1; int k = 2; switch (n) { case k: break; }", "SEM-CASE-NOT-CONSTANT"),
    ("int n = 1; switch (n) { case 1.5: break; }", "SEM-CASE-NOT-CONSTANT"),
    ("double d = 1; switch (d) { default: break; }", "SEM-SWITCH-NON-INT"),
    ("int *p = 0; switch (p) { default: break; }", "SEM-SWITCH-NON-INT"),
    ("case 1: break;", "SEM-CASE-OUTSIDE-SWITCH"),
    ("struct Q; struct Q q;", "SEM-INCOMPLETE-TYPE"),
    ("int *p = 5;", "SEM-TYPE-MISMATCH"),
    ("int *p = 0; int n = p;", "SEM-TYPE-MISMATCH"),
    ("int *p = 0; int *q = p + p;", "SEM-TYPE-MISMATCH"),
    ("struct P { int x; }; struct P p; int n = p + 1;", "SEM-TYPE-MISMATCH"),
    ("double d = 1.0; int n = d << 1;", "SEM-TYPE-MISMATCH"),
    ("double d = 1.0; int n = ~d;", "SEM-TYPE-MISMATCH"),
    ("int a[4]; int b[4]; a = b;", "SEM-TYPE-MISMATCH"),
    ("int n = 3; int a[n];", "SEM-BAD-ARRAY-SIZE"),
    ("int a[0];", "SEM-BAD-ARRAY-SIZE"),
    ("int a[];", "SEM-BAD-ARRAY-SIZE"),
    ("typedef int T; T x = 1; T y = x.z;", "SEM-MEMBER-ON-NON-STRUCT"),
])
def test_rejects_or_warns(body, code):
    got = [c for c, _ in codes(main(body))]
    assert code in got, got


def test_break_is_legal_in_switch_but_continue_is_not():
    assert "SEM-BREAK-OUTSIDE-LOOP" not in [c for c, _ in codes(main("int n = 1; switch (n) { case 1: break; }"))]
    assert "SEM-BREAK-OUTSIDE-LOOP" in [c for c, _ in codes(main("int n = 1; switch (n) { case 1: continue; }"))]
    assert "SEM-BREAK-OUTSIDE-LOOP" not in [c for c, _ in codes(main("int n = 1; while (n) { switch (n) { case 1: continue; } }"))]


def test_builtins_need_their_header():
    assert ("SEM-UNDECLARED-FUNC", 2) in codes(main("char *p = malloc(3);"))
    assert ("SEM-UNDECLARED-FUNC", 3) in codes(main("double d = sqrt(4);", pre="#include <stdio.h>\n"))
    assert codes(main("double d = sqrt(4);", pre="#include <math.h>\n")) == [("WRN-UNUSED-VAR", 3)]
    assert "SEM-UNDECLARED-VAR" in [c for c, _ in codes(main("int x = NULL == 0;"))]


def test_builtin_signatures_are_checked():
    pre = "#include <string.h>\n#include <stdio.h>\n"
    assert "SEM-ARG-COUNT" in [c for c, _ in codes(main("char a[4]; strcpy(a);", pre=pre))]
    assert "SEM-ARG-TYPE" in [c for c, _ in codes(main("int n = 1; int m = strlen(n);", pre=pre))]
    assert "SEM-PRINTF-FORMAT" in [c for c, _ in codes(main("int n = 1; printf(n);", pre=pre))]
    assert [c for c, _ in codes(main("char buf[8]; printf(buf);", pre=pre))] == []
    assert "SEM-REDECLARED" in [c for c, _ in codes("#include <string.h>\nint strlen(int x) { return x; }\n" + main())]


def test_unused_pointer_and_struct_variables_warn():
    got = codes(main("int *p = 0;", "struct { int a; } s;"))
    assert [c for c, _ in got].count("WRN-UNUSED-VAR") == 2


def test_missing_return_with_switch_default():
    ok = "int f(int n) { switch (n) { case 1: return 1; default: return 0; } }\n" + main("f(1);")
    assert "WRN-MISSING-RETURN" not in [c for c, _ in codes(ok)]
    bad = "int f(int n) { switch (n) { case 1: return 1; } }\n" + main("f(1);")
    assert "WRN-MISSING-RETURN" in [c for c, _ in codes(bad)]


def test_no_unreachable_warning_after_break_before_a_case_label():
    src = main("int n = 1; switch (n) { case 1: n = 2; break; case 2: n = 3; break; default: n = 0; }", "n++;")
    assert "WRN-UNREACHABLE-CODE" not in [c for c, _ in codes(src)]


# ---------------------------------------------------------------- the parser
def test_ast_shapes():
    prog = run("struct P { int x; int y; };\ntypedef struct P Pt;\nint f(Pt *p, int a[], char *s) {\n    return p->x + a[1] + *s;\n}\n"
               "int main(void) { int m[2][3]; return sizeof(int) + (int)1.5 + (1 ? 2 : 3); }\n").program
    struct, typedef, f, m = prog.decls
    assert isinstance(struct, A.VarDeclStmt) and struct.type_def.members[0].name == "x"
    assert typedef.is_typedef and typedef.decls[0].name == "Pt"
    assert [(p.type_name, p.ptr, len(p.dims)) for p in f.params] == [("Pt", 1, 0), ("int", 0, 1), ("char", 1, 0)]
    decl = m.body.stmts[0].decls[0]
    assert decl.is_array and isinstance(decl.array_size, A.IntLit) and len(decl.more_dims) == 1


def test_type_keyword_combinations():
    from cea.parser import canonical_type
    assert canonical_type(["unsigned"]) == "unsigned int"
    assert canonical_type(["long", "long", "int"]) == "long long"
    assert canonical_type(["unsigned", "char"]) == "unsigned char"
    assert canonical_type(["long", "double"]) == "long double"
    assert canonical_type(["short", "int"]) == "short"
    assert canonical_type(["short", "long"]) is None
    assert canonical_type(["float", "long"]) is None
    assert canonical_type(["unsigned", "signed"]) is None
    assert canonical_type(["void", "int"]) is None


@pytest.mark.parametrize("src,code,found", [
    ("int main(void) {\n    goto end;\nend: return 0;\n}\n", "SYN-UNSUPPORTED-FEATURE", "goto"),
    ("int (*fp)(int);\nint main(void) { return 0; }\n", "SYN-UNSUPPORTED-FEATURE", "("),
    ("int f(int n, ...) { return n; }\nint main(void) { return 0; }\n", "SYN-UNSUPPORTED-FEATURE", "..."),
    ("struct S { int a : 2; };\nint main(void) { return 0; }\n", "SYN-UNSUPPORTED-FEATURE", ":"),
    ("int main(void) {\n    int a[2] = {[0] = 1};\n    return 0;\n}\n", "SYN-UNSUPPORTED-FEATURE", "["),
    ("int main(void) {\n    short long x;\n    return 0;\n}\n", "SYN-UNSUPPORTED-FEATURE", "x"),
    ("register int main(void) { return 0; }\n", "SYN-UNSUPPORTED-FEATURE", "register"),
])
def test_still_unsupported(src, code, found):
    first = run(src).errors[0]
    assert (first.code, first.found) == (code, found)


@pytest.mark.parametrize("src,code", [
    ("int main(void) {\n    int a[2] = {1, 2;\n    return 0;\n}\n", "SYN-EXPECTED-TOKEN"),
    ("int main(void) {\n    int a[2] = {};\n    return 0;\n}\n", "SYN-EXPECTED-EXPRESSION"),
    ("int main(void) {\n    switch (1) {\n        case 1\n            break;\n    }\n    return 0;\n}\n", "SYN-EXPECTED-TOKEN"),
    ("int main(void) {\n    do { } while (1)\n    return 0;\n}\n", "SYN-MISSING-SEMICOLON"),
    ("int main(void) {\n    struct P { int x; int y }; \n    return 0;\n}\n", "SYN-MISSING-SEMICOLON"),
    ("enum E { A, B\nint main(void) { return 0; }\n", "SYN-EXPECTED-TOKEN"),
    ("int main(void) {\n    int x = (int;\n    return 0;\n}\n", "SYN-UNBALANCED-BRACKET"),
    ("int main(void) {\n    int x = 1 ? 2;\n    return 0;\n}\n", "SYN-EXPECTED-TOKEN"),
    ("int main(void) {\n    int x = p->;\n    return 0;\n}\n", "SYN-EXPECTED-TOKEN"),
])
def test_syntax_errors_in_new_constructs(src, code):
    syn = [r for r in run(src).errors if r.phase == "syntax"]
    assert syn and syn[0].code == code, [(r.code, r.line, r.column) for r in run(src).errors]


def test_syntax_error_in_switch_body_keeps_cascade_linked():
    src = "int main(void) {\n    int n = 1;\n    switch (n {\n        case 1: break;\n    }\n    return n;\n}\n"
    result = run(src)
    assert [r.code for r in result.errors] == ["SYN-UNBALANCED-BRACKET"]
    assert len(result.clusters) == 1


def test_unsupported_feature_cascades_link_to_their_root():
    src = "int main(void) {\n    int (*op)(int, int) = 0;\n    int a = op(1, 2);\n    int b = op(3, 4);\n    return a + b;\n}\n"
    result = run(src)
    assert len(result.clusters) == 1 and len(result.clusters[0].symptoms) == 2
    src = "struct F {\n    int ready : 1;\n    int n;\n};\nint main(void) {\n    struct F f;\n    f.n = 1;\n    return f.n;\n}\n"
    result = run(src)
    assert len(result.clusters) == 1 and {r.code for r in result.clusters[0].symptoms} == {"SEM-INCOMPLETE-TYPE"}
