"""AST node dataclasses for the course C subset.

Defined by plans/m1-architecture.md section 4 (plan 006); consumed by the
semantic analyser (plan 007). The error nodes and recovery fields follow
docs/error-recovery.md section 5. Import this module as
``from cea import ast as A`` so it never shadows the standard-library ``ast``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from cea.records import Position


@dataclass(frozen=True)
class Span:
    """Inclusive, 1-based source range."""
    start_line: int
    start_col: int
    end_line: int
    end_col: int


# ---- top level
@dataclass
class Program:
    decls: list["FunctionDecl | VarDeclStmt | ErrorStmt"]
    span: Span


@dataclass
class Param:
    type_name: str
    name: str
    name_pos: Position
    span: Span


@dataclass
class FunctionDecl:
    ret_type: str
    name: str
    name_pos: Position
    params: list[Param]            # [] for both "()" and "(void)"
    body: "Block | None"           # None for a prototype
    span: Span
    error_id: str | None = None    # broken declaration (error-recovery section 5)
    idents_in_span: set[str] = field(default_factory=set)


@dataclass
class VarDecl:
    """One declarator."""
    type_name: str
    name: str
    name_pos: Position
    array_size: "Expr | None"
    init: "Expr | None"
    is_global: bool
    span: Span
    error_id: str | None = None
    idents_in_span: set[str] = field(default_factory=set)


@dataclass
class VarDeclStmt:
    """'int a, b = 2;' (local or global)."""
    decls: list[VarDecl]
    span: Span


# ---- statements
@dataclass
class Block:
    stmts: list["Stmt"]
    span: Span
    orphan_of: str | None = None
    closed_by_repair: str | None = None


@dataclass
class If:
    cond: "Expr"
    then: "Stmt"
    els: "Stmt | None"
    span: Span


@dataclass
class While:
    cond: "Expr"
    body: "Stmt"
    span: Span


@dataclass
class For:
    init: "VarDeclStmt | Expr | None"
    cond: "Expr | None"
    step: "Expr | None"
    body: "Stmt"
    span: Span


@dataclass
class Return:
    value: "Expr | None"
    span: Span                     # starts at 'return'


@dataclass
class Break:
    span: Span


@dataclass
class Continue:
    span: Span


@dataclass
class ExprStmt:
    expr: "Expr"
    span: Span


@dataclass
class EmptyStmt:
    span: Span


@dataclass
class ErrorStmt:
    """A statement or top-level declaration that failed and was skipped."""
    span: Span
    error_id: str
    kind_hint: str   # 'if' 'while' 'for' 'return' 'break' 'continue' 'decl' 'expr' 'top' 'unsupported'
    declared_names: list[tuple[str, str]]
    idents_in_span: set[str]
    stopped_before: str | None


# ---- expressions
@dataclass
class IntLit:
    value: int
    span: Span


@dataclass
class FloatLit:
    value: float
    span: Span


@dataclass
class CharLit:
    value: str
    span: Span


@dataclass
class StringLit:
    value: str
    span: Span


@dataclass
class Name:
    name: str
    span: Span


@dataclass
class Unary:
    op: str                        # '!', '-', '+', '++', '--'
    operand: "Expr"
    postfix: bool
    span: Span


@dataclass
class Binary:
    op: str
    left: "Expr"
    right: "Expr"
    op_pos: Position
    span: Span


@dataclass
class Assign:
    op: str                        # '=', '+=', '-=', '*=', '/=', '%='
    target: "Expr"
    value: "Expr"
    op_pos: Position
    span: Span


@dataclass
class Call:
    callee: "Expr"
    args: list["Expr"]
    span: Span


@dataclass
class Index:
    base: "Expr"
    index: "Expr"
    span: Span


@dataclass
class ErrorExpr:
    """Stands in for an expression that failed to parse (type <error>)."""
    span: Span
    error_id: str


Expr = Union[IntLit, FloatLit, CharLit, StringLit, Name, Unary, Binary, Assign, Call, Index, ErrorExpr]
Stmt = Union[VarDeclStmt, Block, If, While, For, Return, Break, Continue, ExprStmt, EmptyStmt, ErrorStmt]
