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
class TypeInfo:
    """What the declaration specifiers said. ``base`` is canonical text: 'int', 'unsigned long',
    'struct Point', 'enum Color', or a typedef name; ``type_def`` is an inline struct/union/enum definition."""
    base: str
    const: bool = False
    storage: str | None = None             # 'static' | 'extern' | 'typedef' | None
    type_def: "StructDef | EnumDef | None" = None


@dataclass
class Param:
    type_name: str
    name: str                      # "" for an unnamed parameter of a prototype
    name_pos: Position
    span: Span
    ptr: int = 0                   # number of '*' in the declarator
    dims: list = field(default_factory=list)       # array suffixes ('[]' is None): decays to a pointer
    const: bool = False            # 'const' applies to the pointed-to / element type (or the value itself)
    ptr_const: bool = False        # 'const' after the last '*'


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
    ret_ptr: int = 0               # '*' before the function name
    ret_const: bool = False
    storage: str | None = None
    type_def: "StructDef | EnumDef | None" = None


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
    ptr: int = 0                   # number of '*' in the declarator
    is_array: bool = False         # array_size is the first dimension (None for '[]')
    more_dims: list = field(default_factory=list)  # second and later dimensions
    const: bool = False            # 'const' on the base type
    storage: str | None = None
    ptr_const: bool = False        # 'const' after the last '*' (char *const p)


@dataclass
class VarDeclStmt:
    """'int a, b = 2;' (local or global); also 'struct P {...};' (no declarators) and typedefs."""
    decls: list[VarDecl]
    span: Span
    type_def: "StructDef | EnumDef | None" = None   # inline struct/union/enum definition in the specifiers
    is_typedef: bool = False       # the declarators are typedef names
    base: str = ""                 # canonical base type text of the specifiers


@dataclass
class StructMember:
    type_name: str
    name: str
    name_pos: Position
    ptr: int
    dims: list
    const: bool
    span: Span
    type_def: "StructDef | EnumDef | None" = None


@dataclass
class StructDef:
    kind: str                      # 'struct' | 'union'
    tag: str | None
    members: list[StructMember]
    span: Span
    name_pos: Position | None = None


@dataclass
class EnumItem:
    name: str
    name_pos: Position
    value: "Expr | None"


@dataclass
class EnumDef:
    tag: str | None
    items: list[EnumItem]
    span: Span
    name_pos: Position | None = None


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
class DoWhile:
    body: "Stmt"
    cond: "Expr"
    span: Span


@dataclass
class Switch:
    cond: "Expr"
    body: "Stmt"
    span: Span


@dataclass
class Case:
    """'case value:' label (a marker inside the switch body)."""
    value: "Expr"
    span: Span


@dataclass
class Default:
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
    op: str                        # '!', '-', '+', '~', '*', '&', '++', '--'
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
class Member:
    base: "Expr"
    name: str
    arrow: bool                    # '->' (True) or '.' (False)
    name_pos: Position
    span: Span


@dataclass
class TypeName:
    """A type written without a name: the operand of a cast or of sizeof."""
    base: str
    ptr: int
    dims: list
    const: bool
    span: Span


@dataclass
class Cast:
    type: TypeName
    operand: "Expr"
    span: Span


@dataclass
class SizeOf:
    operand: "Expr | TypeName"
    span: Span


@dataclass
class Ternary:
    cond: "Expr"
    then: "Expr"
    els: "Expr"
    span: Span


@dataclass
class InitList:
    items: list["Expr | InitList"]
    span: Span


@dataclass
class ErrorExpr:
    """Stands in for an expression that failed to parse (type <error>)."""
    span: Span
    error_id: str


Expr = Union[IntLit, FloatLit, CharLit, StringLit, Name, Unary, Binary, Assign, Call, Index, Member, Cast,
             SizeOf, Ternary, InitList, ErrorExpr]
Stmt = Union[VarDeclStmt, Block, If, While, DoWhile, For, Switch, Case, Default, Return, Break, Continue,
             ExprStmt, EmptyStmt, ErrorStmt]
