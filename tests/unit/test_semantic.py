"""Unit tests for the semantic phase (plan 007).

One table row per SEM/WRN code (the catalog's example trigger), then scopes,
reads and writes, types, control flow, and the caused_by rules R3-R8.
"""
import pytest

from cea import ast as A
from cea.catalog import load_catalog
from cea.diagnostics import ErrorSink
from cea.lexer import lex
from cea.parser import parse
from cea.records import Position
from cea.semantic import analyze


def records(src):
    """All records of the three phases (the same steps as cea.pipeline.compile_source)."""
    sink = ErrorSink(src)
    lr = lex(src, sink)
    analyze(parse(lr, sink), sink, lr.stdio_include)
    return sink.records


def table(src):
    return [(r.code, r.line, r.column) for r in records(src)]


MAIN0 = "int main(void) {\n    return 0;\n}\n"

# (code, source, full expected [(code, line, col)] list, message of the first record)
# -- the catalog's "Example trigger" placed in a minimal program
CODE_CASES = [
    ("SEM-DEREF-NON-POINTER", "int main(void) {\n    int x = 1;\n    *x = 2;\n    return x;\n}\n",
     [("SEM-DEREF-NON-POINTER", 3, 5)], "Cannot dereference 'x': int is not a pointer"),
    ("SEM-ADDR-OF-NON-LVALUE", "int main(void) {\n    int x = 1;\n    int *p = &(x + 1);\n    return *p;\n}\n",
     [("SEM-ADDR-OF-NON-LVALUE", 3, 14)], "Cannot take the address of 'x + 1': it is not a variable or memory location"),
    ("SEM-NO-SUCH-MEMBER", "struct Point { int x; int y; };\nint main(void) {\n    struct Point p;\n    p.z = 3;\n    return p.x;\n}\n",
     [("SEM-NO-SUCH-MEMBER", 4, 7)], "struct Point has no member named 'z'"),
    ("SEM-MEMBER-ON-NON-STRUCT", "int main(void) {\n    int n = 1;\n    n.x = 1;\n    return n;\n}\n",
     [("SEM-MEMBER-ON-NON-STRUCT", 3, 5)], "Cannot access member 'x' of int: it is not a struct or union"),
    ("SEM-ARROW-ON-NON-POINTER", "struct Point { int x; };\nint main(void) {\n    struct Point p;\n    p->x = 1;\n    return p.x;\n}\n",
     [("SEM-ARROW-ON-NON-POINTER", 4, 5)], "'->' needs a pointer to a struct or union, but this is struct Point (use '.' for member 'x')"),
    ("SEM-INCOMPLETE-TYPE", "struct Node;\nint main(void) {\n    struct Node n;\n    return 0;\n}\n",
     [("SEM-INCOMPLETE-TYPE", 3, 17)], "'n' has incomplete type struct Node: the struct is declared but never defined"),
    ("SEM-ASSIGN-TO-CONST", "int main(void) {\n    const int n = 1;\n    n = 2;\n    return n;\n}\n",
     [("SEM-ASSIGN-TO-CONST", 3, 5)], "Cannot assign to 'n': it is read-only (const)"),
    ("SEM-DUPLICATE-CASE", "int main(void) {\n    int n = 1;\n    switch (n) {\n        case 1: n = 2; break;\n        case 1: n = 3; break;\n    }\n    return n;\n}\n",
     [("SEM-DUPLICATE-CASE", 5, 14)], "Duplicate case label 1 (first used on line 4)"),
    ("SEM-CASE-NOT-CONSTANT", "int main(void) {\n    int n = 1;\n    int k = 2;\n    switch (n) {\n        case k: n = 2; break;\n    }\n    return n;\n}\n",
     [("SEM-CASE-NOT-CONSTANT", 5, 14)], "A case label must be an integer constant expression"),
    ("SEM-SWITCH-NON-INT", "int main(void) {\n    double d = 1.5;\n    switch (d) {\n        default: break;\n    }\n    return 0;\n}\n",
     [("SEM-SWITCH-NON-INT", 3, 13)], "A switch needs an integer expression but this is double"),
    ("SEM-CASE-OUTSIDE-SWITCH", "int main(void) {\n    case 1: ;\n    return 0;\n}\n",
     [("SEM-CASE-OUTSIDE-SWITCH", 2, 5)], "'case' can only be used inside a switch"),
    ("WRN-INCOMPATIBLE-POINTER", "int main(void) {\n    double d = 1.5;\n    int *p = &d;\n    return *p;\n}\n",
     [("WRN-INCOMPATIBLE-POINTER", 3, 10)], "Incompatible pointer types: double* used where int* is expected"),
    ("SEM-UNDECLARED-VAR", "int main(void) {\n    y = 3;\n    return 0;\n}\n",
     [("SEM-UNDECLARED-VAR", 2, 5)],
     "Variable 'y' is used before it is declared"),
    ("SEM-UNDECLARED-FUNC", "int main(void) {\n    foo(1);\n    return 0;\n}\n",
     [("SEM-UNDECLARED-FUNC", 2, 5)],
     "Function 'foo' is not declared before this call"),
    ("SEM-REDECLARED", "int main(void) {\n    int x;\n    int x;\n    x = 1;\n    return x;\n}\n",
     [("SEM-REDECLARED", 3, 9)],
     "'x' is already declared in this scope (line 2)"),
    ("SEM-CONFLICTING-TYPES", "int f(int a);\nfloat f(int a) {\n    return 1.0;\n}\n" + MAIN0,
     [("SEM-CONFLICTING-TYPES", 2, 7)],
     "Declarations of 'f' disagree: int f(int) vs float f(int)"),
    ("SEM-TYPE-MISMATCH", "int main(void) {\n    int x = \"hi\";\n    return x;\n}\n",
     [("SEM-TYPE-MISMATCH", 2, 9)],
     'Cannot use string literal where int is required'),
    ("SEM-TYPE-MISMATCH", "int main(void) {\n    int r = 7.5 % 2;\n    return r;\n}\n",
     [("SEM-TYPE-MISMATCH", 2, 17)],
     'Cannot use double where an integer is required'),
    ("SEM-VOID-VALUE", "void log_it(void) {\n}\nint main(void) {\n    int x = log_it();\n    return x;\n}\n",
     [("SEM-VOID-VALUE", 4, 13)],
     'A void value cannot be stored or used in an expression'),
    ("SEM-NOT-CALLABLE", "int main(void) {\n    int x = 0;\n    x(1);\n    return x;\n}\n",
     [("SEM-NOT-CALLABLE", 3, 5)],
     "'x' is not a function"),
    ("SEM-ARG-COUNT", "int add(int a, int b) {\n    return a + b;\n}\nint main(void) {\n    return add(1);\n}\n",
     [("SEM-ARG-COUNT", 5, 12)],
     "'add' expects 2 argument(s) but got 1"),
    ("SEM-ARG-TYPE", "int add(int a, int b) {\n    return a + b;\n}\nint main(void) {\n    return add(1, \"two\");\n}\n",
     [("SEM-ARG-TYPE", 5, 12)],
     "Argument 2 of 'add' must be int but is string literal"),
    ("SEM-RETURN-TYPE", "void f(void) {\n    return 5;\n}\n" + MAIN0,
     [("SEM-RETURN-TYPE", 2, 5)],
     "Function 'f' returns void but this returns int"),
    ("SEM-RETURN-TYPE", "int g(void) {\n    return;\n}\n" + MAIN0,
     [("SEM-RETURN-TYPE", 2, 5)],
     "Function 'g' returns int but this returns nothing"),
    ("SEM-NOT-ARRAY", "int main(void) {\n    int x = 1;\n    x[0] = 1;\n    return x;\n}\n",
     [("SEM-NOT-ARRAY", 3, 5)],
     "'x' is not an array or pointer and cannot be indexed"),
    ("SEM-INDEX-NOT-INT", "int main(void) {\n    int a[3];\n    a[1.5] = 2;\n    return a[0];\n}\n",
     [("SEM-INDEX-NOT-INT", 3, 7)],
     'Array index must be an integer but has type double'),
    ("SEM-BAD-ARRAY-SIZE", "int main(void) {\n    int n = 3;\n    int a[n];\n    a[0] = n;\n    return a[0];\n}\n",
     [("SEM-BAD-ARRAY-SIZE", 3, 11)],
     'Array size must be a constant integer greater than 0'),
    ("SEM-BREAK-OUTSIDE-LOOP", "int main(void) {\n    if (1) {\n        break;\n    }\n    return 0;\n}\n",
     [("SEM-BREAK-OUTSIDE-LOOP", 3, 9)],
     "'break' can only be used inside a loop"),
    ("SEM-NONCONST-GLOBAL-INIT", "int x = 4;\nint y = x + 1;\nint main(void) {\n    return y;\n}\n",
     [("SEM-NONCONST-GLOBAL-INIT", 2, 9)],
     'A global variable must be initialised with a constant expression'),
    ("SEM-PRINTF-FORMAT", "#include <stdio.h>\nint main(void) {\n    int x = 1;\n    printf(x);\n    return 0;\n}\n",
     [("SEM-PRINTF-FORMAT", 4, 5)],
     'The first argument of printf must be a string (a string literal or a char array or pointer)'),
    ("SEM-MISSING-MAIN", "void g(void) {\n}\n",
     [("SEM-MISSING-MAIN", 2, 2)],
     "Program has no 'int main()' function"),
    ("WRN-UNUSED-VAR", "int main(void) {\n    int t = 1;\n    return 0;\n}\n",
     [("WRN-UNUSED-VAR", 2, 9)],
     "Variable 't' is declared but never used"),
    ("WRN-UNREACHABLE-CODE", "int main(void) {\n    return 0;\n    return 1;\n}\n",
     [("WRN-UNREACHABLE-CODE", 3, 5)],
     'This statement can never run'),
    ("WRN-IMPLICIT-NARROWING", "int main(void) {\n    int n = 2.5;\n    return n;\n}\n",
     [("WRN-IMPLICIT-NARROWING", 2, 9)],
     'double value converted to int; the fractional part is lost'),
    ("WRN-MISSING-RETURN", "int f(int b) {\n    if (b) {\n        return 1;\n    }\n}\nint main(void) {\n    return f(1);\n}\n",
     [("WRN-MISSING-RETURN", 1, 5)],
     "Function 'f' may end without returning a value"),
    ("WRN-ASSIGN-IN-CONDITION", "int main(void) {\n    int x = 0;\n    if (x = 5) {\n        x = 1;\n    }\n    return x;\n}\n",
     [("WRN-ASSIGN-IN-CONDITION", 3, 11)],
     "Assignment used as a condition; did you mean '=='?"),
]


@pytest.mark.parametrize("code,src,expected,message", CODE_CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CODE_CASES)])
def test_catalog_example_trigger(code, src, expected, message):
    recs = records(src)
    assert [(r.code, r.line, r.column) for r in recs] == expected
    rec = recs[0]
    entry = load_catalog()[code]
    assert (rec.phase, rec.severity, rec.rule_ref) == ("semantic", entry.severity, entry.rule_ref)
    assert rec.caused_by is None and rec.root_id == rec.id
    assert rec.message == message


def test_every_sem_and_wrn_code_has_a_table_row():
    codes = {c for c in load_catalog() if c.startswith(("SEM-", "WRN-"))}
    assert codes == {c[0] for c in CODE_CASES}


# ---------------------------------------------------------------- printf builtin
def test_printf_without_include_is_undeclared():
    assert table("int main(void) {\n    printf(\"hi\");\n    return 0;\n}\n") == [("SEM-UNDECLARED-FUNC", 2, 5)]


def test_printf_include_after_first_use_is_undeclared():
    src = "int main(void) {\n    printf(\"a\");\n    return 0;\n}\n#include <stdio.h>\nint f(void) {\n    printf(\"b\");\n    return 1;\n}\n"
    assert table(src) == [("SEM-UNDECLARED-FUNC", 2, 5)]


def test_printf_redeclared_after_include():
    src = "#include <stdio.h>\nint printf(int x);\n" + MAIN0
    assert table(src) == [("SEM-REDECLARED", 2, 5)]


def test_printf_extra_arguments_must_be_numbers_or_pointers():
    src = ("#include <stdio.h>\nstruct P { int x; };\nint main(void) {\n    struct P p;\n    p.x = 1;\n"
           "    printf(\"%d %s\", 1, \"x\");\n    printf(\"%d\", p);\n    return 0;\n}\n")
    assert table(src) == [("SEM-ARG-TYPE", 7, 5)]


# ---------------------------------------------------------------- scopes
def test_shadowing_an_outer_scope_is_allowed():
    src = "int x = 1;\nint main(void) {\n    int x = 2;\n    {\n        int x = 3;\n        x = x + 1;\n    }\n    return x;\n}\n"
    assert table(src) == []


def test_parameters_share_the_body_scope():
    assert table("int f(int a) {\n    int a = 1;\n    return a;\n}\n" + MAIN0) == [("SEM-REDECLARED", 2, 9)]


def test_for_init_has_its_own_scope():
    src = ("int main(void) {\n    int s = 0;\n    for (int i = 0; i < 3; i++) {\n        int i = 5;\n        s += i;\n    }\n"
           "    return i;\n}\n")
    assert table(src) == [("SEM-UNDECLARED-VAR", 7, 12)]


def test_function_defined_twice_is_redeclared():
    assert table("int f(void) {\n    return 1;\n}\nint f(void) {\n    return 2;\n}\n" + MAIN0) == [("SEM-REDECLARED", 4, 5)]


def test_prototype_then_definition_then_recursion_is_clean():
    src = "int f(int n);\nint f(int n) {\n    if (n < 1) {\n        return 0;\n    }\n    return f(n - 1);\n}\n" + MAIN0
    assert table(src) == []


# ---------------------------------------------------------------- reads and writes (sem.unused_declaration, plan 004)
@pytest.mark.parametrize("stmt,unused", [
    ("s = 1;", True), ("s += 1;", False), ("s -= 1;", False), ("s *= 2;", False), ("s /= 2;", False),
    ("s %= 2;", False), ("s++;", False), ("++s;", False), ("s--;", False), ("--s;", False), ("s = s;", False),
])
def test_compound_assignment_and_increment_are_reads(stmt, unused):
    src = f"int main(void) {{\n    int s = 0;\n    {stmt}\n    return 0;\n}}\n"
    assert table(src) == ([("WRN-UNUSED-VAR", 2, 9)] if unused else [])


def test_array_element_target_writes_the_array_and_reads_the_index():
    src = "int main(void) {\n    int a[2];\n    int i = 1;\n    a[i] = 3;\n    return 0;\n}\n"
    assert table(src) == [("WRN-UNUSED-VAR", 2, 9)]


def test_unused_warnings_come_at_scope_exit_in_declaration_order():
    src = "int main(void) {\n    int a = 1;\n    {\n        int b = 2;\n    }\n    int c = 3;\n    return 0;\n}\n"
    assert table(src) == [("WRN-UNUSED-VAR", 4, 13), ("WRN-UNUSED-VAR", 2, 9), ("WRN-UNUSED-VAR", 6, 9)]


def test_parameters_and_globals_are_exempt():
    assert table("int g = 1;\nint f(int a) {\n    return 0;\n}\n" + MAIN0) == []


# ---------------------------------------------------------------- types
@pytest.mark.parametrize("decl,expected", [
    ("int n = 2.5;", [("WRN-IMPLICIT-NARROWING", 2, 9)]),
    ("char c = 2.5;", [("WRN-IMPLICIT-NARROWING", 2, 10)]),
    ("float f = 2.5;", []),
    ("char c = 300;", []),
    ("double d = 'a';", []),
])
def test_conversions(decl, expected):
    name_used = decl.split()[1]
    src = f"int main(void) {{\n    {decl}\n    return {name_used};\n}}\n"
    got = [t for t in table(src) if t[0] != "WRN-IMPLICIT-NARROWING" or t[1] == 2]
    assert [t for t in got if t[1] == 2] == expected


def test_narrowing_on_assignment_compound_return_and_argument():
    src = ("int h(int v) {\n    return v;\n}\nint k(void) {\n    return 1.5;\n}\nint main(void) {\n    int x = 0;\n"
           "    x = 1.5;\n    x += 0.5;\n    x = h(2.5);\n    return x;\n}\n")
    assert table(src) == [("WRN-IMPLICIT-NARROWING", 5, 5), ("WRN-IMPLICIT-NARROWING", 9, 7),
                          ("WRN-IMPLICIT-NARROWING", 10, 7), ("WRN-IMPLICIT-NARROWING", 11, 9)]


def test_struct_condition_is_a_type_mismatch():
    src = "struct P { int x; };\nint main(void) {\n    struct P p;\n    p.x = 1;\n    if (p) {\n        return 1;\n    }\n    return 0;\n}\n"
    assert table(src) == [("SEM-TYPE-MISMATCH", 5, 9)]


def test_void_variable_and_void_operand():
    src = "void v(void) {\n}\nint main(void) {\n    void x;\n    int y = v() + 1;\n    return y + x;\n}\n"
    assert table(src) == [("SEM-VOID-VALUE", 4, 10), ("SEM-VOID-VALUE", 5, 13)]


def test_unused_void_variable_gets_only_void_value():
    assert table("int main(void) {\n    void x;\n    return 0;\n}\n") == [("SEM-VOID-VALUE", 2, 10)]


def test_array_name_is_not_a_value():
    src = "int main(void) {\n    int a[2];\n    int b = 0;\n    a = 1;\n    b = a + 1;\n    return b;\n}\n"
    assert [t[0] for t in table(src)] == ["SEM-TYPE-MISMATCH", "SEM-TYPE-MISMATCH"]


def test_error_type_absorbs_type_checks():
    src = "int main(void) {\n    int x = 0;\n    x = nope + 1.5;\n    x = nope[2];\n    return nope(x);\n}\n"
    assert [t[0] for t in table(src)] == ["SEM-UNDECLARED-VAR", "SEM-UNDECLARED-VAR", "SEM-UNDECLARED-FUNC"]


# ---------------------------------------------------------------- control flow
def test_unreachable_is_reported_once_per_block():
    src = "int main(void) {\n    return 0;\n    return 1;\n    return 2;\n}\n"
    assert table(src) == [("WRN-UNREACHABLE-CODE", 3, 5)]


@pytest.mark.parametrize("body,warn", [
    ("    if (b) {\n        return 1;\n    } else {\n        return 2;\n    }\n", False),
    ("    while (b) {\n        return 1;\n    }\n", True),
    ("    {\n        return 1;\n    }\n", False),
    ("    if (b) {\n        return 1;\n    } else if (b > 1) {\n        return 2;\n    }\n", True),
])
def test_return_paths(body, warn):
    src = "int f(int b) {\n" + body + "}\n" + MAIN0
    assert table(src) == ([("WRN-MISSING-RETURN", 1, 5)] if warn else [])


def test_code_after_a_return_is_unreachable_not_a_missing_return():
    src = "void f(void) {\n}\nint g(void) {\n    return 1;\n    f();\n}\n" + MAIN0
    assert table(src) == [("WRN-UNREACHABLE-CODE", 5, 5)]


def test_statement_after_an_if_else_that_returns_is_unreachable():
    src = ("int f(int b) {\n    if (b) {\n        return 1;\n    } else {\n        return 2;\n    }\n    b = 3;\n}\n"
           + MAIN0)
    assert table(src) == [("WRN-UNREACHABLE-CODE", 7, 5)]


def test_main_and_void_functions_need_no_return():
    assert table("void p(void) {\n}\nint main(void) {\n    p();\n}\n") == []


def test_break_inside_nested_loop_block_is_fine():
    assert table("int main(void) {\n    while (1) {\n        if (1) {\n            break;\n        }\n    }\n    return 0;\n}\n") == []


# ---------------------------------------------------------------- caused_by rules R3-R8 on real source
def test_r3_global_initializer_error_expr():
    recs = records("int g = ;\n" + MAIN0)
    assert [(r.code, r.caused_by) for r in recs] == [("SYN-EXPECTED-EXPRESSION", None),
                                                    ("SEM-NONCONST-GLOBAL-INIT", "E-0001")]


def test_r3_array_size_error_expr():
    recs = records("int main(void) {\n    int a[;\n    return 0;\n}\n")
    assert [(r.code, r.caused_by) for r in recs][:2] == [("SYN-EXPECTED-EXPRESSION", None),
                                                        ("SEM-BAD-ARRAY-SIZE", "E-0001")]


def test_r5_missing_main_after_broken_main_header():
    recs = records("int main(void {\n    return 0;\n}\n")
    assert [(r.code, r.caused_by) for r in recs] == [(recs[0].code, None), ("SEM-MISSING-MAIN", "E-0001")]
    assert recs[0].phase == "syntax"


# ---------------------------------------------------------------- caused_by rules on hand-built ASTs (parser-independent)
def S(l1, c1, l2=None, c2=None):
    return A.Span(l1, c1, l2 or l1, c2 or c1)


def _sink_with_syntax_records(n):
    sink = ErrorSink("x\n" * 10)
    recs = [sink.report("SYN-EXPECTED-EXPRESSION", 2, 5, found=";", rule_ref="primary") for _ in range(n)]
    return sink, recs


def test_r3_printf_first_argument_error_expr():
    sink, (syn,) = _sink_with_syntax_records(1)
    call = A.ExprStmt(A.Call(A.Name("printf", S(3, 5, 3, 10)), [A.ErrorExpr(S(3, 12), syn.id)], S(3, 5, 3, 13)),
                      S(3, 5, 3, 14))
    body = A.Block([call, A.Return(A.IntLit(0, S(4, 12)), S(4, 5, 4, 13))], S(2, 16, 5, 1))
    prog = A.Program([A.FunctionDecl("int", "main", Position(2, 5), [], body, S(2, 1, 5, 1))], S(1, 1, 5, 2))
    analyze(prog, sink, Position(1, 1))
    assert [(r.code, r.caused_by) for r in sink.records] == [("SYN-EXPECTED-EXPRESSION", None),
                                                            ("SEM-PRINTF-FORMAT", syn.id)]


def test_r4_r6_r7_r8_on_hand_built_ast():
    sink, (syn1, syn2) = _sink_with_syntax_records(2)
    broken = A.VarDecl("int", "b", Position(3, 9), None, A.ErrorExpr(S(3, 13), syn1.id), False, S(3, 9, 3, 13),
                       error_id=syn1.id, idents_in_span={"b"})
    keep = A.VarDecl("int", "k", Position(4, 9), None, A.IntLit(1, S(4, 13)), False, S(4, 9, 4, 13))
    lost = A.ErrorStmt(S(5, 5, 5, 20), syn2.id, "while", [], {"k"}, "{")
    orphan = A.Block([A.Break(S(6, 9, 6, 14))], S(5, 21, 7, 5), orphan_of=syn2.id)
    body = A.Block([A.VarDeclStmt([broken], S(3, 5, 3, 14)), A.VarDeclStmt([keep], S(4, 5, 4, 14)), lost, orphan],
                   S(2, 14, 8, 1))
    f = A.FunctionDecl("int", "f", Position(2, 5), [], body, S(2, 1, 8, 1))
    main_body = A.Block([A.Return(A.IntLit(0, S(9, 25)), S(9, 18, 9, 26))], S(9, 16, 9, 28))
    main = A.FunctionDecl("int", "main", Position(9, 5), [], main_body, S(9, 1, 9, 28))
    analyze(A.Program([f, main], S(1, 1, 9, 29)), sink, None)
    got = [(r.code, r.line, r.caused_by) for r in sink.records[2:]]
    assert got == [("SEM-BREAK-OUTSIDE-LOOP", 6, syn2.id),     # R7: orphan of a 'while' ErrorStmt
                   ("WRN-UNUSED-VAR", 3, syn1.id),             # R4: broken declaration
                   ("WRN-UNUSED-VAR", 4, syn2.id),             # R6: 'k' is in the ErrorStmt's idents_in_span
                   ("WRN-MISSING-RETURN", 2, syn2.id)]         # R8: first ErrorStmt in the body


def test_analyze_never_raises_on_empty_program():
    sink = ErrorSink("")
    analyze(A.Program([], S(1, 1)), sink, None)
    assert [(r.code, r.line) for r in sink.records] == [("SEM-MISSING-MAIN", 1)]
