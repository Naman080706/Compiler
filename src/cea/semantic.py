"""Semantic analysis: the third compiler phase (PRD F1), plan 007.

``analyze(program, sink, stdio_include)`` walks the AST built by the parser once,
depth-first and left to right in source order (docs/error-recovery.md §6), and
reports every ``sem.*`` violation of docs/language-spec.md §4 through the
error sink. It never raises on a partial AST: ``ErrorStmt`` nodes are skipped,
``ErrorExpr`` nodes have the ``<error>`` type, and ``caused_by`` is set only by
rules R3-R8 (docs/error-recovery.md §7, as amended by plan 004).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cea import ast as A
from cea.diagnostics import ErrorSink
from cea.records import ErrorRecord, Position

# ---------------------------------------------------------------- types
# Scalar types are plain strings. Everything else is a small frozen dataclass.
INT, CHAR, FLOAT, DOUBLE, VOID = "int", "char", "float", "double", "void"
INTEGER_TYPES = frozenset({INT, CHAR})
FLOATING_TYPES = frozenset({FLOAT, DOUBLE})
ARITHMETIC_TYPES = INTEGER_TYPES | FLOATING_TYPES
STRING = "string literal"          # the type of a StringLit: no usable type (spec §3)


@dataclass(frozen=True)
class ArrayType:
    elem: str                      # int | char | float | double
    size: int | None               # None when the size expression was bad


@dataclass(frozen=True)
class FuncType:
    ret: str
    params: tuple[str, ...]


@dataclass(frozen=True)
class ErrorType:
    cause: str                     # id of the record that explains the unknown type


def type_name(t: object) -> str:
    """Human-readable type for messages and the ``found``/``expected`` fields."""
    if isinstance(t, ArrayType):
        return f"array {t.elem}[{t.size if t.size is not None else ''}]"
    if isinstance(t, FuncType):
        return f"function {sig_text('', t)}".replace("  ", " ")
    if isinstance(t, ErrorType):
        return "<error>"
    return str(t)


def sig_text(name: str, f: FuncType) -> str:
    params = ", ".join(f.params) if f.params else "void"
    return f"{f.ret} {name}({params})"


def is_arith(t: object) -> bool:
    return isinstance(t, str) and t in ARITHMETIC_TYPES


def is_err(t: object) -> bool:
    return isinstance(t, ErrorType)


def usual_arith(a: str, b: str) -> str:
    """Usual arithmetic conversions of spec §3 (char becomes int)."""
    if DOUBLE in (a, b):
        return DOUBLE
    if FLOAT in (a, b):
        return FLOAT
    return INT


# ---------------------------------------------------------------- symbols and scopes
@dataclass
class Symbol:
    name: str
    type: object
    pos: Position                  # name position of the (first) declaration
    kind: str                      # "var" | "param" | "global" | "func"
    decl: object = None            # VarDecl / Param / FunctionDecl (None for the printf builtin)
    read: bool = False
    defined: bool = False          # functions: a body has been seen
    err_mark: int = 0              # len(scope.error_nodes) when declared (R6)


@dataclass
class Scope:
    symbols: dict[str, Symbol] = field(default_factory=dict)
    order: list[Symbol] = field(default_factory=list)            # declaration order (WRN-UNUSED-VAR)
    error_nodes: list[tuple[str, set]] = field(default_factory=list)  # (error_id, idents) in source order (R6)


@dataclass
class FuncCtx:
    decl: A.FunctionDecl
    ret: str
    lost: list[tuple[str, str]] = field(default_factory=list)   # (name, error_id) for R5, source order
    first_error_stmt: str | None = None                         # R8


class Analyzer:
    def __init__(self, sink: ErrorSink, stdio_include: Position | None) -> None:
        self.sink = sink
        self.stdio = stdio_include
        self.printf_declared = False
        self.scopes: list[Scope] = [Scope()]           # [0] is file scope
        self.file_lost: list[tuple[str, str]] = []     # (name, error_id) at file scope, source order (R5)
        self.error_kinds: dict[str, str] = {}          # ErrorStmt.error_id -> kind_hint (R7)
        self.loop_stack: list[str | None] = []         # "loop" or an orphan error_id (R7)
        self.func: FuncCtx | None = None

    # ------------------------------------------------------------ reporting
    def report(self, code: str, pos: Position, *, found: str, end: Position | None = None,
               expected: tuple[str, ...] | list[str] = (), caused_by: str | None = None,
               **args: object) -> ErrorRecord:
        if end is None:
            end = Position(pos.line, pos.column + max(len(found), 1) - 1)
        return self.sink.report(code, pos.line, pos.column, found=found, expected=list(expected),
                                span_end=end, caused_by=caused_by, **args)

    # ------------------------------------------------------------ scope helpers
    def push(self) -> None:
        self.scopes.append(Scope())

    def pop(self) -> None:
        scope = self.scopes.pop()
        for sym in scope.order:                      # declaration order
            if sym.kind == "var" and not sym.read:
                self.report_unused(sym, scope)

    def report_unused(self, sym: Symbol, scope: Scope) -> None:
        decl = sym.decl
        cause = decl.error_id if isinstance(decl, A.VarDecl) and decl.error_id else None     # R4
        if cause is None:                                                                    # R6
            for eid, idents in scope.error_nodes[sym.err_mark:]:
                if sym.name in idents:
                    cause = eid
                    break
        self.report("WRN-UNUSED-VAR", sym.pos, found=sym.name, caused_by=cause, name=sym.name)

    def lookup(self, name: str) -> Symbol | None:
        for scope in reversed(self.scopes):
            if name in scope.symbols:
                return scope.symbols[name]
        return None

    def note_error_node(self, error_id: str, idents: set) -> None:
        """R6 bookkeeping: an ErrorStmt / broken declaration is visible to every open scope.

        R6 also names ErrorExpr, but an ErrorExpr only occurs inside a broken declaration
        (error-recovery §4.4 catch point (b)), whose idents_in_span already covers it.
        """
        for scope in self.scopes:
            scope.error_nodes.append((error_id, set(idents)))

    def note_lost(self, name: str, error_id: str) -> None:
        """R5 bookkeeping: a name that an error node failed to declare."""
        (self.func.lost if self.func else self.file_lost).append((name, error_id))

    def r5(self, name: str) -> str | None:
        """Nearest earlier ErrorStmt/broken declaration (current function body, then file scope) naming ``name``."""
        lists = ([self.func.lost] if self.func else []) + [self.file_lost]
        for lost in lists:
            for n, eid in reversed(lost):
                if n == name:
                    return eid
        return None

    def declare(self, name: str, typ: object, pos: Position, kind: str, decl: object) -> Symbol | None:
        scope = self.scopes[-1]
        prev = scope.symbols.get(name)
        if prev is not None:
            self.report("SEM-REDECLARED", pos, found=name, name=name, prev_line=prev.pos.line)
            return None
        sym = Symbol(name, typ, pos, kind, decl, err_mark=len(scope.error_nodes))
        scope.symbols[name] = sym
        scope.order.append(sym)
        return sym

    def ensure_printf(self, at: Position) -> None:
        """sem.builtins: printf exists only after an accepted #include <stdio.h>."""
        if self.printf_declared or self.stdio is None:
            return
        if (self.stdio.line, self.stdio.column) < (at.line, at.column):
            self.printf_declared = True
            file_scope = self.scopes[0]
            if "printf" not in file_scope.symbols:
                sym = Symbol("printf", FuncType(INT, ()), self.stdio, "func", None, defined=True)
                file_scope.symbols["printf"] = sym

    # ------------------------------------------------------------ program
    def program(self, prog: A.Program) -> None:
        for d in prog.decls:
            start = Position(d.span.start_line, d.span.start_col)
            self.ensure_printf(start)
            if isinstance(d, A.FunctionDecl):
                self.function(d)
            elif isinstance(d, A.VarDeclStmt):
                for vd in d.decls:
                    self.global_var(vd)
            elif isinstance(d, A.ErrorStmt):
                self.error_stmt(d)
        self.check_main(prog)

    def check_main(self, prog: A.Program) -> None:
        sym = self.scopes[0].symbols.get("main")
        ok = (sym is not None and isinstance(sym.type, FuncType) and sym.defined
              and sym.type.ret == INT and sym.type.params == ())
        if not ok:
            eof = eof_position(prog)
            self.report("SEM-MISSING-MAIN", eof, found="EOF", end=eof, caused_by=self.r5("main"))

    def error_stmt(self, s: A.ErrorStmt) -> None:
        """docs/error-recovery.md §6: do nothing except remember it for R5/R6/R7/R8."""
        self.error_kinds[s.error_id] = s.kind_hint
        for name, _type in s.declared_names:
            self.note_lost(name, s.error_id)
        if len(self.scopes) > 1:
            self.note_error_node(s.error_id, s.idents_in_span)
        if self.func is not None and self.func.first_error_stmt is None:
            self.func.first_error_stmt = s.error_id

    # ------------------------------------------------------------ declarations
    def var_type(self, vd: A.VarDecl) -> object:
        if vd.array_size is None:
            return vd.type_name
        size = vd.array_size.value if isinstance(vd.array_size, A.IntLit) else None
        return ArrayType(vd.type_name, size if size and size > 0 else None)

    def check_array_size(self, vd: A.VarDecl) -> None:
        size = vd.array_size
        if size is None:
            return
        if isinstance(size, A.IntLit) and size.value > 0:
            return
        cause = size.error_id if isinstance(size, A.ErrorExpr) else None                       # R3
        self.report("SEM-BAD-ARRAY-SIZE", self.start(size), found=unparse(size), end=self.end(size),
                    caused_by=cause)
        if not isinstance(size, A.ErrorExpr):
            self.expr(size)                       # still analysed: names inside are reads / undeclared

    def global_var(self, vd: A.VarDecl) -> None:
        typ = self.declare_var(vd, "global")
        self.check_array_size(vd)
        if vd.error_id:
            self.note_lost(vd.name, vd.error_id)
        if vd.init is None:
            return
        init = vd.init
        shape_ok = (isinstance(init, (A.IntLit, A.FloatLit, A.CharLit, A.StringLit))
                    or (isinstance(init, A.Unary) and init.op == "-" and not init.postfix
                        and isinstance(init.operand, (A.IntLit, A.FloatLit, A.CharLit))))
        if not shape_ok:
            bad = init.operand if isinstance(init, A.Unary) and init.op == "-" else init
            cause = bad.error_id if isinstance(bad, A.ErrorExpr) else None                       # R3
            self.report("SEM-NONCONST-GLOBAL-INIT", self.start(init), found=unparse(init), end=self.end(init),
                        caused_by=cause)
            if not isinstance(init, A.ErrorExpr):
                self.expr(init)
            return
        t = self.expr(init)
        self.convert(t, typ, init, at=vd.name_pos, ctx="init", name=vd.name)

    def declare_var(self, vd: A.VarDecl, kind: str) -> object:
        typ = self.var_type(vd)
        if vd.type_name == VOID:
            rec = self.report("SEM-VOID-VALUE", vd.name_pos, found=vd.name)
            typ = ErrorType(rec.id)
        # a void variable already has SEM-VOID-VALUE; it is not also tracked for WRN-UNUSED-VAR
        self.declare(vd.name, typ, vd.name_pos, "void" if vd.type_name == VOID else kind, vd)
        return typ

    def local_var(self, vd: A.VarDecl) -> None:
        typ = self.declare_var(vd, "var")
        self.check_array_size(vd)
        if vd.error_id:
            self.note_lost(vd.name, vd.error_id)
            self.note_error_node(vd.error_id, vd.idents_in_span)
        if vd.init is None:
            return
        t = self.expr(vd.init)
        if isinstance(typ, ArrayType):
            if not is_err(t):
                self.report("SEM-TYPE-MISMATCH", vd.name_pos, found=type_name(t), expected=[type_name(typ)],
                            end=self.name_end(vd.name_pos, vd.name))
            return
        self.convert(t, typ, vd.init, at=vd.name_pos, ctx="init", name=vd.name)

    def signature(self, f: A.FunctionDecl) -> FuncType:
        return FuncType(f.ret_type, tuple(p.type_name for p in f.params))

    def function(self, f: A.FunctionDecl) -> None:
        sig = self.signature(f)
        file_scope = self.scopes[0]
        prev = file_scope.symbols.get(f.name)
        if f.error_id:
            self.note_lost(f.name, f.error_id)
        if prev is None:
            sym = Symbol(f.name, sig, f.name_pos, "func", f, defined=f.body is not None)
            file_scope.symbols[f.name] = sym
            file_scope.order.append(sym)
        elif not isinstance(prev.type, FuncType) or (prev.decl is None and f.name == "printf"):
            self.report("SEM-REDECLARED", f.name_pos, found=f.name, name=f.name, prev_line=prev.pos.line)
        elif prev.type != sig:
            self.report("SEM-CONFLICTING-TYPES", f.name_pos, found=f.name, name=f.name,
                        prev_sig=sig_text(f.name, prev.type), sig=sig_text(f.name, sig))
            prev.defined = prev.defined or f.body is not None
        elif prev.defined and f.body is not None:
            self.report("SEM-REDECLARED", f.name_pos, found=f.name, name=f.name, prev_line=prev.pos.line)
        else:
            prev.defined = prev.defined or f.body is not None
        # parameters live in the body's outermost scope (sem.unique_in_scope)
        self.push()
        for p in f.params:
            ptype: object = p.type_name
            if p.type_name == VOID:
                ptype = ErrorType(self.report("SEM-VOID-VALUE", p.name_pos, found=p.name).id)
            self.declare(p.name, ptype, p.name_pos, "param", p)
        if f.body is None:
            self.scopes.pop()                  # prototype: no unused check
            return
        self.func = FuncCtx(f, f.ret_type)
        self.stmts(f.body.stmts)               # the body Block shares the parameter scope
        self.pop()                             # WRN-UNUSED-VAR for the outermost scope
        if f.ret_type != VOID and f.name != "main" and not returns(f.body):
            cause = self.func.first_error_stmt or f.body.closed_by_repair                    # R8
            self.report("WRN-MISSING-RETURN", f.name_pos, found=f.name, caused_by=cause, name=f.name)
        self.func = None

    # ------------------------------------------------------------ statements
    def stmts(self, stmts: list) -> None:
        terminated = warned = False
        for s in stmts:
            if terminated and not warned:
                warned = True                  # one warning per block, at the first statement after
                if not isinstance(s, A.ErrorStmt):
                    self.report("WRN-UNREACHABLE-CODE", self.start(s), found=first_token(s))
            self.stmt(s)
            if isinstance(s, (A.Break, A.Continue)) or returns(s):
                terminated = True          # a return, break or continue, or anything that returns on every path

    def stmt(self, s: object) -> None:
        if isinstance(s, A.VarDeclStmt):
            for vd in s.decls:
                self.local_var(vd)
        elif isinstance(s, A.Block):
            pushed_orphan = s.orphan_of is not None and self.error_kinds.get(s.orphan_of) in ("while", "for", "unsupported")
            if pushed_orphan:
                self.loop_stack.append(s.orphan_of)
            self.push()
            self.stmts(s.stmts)
            self.pop()
            if pushed_orphan:
                self.loop_stack.pop()
        elif isinstance(s, A.ExprStmt):
            self.expr(s.expr)
        elif isinstance(s, A.If):
            self.condition(s.cond)
            self.stmt(s.then)
            if s.els is not None:
                self.stmt(s.els)
        elif isinstance(s, A.While):
            self.condition(s.cond)
            self.loop_body(s.body)
        elif isinstance(s, A.For):
            self.push()                        # the for-init scope (C99 6.8.5p5)
            if isinstance(s.init, A.VarDeclStmt):
                for vd in s.init.decls:
                    self.local_var(vd)
            elif s.init is not None:
                self.expr(s.init)
            if s.cond is not None:
                self.condition(s.cond)
            if s.step is not None:
                self.expr(s.step)
            self.loop_body(s.body)
            self.pop()
        elif isinstance(s, A.Return):
            self.return_stmt(s)
        elif isinstance(s, (A.Break, A.Continue)):
            self.loop_control(s)
        elif isinstance(s, A.ErrorStmt):
            self.error_stmt(s)
        # EmptyStmt: nothing

    def loop_body(self, body: object) -> None:
        self.loop_stack.append("loop")
        self.stmt(body)
        self.loop_stack.pop()

    def loop_control(self, s: object) -> None:
        if "loop" in self.loop_stack:
            return
        word = "break" if isinstance(s, A.Break) else "continue"
        cause = self.loop_stack[-1] if self.loop_stack else None                                # R7
        self.report("SEM-BREAK-OUTSIDE-LOOP", self.start(s), found=word, caused_by=cause)

    def condition(self, cond: object) -> None:
        t = self.expr(cond)
        self.require_value(t, cond, expected="an arithmetic value")
        if isinstance(cond, A.Assign) and cond.op == "=":
            self.report("WRN-ASSIGN-IN-CONDITION", cond.op_pos, found="=", end=cond.op_pos)

    def return_stmt(self, s: A.Return) -> None:
        fn = self.func
        at = self.start(s)
        name = fn.decl.name
        if s.value is None:
            if fn.ret != VOID:
                self.report("SEM-RETURN-TYPE", at, found="nothing", end=Position(at.line, at.column + 5),
                            expected=[fn.ret], name=name)
            return
        t = self.expr(s.value)
        if fn.ret == VOID:
            if not is_err(t):
                self.report("SEM-RETURN-TYPE", at, found=type_name(t), end=Position(at.line, at.column + 5),
                            expected=[VOID], name=name)
            return
        self.convert(t, fn.ret, s.value, at=at, ctx="return", name=name)

    # ------------------------------------------------------------ conversions
    def require_value(self, t: object, node: object, expected: str, integer: bool = False,
                      at: Position | None = None, op: str = "") -> object:
        """Check that an operand is a usable (arithmetic / integer) value. Returns the type to continue with."""
        if is_err(t):
            return t
        if t == VOID:
            return ErrorType(self.void_value(node).id)
        if not is_arith(t) or (integer and t not in INTEGER_TYPES):
            loc = at or self.start(node)
            end = op_end(at, op) if at else self.end(node)
            rec = self.report("SEM-TYPE-MISMATCH", loc, found=type_name(t), expected=[expected], end=end)
            return ErrorType(rec.id)
        return t

    def void_value(self, node: object) -> ErrorRecord:
        if isinstance(node, A.Call) and isinstance(node.callee, A.Name):
            return self.report("SEM-VOID-VALUE", self.start(node.callee), found=node.callee.name)
        return self.report("SEM-VOID-VALUE", self.start(node), found=unparse(node), end=self.end(node))

    def convert(self, t: object, target: object, node: object, *, at: Position, ctx: str, name: str,
                index: int = 0) -> None:
        """Assignment / initialisation / argument / return conversion (spec §3)."""
        if is_err(t) or is_err(target):
            return
        if t == VOID:
            self.void_value(node)
            return
        if not is_arith(t):
            if ctx == "arg":
                self.report("SEM-ARG-TYPE", at, found=type_name(t), expected=[type_name(target)],
                            end=self.name_end(at, name), name=name, index=index)
            elif ctx == "return":
                self.report("SEM-RETURN-TYPE", at, found=type_name(t), expected=[type_name(target)],
                            end=Position(at.line, at.column + 5), name=name)
            else:
                end = self.name_end(at, name) if ctx == "init" else at
                self.report("SEM-TYPE-MISMATCH", at, found=type_name(t), expected=[type_name(target)], end=end)
            return
        if t in FLOATING_TYPES and target in INTEGER_TYPES:
            end = (self.name_end(at, name) if ctx in ("init", "arg") else
                   Position(at.line, at.column + 5) if ctx == "return" else at)
            self.report("WRN-IMPLICIT-NARROWING", at, found=t, expected=[target], end=end)

    # ------------------------------------------------------------ expressions
    def expr(self, e: object, *, write: bool = False) -> object:
        """Analyse an expression and return its type. ``write`` marks a plain '=' target (not a read)."""
        if isinstance(e, A.IntLit):
            return INT
        if isinstance(e, A.FloatLit):
            return DOUBLE
        if isinstance(e, A.CharLit):
            return CHAR
        if isinstance(e, A.StringLit):
            return STRING
        if isinstance(e, A.ErrorExpr):
            return ErrorType(e.error_id)
        if isinstance(e, A.Name):
            return self.name(e, write=write)
        if isinstance(e, A.Index):
            return self.index(e, write=write)
        if isinstance(e, A.Call):
            return self.call(e)
        if isinstance(e, A.Assign):
            return self.assign(e)
        if isinstance(e, A.Unary):
            return self.unary(e)
        if isinstance(e, A.Binary):
            return self.binary(e)
        raise TypeError(f"unknown expression node {e!r}")

    def name(self, e: A.Name, *, write: bool = False) -> object:
        sym = self.lookup(e.name)
        if sym is None:
            rec = self.report("SEM-UNDECLARED-VAR", self.start(e), found=e.name, caused_by=self.r5(e.name),
                              name=e.name)
            return ErrorType(rec.id)
        if not write:
            sym.read = True
        return sym.type

    def index(self, e: A.Index, *, write: bool = False) -> object:
        base_t = self.expr(e.base, write=write)
        result: object
        if is_err(base_t):
            result = base_t
        elif isinstance(base_t, ArrayType):
            result = base_t.elem
        else:
            label = e.base.name if isinstance(e.base, A.Name) else unparse(e.base)
            rec = self.report("SEM-NOT-ARRAY", self.start(e.base), found=label, end=self.end(e.base), name=label)
            result = ErrorType(rec.id)
        idx_t = self.expr(e.index)
        if not is_err(idx_t):
            if idx_t == VOID:
                self.void_value(e.index)
            elif idx_t not in INTEGER_TYPES:
                self.report("SEM-INDEX-NOT-INT", self.start(e.index), found=type_name(idx_t), end=self.end(e.index))
        return result

    def call(self, e: A.Call) -> object:
        callee = e.callee
        if not isinstance(callee, A.Name):
            t = self.expr(callee)
            for a in e.args:
                self.expr(a)
            if is_err(t):
                return t
            label = unparse(callee)
            return ErrorType(self.report("SEM-NOT-CALLABLE", self.start(callee), found=label, end=self.end(callee),
                                         name=label).id)
        name = callee.name
        at = self.start(callee)
        if name == "printf":
            self.ensure_printf(at)
        sym = self.lookup(name)
        if sym is None:
            rec = self.report("SEM-UNDECLARED-FUNC", at, found=name, caused_by=self.r5(name), name=name)
            for a in e.args:
                self.expr(a)
            return ErrorType(rec.id)
        if not isinstance(sym.type, FuncType):
            sym.read = True
            if is_err(sym.type):
                for a in e.args:
                    self.expr(a)
                return sym.type
            rec = self.report("SEM-NOT-CALLABLE", at, found=name, name=name)
            for a in e.args:
                self.expr(a)
            return ErrorType(rec.id)
        ftype: FuncType = sym.type
        if sym.decl is None and name == "printf":                  # the builtin
            first = e.args[0] if e.args else None
            if not isinstance(first, A.StringLit):
                cause = first.error_id if isinstance(first, A.ErrorExpr) else None                   # R3
                self.report("SEM-PRINTF-FORMAT", at, found=name, caused_by=cause)
            types = [self.expr(a) for a in e.args]
            for i, (a, t) in enumerate(zip(e.args, types), start=1):
                if i == 1:
                    continue                    # the format: checked above by shape (SEM-PRINTF-FORMAT)
                if t == VOID:
                    self.void_value(a)
                elif not is_err(t) and not is_arith(t):
                    self.report("SEM-ARG-TYPE", at, found=type_name(t), expected=["an arithmetic value"],
                                name=name, index=i)
            return INT
        if len(e.args) != len(ftype.params):
            self.report("SEM-ARG-COUNT", at, found=str(len(e.args)), expected=[str(len(ftype.params))],
                        end=self.name_end(at, name), name=name)
            for a in e.args:
                self.expr(a)
            return ftype.ret
        types = [self.expr(a) for a in e.args]
        for i, (a, t, p) in enumerate(zip(e.args, types, ftype.params), start=1):
            self.convert(t, p, a, at=at, ctx="arg", name=name, index=i)
        return ftype.ret

    def assign(self, e: A.Assign) -> object:
        plain = e.op == "="
        tt = self.expr(e.target, write=plain)              # '=' writes; compound ops read and write (plan 004)
        vt = self.expr(e.value)
        if is_err(tt):
            return tt
        if not is_arith(tt):                               # array name, function name, void...
            rec = self.report("SEM-TYPE-MISMATCH", e.op_pos, found=type_name(tt),
                              expected=["a variable or array element"], end=op_end(e.op_pos, e.op))
            return ErrorType(rec.id)
        if plain:
            self.convert(vt, tt, e.value, at=e.op_pos, ctx="assign", name="")
            return tt
        integer = e.op == "%="
        vt = self.require_value(vt, e.value, "an integer" if integer else "an arithmetic value", integer=integer,
                                at=e.op_pos, op=e.op)
        if integer and tt not in INTEGER_TYPES:
            self.report("SEM-TYPE-MISMATCH", e.op_pos, found=tt, expected=["an integer"], end=op_end(e.op_pos, e.op))
            return tt
        if is_err(vt):
            return tt
        result = usual_arith(tt, vt)
        if result in FLOATING_TYPES and tt in INTEGER_TYPES:
            self.report("WRN-IMPLICIT-NARROWING", e.op_pos, found=result, expected=[tt], end=op_end(e.op_pos, e.op))
        return tt

    def unary(self, e: A.Unary) -> object:
        if e.op in ("++", "--"):
            t = self.expr(e.operand)                       # read and write (plan 004)
            op_at = Position(e.span.end_line, e.span.end_col - 1) if e.postfix else self.start(e)
            return self.require_value(t, e.operand, "an arithmetic value", at=op_at, op=e.op)
        t = self.expr(e.operand)
        t = self.require_value(t, e.operand, "an arithmetic value", at=self.start(e), op=e.op)
        if is_err(t):
            return t
        if e.op == "!":
            return INT
        return INT if t == CHAR else t

    def binary(self, e: A.Binary) -> object:
        lt = self.expr(e.left)
        rt = self.expr(e.right)
        integer = e.op == "%"
        want = "an integer" if integer else "an arithmetic value"
        lt = self.require_value(lt, e.left, want, integer=integer, at=e.op_pos, op=e.op)
        if is_err(lt):
            return lt
        rt = self.require_value(rt, e.right, want, integer=integer, at=e.op_pos, op=e.op)
        if is_err(rt):
            return rt
        if e.op in ("+", "-", "*", "/"):
            return usual_arith(lt, rt)
        return INT                                        # %, comparisons, equality, && and ||

    # ------------------------------------------------------------ positions
    @staticmethod
    def start(node: object) -> Position:
        return Position(node.span.start_line, node.span.start_col)

    @staticmethod
    def end(node: object) -> Position:
        return Position(node.span.end_line, node.span.end_col)

    @staticmethod
    def name_end(at: Position, name: str) -> Position:
        return Position(at.line, at.column + max(len(name), 1) - 1)


# ---------------------------------------------------------------- pure helpers
def eof_position(prog: A.Program) -> Position:
    """The EOF token's position (docs/error-recovery.md §8); contract §4: Program.span ends at it."""
    return Position(prog.span.end_line, prog.span.end_col)


def op_end(at: Position, op: str) -> Position:
    """Inclusive end of an operator token that starts at ``at``."""
    return Position(at.line, at.column + max(len(op), 1) - 1)


def returns(s: object) -> bool:
    """sem.return_paths: does ``s`` return on every path?

    A ``return`` does; a block does if ANY of its statements does (what follows is
    unreachable, sem.unreachable); an ``if`` does if it has an ``else`` and both
    branches do. Loops never count.
    """
    if isinstance(s, A.Return):
        return True
    if isinstance(s, A.Block):
        return any(returns(x) for x in s.stmts)
    if isinstance(s, A.If):
        return s.els is not None and returns(s.then) and returns(s.els)
    return False                                          # loops never count (spec)


def unparse(e: object) -> str:
    """Source-like text of an expression, for ``found`` fields."""
    if isinstance(e, A.IntLit):
        return str(e.value)
    if isinstance(e, A.FloatLit):
        return repr(e.value)
    if isinstance(e, A.CharLit):
        return repr(e.value)
    if isinstance(e, A.StringLit):
        return '"' + e.value.replace("\n", "\\n") + '"'
    if isinstance(e, A.Name):
        return e.name
    if isinstance(e, A.ErrorExpr):
        return "<error>"
    if isinstance(e, A.Unary):
        return f"{unparse(e.operand)}{e.op}" if e.postfix else f"{e.op}{unparse(e.operand)}"
    if isinstance(e, A.Binary):
        return f"{unparse(e.left)} {e.op} {unparse(e.right)}"
    if isinstance(e, A.Assign):
        return f"{unparse(e.target)} {e.op} {unparse(e.value)}"
    if isinstance(e, A.Call):
        return f"{unparse(e.callee)}({', '.join(unparse(a) for a in e.args)})"
    if isinstance(e, A.Index):
        return f"{unparse(e.base)}[{unparse(e.index)}]"
    return "?"


def first_token(s: object) -> str:
    """Text of the first token of a statement (``found`` of WRN-UNREACHABLE-CODE)."""
    words = {A.Return: "return", A.Break: "break", A.Continue: "continue", A.If: "if", A.While: "while",
             A.For: "for", A.Block: "{", A.EmptyStmt: ";"}
    for cls, w in words.items():
        if isinstance(s, cls):
            return w
    if isinstance(s, A.VarDeclStmt):
        return s.decls[0].type_name
    if isinstance(s, A.ExprStmt):
        e = s.expr
        while True:
            if isinstance(e, A.Assign):
                e = e.target
            elif isinstance(e, A.Binary):
                e = e.left
            elif isinstance(e, A.Call):
                e = e.callee
            elif isinstance(e, A.Index):
                e = e.base
            elif isinstance(e, A.Unary):
                if not e.postfix:
                    return e.op
                e = e.operand
            else:
                return unparse(e)
    return "?"


def analyze(program: A.Program, sink: ErrorSink, stdio_include: Position | None) -> None:
    """Run the semantic phase on ``program`` and report through ``sink``. Never raises on a partial AST."""
    Analyzer(sink, stdio_include).program(program)
