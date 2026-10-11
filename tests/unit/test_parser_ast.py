"""AST contract checks for src/cea/ast.py (plan 006 step 1).

The field names and order are fixed by plans/m1-architecture.md section 4;
plan 007 consumes them, so any drift must fail here.
"""
import dataclasses

import pytest

from cea import ast as A
from cea.records import Position

CONTRACT = {
    "Span": ["start_line", "start_col", "end_line", "end_col"],
    "Program": ["decls", "span"],
    "Param": ["type_name", "name", "name_pos", "span"],
    "FunctionDecl": ["ret_type", "name", "name_pos", "params", "body", "span", "error_id", "idents_in_span"],
    "VarDecl": ["type_name", "name", "name_pos", "array_size", "init", "is_global", "span",
                "error_id", "idents_in_span"],
    "VarDeclStmt": ["decls", "span"],
    "Block": ["stmts", "span", "orphan_of", "closed_by_repair"],
    "If": ["cond", "then", "els", "span"],
    "While": ["cond", "body", "span"],
    "For": ["init", "cond", "step", "body", "span"],
    "Return": ["value", "span"],
    "Break": ["span"],
    "Continue": ["span"],
    "ExprStmt": ["expr", "span"],
    "EmptyStmt": ["span"],
    "ErrorStmt": ["span", "error_id", "kind_hint", "declared_names", "idents_in_span", "stopped_before"],
    "IntLit": ["value", "span"],
    "FloatLit": ["value", "span"],
    "CharLit": ["value", "span"],
    "StringLit": ["value", "span"],
    "Name": ["name", "span"],
    "Unary": ["op", "operand", "postfix", "span"],
    "Binary": ["op", "left", "right", "op_pos", "span"],
    "Assign": ["op", "target", "value", "op_pos", "span"],
    "Call": ["callee", "args", "span"],
    "Index": ["base", "index", "span"],
    "ErrorExpr": ["span", "error_id"],
}
SP = A.Span(1, 1, 1, 1)


@pytest.mark.parametrize("name,fields", sorted(CONTRACT.items()))
def test_node_fields_match_contract(name, fields):
    cls = getattr(A, name)
    assert dataclasses.is_dataclass(cls), f"{name} must be a dataclass"
    # course-level C appended fields after the original contract; the original fields keep their order
    assert [f.name for f in dataclasses.fields(cls)][:len(fields)] == fields


def test_span_is_frozen_and_hashable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        SP.start_line = 2  # type: ignore[misc]
    assert hash(SP) == hash(A.Span(1, 1, 1, 1))


def test_recovery_fields_default_to_empty():
    f1 = A.FunctionDecl("int", "f", Position(1, 5), [], None, SP)
    f2 = A.FunctionDecl("int", "g", Position(1, 5), [], None, SP)
    assert f1.error_id is None and f1.idents_in_span == set()
    assert f1.idents_in_span is not f2.idents_in_span        # default_factory, not a shared set
    v = A.VarDecl("int", "x", Position(1, 5), None, None, False, SP)
    assert v.error_id is None and v.idents_in_span == set()
    b = A.Block([], SP)
    assert b.orphan_of is None and b.closed_by_repair is None


def test_module_does_not_shadow_stdlib_ast():
    import ast as stdlib_ast
    assert hasattr(stdlib_ast, "parse") and stdlib_ast is not A
    assert A.__name__ == "cea.ast"
