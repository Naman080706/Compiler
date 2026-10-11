"""Semantic analysis: the third compiler phase (PRD F1), plan 007, extended to course-level C.

``analyze(program, sink, includes)`` walks the AST built by the parser once,
depth-first and left to right in source order (docs/error-recovery.md §6), and
reports every ``sem.*`` violation of docs/language-spec.md §4 through the
error sink. It never raises on a partial AST: ``ErrorStmt`` nodes are skipped,
``ErrorExpr`` nodes have the ``<error>`` type, and ``caused_by`` is set only by
rules R3-R8 (docs/error-recovery.md §7, as amended by plan 004).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cea import ast as A
from cea import stdlib_decls
from cea.diagnostics import ErrorSink
from cea.records import ErrorRecord, Position

# ---------------------------------------------------------------- types
# Scalar types are plain strings (their canonical C name). Everything else is a small frozen dataclass.
INT, CHAR, FLOAT, DOUBLE, VOID, BOOL = "int", "char", "float", "double", "void", "_Bool"
INTEGER_TYPES = frozenset({
    "char", "signed char", "unsigned char", "short", "unsigned short", "int", "unsigned int", "long",
    "unsigned long", "long long", "unsigned long long", BOOL,
})
FLOATING_TYPES = frozenset({"float", "double", "long double"})
ARITHMETIC_TYPES = INTEGER_TYPES | FLOATING_TYPES
RANK = {BOOL: 0, "char": 1, "signed char": 1, "unsigned char": 1, "short": 2, "unsigned short": 2, "int": 3,
        "unsigned int": 3, "long": 4, "unsigned long": 4, "long long": 5, "unsigned long long": 5}


@dataclass(frozen=True)
class PointerType:
    base: object
    base_const: bool = False       # the pointed-to type is const (const char *p)


@dataclass(frozen=True)
class ArrayType:
    elem: object                   # any type (an ArrayType for a multi-dimensional array)
    size: int | None               # None when the size is unknown or the size expression was bad
    const: bool = False            # the elements are const
    literal: bool = field(default=False, compare=False)   # the type of a string literal


@dataclass(frozen=True)
class StructType:
    kind: str                      # "struct" | "union"
    tag: str
    uid: int


@dataclass(frozen=True)
class EnumType:
    tag: str


@dataclass(frozen=True)
class FuncType:
    ret: object
    params: tuple
    variadic: bool = False


@dataclass(frozen=True)
class ErrorType:
    cause: str                     # id of the record that explains the unknown type


@dataclass
class StructInfo:
    kind: str
    tag: str
    members: dict[str, object] = field(default_factory=dict)
    complete: bool = False


NONCONST = object()                # const_int: not a constant expression
UNKNOWN = object()                 # const_int: a constant whose value is not computed


def type_name(t: object) -> str:
    """Human-readable type for messages and the ``found``/``expected`` fields."""
    if isinstance(t, PointerType):
        return ("const " if t.base_const else "") + type_name(t.base) + "*"
    if isinstance(t, ArrayType):
        if t.literal:
            return "string literal"
        return f"array {type_name(t.elem)}[{t.size if t.size is not None else ''}]"
    if isinstance(t, StructType):
        return f"{t.kind} " + ("<anonymous>" if t.tag.startswith("<") else t.tag)
    if isinstance(t, EnumType):
        return "enum " + ("<anonymous>" if t.tag.startswith("<") else t.tag)
    if isinstance(t, FuncType):
        return f"function {sig_text('', t)}".replace("  ", " ")
    if isinstance(t, ErrorType):
        return "<error>"
    return str(t)


def sig_text(name: str, f: FuncType) -> str:
    params = [type_name(p) for p in f.params] + (["..."] if f.variadic else [])
    return f"{type_name(f.ret)} {name}({', '.join(params) if params else 'void'})"


def is_arith(t: object) -> bool:
    return (isinstance(t, str) and t in ARITHMETIC_TYPES) or isinstance(t, EnumType)


def is_integer(t: object) -> bool:
    return (isinstance(t, str) and t in INTEGER_TYPES) or isinstance(t, EnumType)


def is_err(t: object) -> bool:
    return isinstance(t, ErrorType)


def decay(t: object) -> object:
    """Array-to-pointer decay."""
    if isinstance(t, ArrayType):
        return PointerType(t.elem, t.const)
    return t


def is_pointer(t: object) -> bool:
    return isinstance(decay(t), PointerType)


def is_scalar(t: object) -> bool:
    return is_arith(t) or is_pointer(t)


def promote(t: str) -> str:
    if isinstance(t, EnumType):
        return INT
    return INT if RANK.get(t, 3) < 3 else t


def usual_arith(a: object, b: object) -> str:
    """Usual arithmetic conversions of spec §3 (small integers become int)."""
    if "long double" in (a, b):
        return "long double"
    if DOUBLE in (a, b):
        return DOUBLE
    if FLOAT in (a, b):
        return FLOAT
    a, b = promote(a), promote(b)
    if a == b:
        return a
    ra, rb = RANK[a], RANK[b]
    if ra != rb:
        return a if ra > rb else b
    return a if a.startswith("unsigned") else b


# ---------------------------------------------------------------- symbols and scopes
@dataclass
class Symbol:
    name: str
    type: object
    pos: Position                  # name position of the (first) declaration
    kind: str                      # "var" | "param" | "global" | "func" | "typedef" | "enumconst" | "const" | "void"
    decl: object = None            # VarDecl / Param / FunctionDecl (None for builtins)
    read: bool = False
    defined: bool = False          # functions: a body has been seen
    err_mark: int = 0              # len(scope.error_nodes) when declared (R6)
    const: bool = False            # the object itself is const
    builtin: bool = False
    value: int | None = None       # enumconst / builtin constant value
    extern: bool = False


@dataclass
class Scope:
    symbols: dict[str, Symbol] = field(default_factory=dict)
    order: list[Symbol] = field(default_factory=list)            # declaration order (WRN-UNUSED-VAR)
    error_nodes: list[tuple[str, set]] = field(default_factory=list)  # (error_id, idents) in source order (R6)
    tags: dict[str, object] = field(default_factory=dict)        # "struct P" / "union U" / "enum E" -> type


@dataclass
class FuncCtx:
    decl: A.FunctionDecl
    ret: object
    lost: list[tuple[str, str]] = field(default_factory=list)   # (name, error_id) for R5, source order
    first_error_stmt: str | None = None                         # R8


@dataclass
class SwitchCtx:
    seen: dict[int, int] = field(default_factory=dict)          # case value -> line of its first label
    default_line: int | None = None


FILE_STRUCT = StructType("struct", "_IO_FILE", 0)


class Analyzer:
    def __init__(self, sink: ErrorSink, includes: list[tuple[str, Position]]) -> None:
        self.sink = sink
        self.pending_includes = sorted(includes, key=lambda hp: (hp[1].line, hp[1].column))
        self.scopes: list[Scope] = [Scope()]           # [0] is file scope
        self.file_lost: list[tuple[str, str]] = []     # (name, error_id) at file scope, source order (R5)
        self.error_kinds: dict[str, str] = {}          # ErrorStmt.error_id -> kind_hint (R7)
        self.loop_stack: list[str | None] = []         # "loop", "switch" or an orphan error_id (R7)
        self.switch_stack: list[SwitchCtx] = []
        self.func: FuncCtx | None = None
        self.structs: dict[int, StructInfo] = {0: StructInfo("struct", "_IO_FILE", complete=True)}
        self.etype: dict[int, object] = {}             # id(expression node) -> its type (for const checks)

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

    def lookup_tag(self, key: str) -> object | None:
        for scope in reversed(self.scopes):
            if key in scope.tags:
                return scope.tags[key]
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

    def declare(self, name: str, typ: object, pos: Position, kind: str, decl: object, *,
                const: bool = False) -> Symbol | None:
        scope = self.scopes[-1]
        prev = scope.symbols.get(name)
        if prev is not None:
            self.report("SEM-REDECLARED", pos, found=name, name=name, prev_line=prev.pos.line)
            return None
        sym = Symbol(name, typ, pos, kind, decl, err_mark=len(scope.error_nodes), const=const)
        scope.symbols[name] = sym
        scope.order.append(sym)
        return sym

    # ------------------------------------------------------------ builtins (sem.builtins)
    def ensure_builtins(self, at: Position) -> None:
        """Declare the names of every supported header whose #include precedes ``at``."""
        while self.pending_includes and (self.pending_includes[0][1].line, self.pending_includes[0][1].column) \
                < (at.line, at.column):
            header, pos = self.pending_includes.pop(0)
            self.load_header(header, pos)

    def c_type(self, text: str) -> object:
        """A C type written as text in stdlib_decls ('const char*', 'size_t', 'FILE*')."""
        text = text.strip()
        const = text.startswith("const ")
        if const:
            text = text[6:]
        stars = text.count("*")
        base_text = text.replace("*", "").strip()
        base: object = {"size_t": "unsigned long", "FILE": FILE_STRUCT}.get(base_text, base_text)
        t = base
        for i in range(stars):
            t = PointerType(t, const and i == 0)
        return t

    def load_header(self, header: str, pos: Position) -> None:
        scope = self.scopes[0]
        for name, ret, params, variadic in stdlib_decls.parse_functions(header):
            if name not in scope.symbols:
                ftype = FuncType(self.c_type(ret), tuple(self.c_type(p) for p in params), variadic)
                scope.symbols[name] = Symbol(name, ftype, pos, "func", None, defined=True, builtin=True)
        for name, text in stdlib_decls.CONSTANTS.get(header, {}).items():
            if name not in scope.symbols:
                scope.symbols[name] = Symbol(name, self.c_type(text), pos, "const", None, builtin=True,
                                             value=stdlib_decls.CONSTANT_VALUES.get(name))
        for name, text in stdlib_decls.TYPEDEFS.get(header, {}).items():
            if name not in scope.symbols:
                scope.symbols[name] = Symbol(name, self.c_type(text), pos, "typedef", None, builtin=True)

    # ------------------------------------------------------------ program
    def program(self, prog: A.Program) -> None:
        for d in prog.decls:
            start = Position(d.span.start_line, d.span.start_col)
            self.ensure_builtins(start)
            if isinstance(d, A.FunctionDecl):
                self.function(d)
            elif isinstance(d, A.VarDeclStmt):
                self.global_decl(d)
            elif isinstance(d, A.ErrorStmt):
                self.error_stmt(d)
        self.check_main(prog)

    def check_main(self, prog: A.Program) -> None:
        sym = self.scopes[0].symbols.get("main")
        ok = (sym is not None and isinstance(sym.type, FuncType) and sym.defined
              and sym.type.ret == INT and (sym.type.params == () or sym.type.params == (
                  INT, PointerType(PointerType(CHAR)))))
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

    # ------------------------------------------------------------ user-defined types
    def tag_key(self, kind: str, tag: str | None, span: A.Span) -> str:
        return f"{kind} {tag}" if tag else f"{kind} <anonymous {span.start_line}:{span.start_col}>"

    def define_type(self, td: A.StructDef | A.EnumDef | None) -> None:
        if isinstance(td, A.StructDef):
            self.define_struct(td)
        elif isinstance(td, A.EnumDef):
            self.define_enum(td)

    def struct_type_named(self, text: str, pos: Position) -> object:
        """The type for 'struct P' / 'union U' / 'enum E' used without a definition."""
        found = self.lookup_tag(text)
        if found is not None:
            return found
        kind, tag = text.split(" ", 1)
        if kind == "enum":
            t: object = EnumType(tag)
        else:
            uid = len(self.structs)
            self.structs[uid] = StructInfo(kind, tag)
            t = StructType(kind, tag, uid)
        self.scopes[-1].tags[text] = t
        return t

    def define_struct(self, sd: A.StructDef) -> None:
        key = self.tag_key(sd.kind, sd.tag, sd.span)
        existing = self.scopes[-1].tags.get(key)
        if isinstance(existing, StructType) and not self.structs[existing.uid].complete:
            st = existing
        else:
            if existing is not None and sd.name_pos is not None:
                self.report("SEM-REDECLARED", sd.name_pos, found=sd.tag or key, name=key, prev_line=sd.span.start_line)
            uid = len(self.structs)
            self.structs[uid] = StructInfo(sd.kind, key.split(" ", 1)[1])
            st = StructType(sd.kind, key.split(" ", 1)[1], uid)
            self.scopes[-1].tags[key] = st
        info = self.structs[st.uid]
        info.complete = True                          # members may point back to the struct itself
        for m in sd.members:
            self.define_type(m.type_def)
            t = self.declared_type(m.type_name, m.ptr, False, m.const, m.dims, m.name_pos)
            if m.name in info.members:
                self.report("SEM-REDECLARED", m.name_pos, found=m.name, name=m.name, prev_line=m.name_pos.line)
                continue
            if t == VOID:
                self.report("SEM-VOID-VALUE", m.name_pos, found=m.name)
                continue
            self.check_complete(t, m.name_pos, m.name)
            info.members[m.name] = t

    def define_enum(self, ed: A.EnumDef) -> None:
        key = self.tag_key("enum", ed.tag, ed.span)
        et = EnumType(key.split(" ", 1)[1])
        self.scopes[-1].tags[key] = et
        nxt: int | None = 0
        for item in ed.items:
            value: int | None = nxt
            if item.value is not None:
                t = self.expr(item.value)
                v = self.const_int(item.value)
                if not is_err(t) and (v is NONCONST or not is_integer(t)):
                    self.report("SEM-CASE-NOT-CONSTANT", self.start(item.value), found=unparse(item.value),
                                end=self.end(item.value))
                value = v if isinstance(v, int) else None
            sym = self.declare(item.name, INT, item.name_pos, "enumconst", item)
            if sym is not None:
                sym.value = value
            nxt = value + 1 if value is not None else None

    def check_complete(self, t: object, pos: Position, name: str) -> bool:
        """A variable or member may not have an incomplete (declared, never defined) struct type."""
        base = t
        while isinstance(base, ArrayType):
            base = base.elem
        if isinstance(base, StructType) and not self.structs[base.uid].complete:
            self.report("SEM-INCOMPLETE-TYPE", pos, found=name, name=type_name(base),
                        caused_by=self.r5(type_name(base)))
            return False
        return True

    def resolve_base(self, name: str, pos: Position) -> object:
        """The type named by a declaration's base text."""
        if name in ARITHMETIC_TYPES or name == VOID:
            return name
        if name.startswith(("struct ", "union ", "enum ")):
            return self.struct_type_named(name, pos)
        sym = self.lookup(name)
        if sym is not None and sym.kind == "typedef":
            return sym.type
        return ErrorType(self.r5(name) or "")          # a typedef the parser rejected (e.g. a function pointer)

    def dim_value(self, d: object) -> int | None:
        if d is None or isinstance(d, A.ErrorExpr):
            return None
        v = self.const_int(d)
        return v if isinstance(v, int) and v > 0 else None

    def declared_type(self, base_text: str, ptr: int, ptr_const: bool, const: bool, dims: list,
                      pos: Position, init: object = None) -> object:
        """base type + stars + array dimensions (first dimension may be None: inferred from the initialiser)."""
        t: object = self.resolve_base(base_text, pos)
        for i in range(ptr):
            t = PointerType(t, const and i == 0)
        elem_const = const and ptr == 0
        sizes = [self.dim_value(d) for d in dims]
        if dims and dims[0] is None and sizes[0] is None:
            if isinstance(init, A.InitList):
                sizes[0] = len(init.items)
            elif isinstance(init, A.StringLit):
                sizes[0] = len(init.value) + 1
        for size in reversed(sizes):
            t = ArrayType(t, size, elem_const)
        return t

    # ------------------------------------------------------------ declarations
    def var_type(self, vd: A.VarDecl) -> object:
        dims = ([vd.array_size] + list(vd.more_dims)) if vd.is_array else []
        return self.declared_type(vd.type_name, vd.ptr, vd.ptr_const, vd.const, dims, vd.name_pos, vd.init)

    def check_array_size(self, vd: A.VarDecl) -> None:
        if not vd.is_array:
            return
        for i, size in enumerate([vd.array_size] + list(vd.more_dims)):
            if size is None:
                if i > 0 or vd.init is None:
                    self.report("SEM-BAD-ARRAY-SIZE", vd.name_pos, found=vd.name, end=self.name_end(vd.name_pos, vd.name))
                continue
            if isinstance(size, A.IntLit) and size.value > 0:
                continue
            v = None if isinstance(size, A.ErrorExpr) else self.const_int(size)
            if isinstance(v, int) and v > 0 or v is UNKNOWN:
                self.expr(size)
                continue
            cause = size.error_id if isinstance(size, A.ErrorExpr) else None                    # R3
            self.report("SEM-BAD-ARRAY-SIZE", self.start(size), found=unparse(size), end=self.end(size),
                        caused_by=cause)
            if not isinstance(size, A.ErrorExpr):
                self.expr(size)                   # still analysed: names inside are reads / undeclared

    def global_decl(self, d: A.VarDeclStmt) -> None:
        self.define_type(d.type_def)
        for vd in d.decls:
            if d.is_typedef:
                self.typedef_decl(vd)
            else:
                self.global_var(vd)

    def typedef_decl(self, vd: A.VarDecl) -> None:
        t = self.var_type(vd)
        self.check_array_size(vd)
        sym = self.declare(vd.name, t, vd.name_pos, "typedef", vd)
        if vd.error_id:
            self.note_lost(vd.name, vd.error_id)

    def global_var(self, vd: A.VarDecl) -> None:
        typ = self.declare_var(vd, "global")
        self.check_array_size(vd)
        if vd.error_id:
            self.note_lost(vd.name, vd.error_id)
        if vd.init is None:
            return
        init = vd.init
        if not self.is_const_init(init):
            bad = self.first_error(init)
            cause = bad.error_id if bad is not None else None                                    # R3
            self.report("SEM-NONCONST-GLOBAL-INIT", self.start(init), found=unparse(init), end=self.end(init),
                        caused_by=cause)
            if not isinstance(init, (A.ErrorExpr, A.InitList)):
                self.expr(init)
            return
        self.check_init(init, typ, vd)

    def declare_var(self, vd: A.VarDecl, kind: str) -> object:
        typ = self.var_type(vd)
        plain_void = vd.type_name == VOID and vd.ptr == 0 and not vd.is_array
        if plain_void:
            rec = self.report("SEM-VOID-VALUE", vd.name_pos, found=vd.name)
            typ = ErrorType(rec.id)
        elif not self.check_complete(typ, vd.name_pos, vd.name):
            plain_void = True                     # already reported; not also tracked as unused
        const = vd.const if vd.ptr == 0 else vd.ptr_const
        prev = self.scopes[-1].symbols.get(vd.name)
        if (prev is not None and vd.storage == "extern" or prev is not None and prev.extern) and prev.type == typ \
                and prev.kind == kind:
            prev.extern = prev.extern and vd.storage == "extern"
            return typ                                                      # extern int x; int x; (legal C)
        sym = self.declare(vd.name, typ, vd.name_pos, "void" if plain_void else kind, vd, const=const)
        if sym is not None:
            sym.extern = vd.storage == "extern"
        return typ

    def local_var(self, vd: A.VarDecl) -> None:
        typ = self.declare_var(vd, "var")
        self.check_array_size(vd)
        if vd.error_id:
            self.note_lost(vd.name, vd.error_id)
            self.note_error_node(vd.error_id, vd.idents_in_span)
        if vd.init is None:
            return
        if vd.storage == "static" and not self.is_const_init(vd.init):
            bad = self.first_error(vd.init)
            self.report("SEM-NONCONST-GLOBAL-INIT", self.start(vd.init), found=unparse(vd.init),
                        end=self.end(vd.init), caused_by=bad.error_id if bad is not None else None)
            if not isinstance(vd.init, (A.ErrorExpr, A.InitList)):
                self.expr(vd.init)
            return
        self.check_init(vd.init, typ, vd)

    def check_init(self, init: object, typ: object, vd: A.VarDecl) -> None:
        if isinstance(init, A.InitList):
            self.init_list(init, typ, vd)
            return
        t = self.expr(init)
        if isinstance(typ, ArrayType):
            if is_err(t) or is_err(typ):
                return
            if isinstance(init, A.StringLit) and typ.elem in ("char", "signed char", "unsigned char"):
                return
            self.report("SEM-TYPE-MISMATCH", vd.name_pos, found=type_name(t), expected=[type_name(typ)],
                        end=self.name_end(vd.name_pos, vd.name))
            return
        self.convert(t, typ, init, at=vd.name_pos, ctx="init", name=vd.name)

    def init_list(self, il: A.InitList, typ: object, vd: A.VarDecl | None = None) -> None:
        """Type-check '{...}' against an array, struct/union or scalar type."""
        if isinstance(typ, ArrayType):
            targets = [typ.elem] * len(il.items)
        elif isinstance(typ, StructType):
            info = self.structs[typ.uid]
            members = list(info.members.values())
            if typ.kind == "union":
                members = members[:1]
            targets = [members[i] if i < len(members) else None for i in range(len(il.items))]
        elif is_err(typ):
            targets = [typ] * len(il.items)
        else:
            targets = [typ if i == 0 else None for i in range(len(il.items))]
        for item, target in zip(il.items, targets):
            self.init_item(item, target)

    def init_item(self, item: object, target: object) -> None:
        if isinstance(item, A.InitList):
            self.init_list(item, target if target is not None else ErrorType(""))
            return
        t = self.expr(item)
        if target is None or is_err(target) or is_err(t):
            return
        if isinstance(target, (ArrayType, StructType)):
            if isinstance(target, ArrayType) and isinstance(item, A.StringLit):
                return
            if isinstance(t, StructType):
                if t != target:
                    self.report("SEM-TYPE-MISMATCH", self.start(item), found=type_name(t),
                                expected=[type_name(target)], end=self.end(item))
            return                                                          # brace elision: checked leniently
        self.convert(t, target, item, at=self.start(item), ctx="assign", name="")

    def signature(self, f: A.FunctionDecl) -> FuncType:
        ret: object = self.resolve_base(f.ret_type, f.name_pos)
        for i in range(f.ret_ptr):
            ret = PointerType(ret, f.ret_const and i == 0)
        params = []
        for p in f.params:
            params.append(self.param_type(p))
        return FuncType(ret, tuple(params))

    def param_type(self, p: A.Param) -> object:
        t = self.declared_type(p.type_name, p.ptr, p.ptr_const, p.const, [d for d in p.dims[1:]] if p.dims else [],
                               p.name_pos)
        if p.dims:                                    # the first array dimension decays to a pointer
            t = PointerType(t, p.const and p.ptr == 0)
        return t

    def function(self, f: A.FunctionDecl) -> None:
        self.define_type(f.type_def)
        sig = self.signature(f)
        file_scope = self.scopes[0]
        prev = file_scope.symbols.get(f.name)
        if f.error_id:
            self.note_lost(f.name, f.error_id)
        if prev is None:
            sym = Symbol(f.name, sig, f.name_pos, "func", f, defined=f.body is not None)
            file_scope.symbols[f.name] = sym
            file_scope.order.append(sym)
        elif not isinstance(prev.type, FuncType) or prev.builtin:
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
        for p, ptype in zip(f.params, sig.params):
            if p.type_name == VOID and p.ptr == 0 and not p.dims:
                ptype = ErrorType(self.report("SEM-VOID-VALUE", p.name_pos, found=p.name or "void").id)
            if p.name:
                self.declare(p.name, ptype, p.name_pos, "param", p,
                             const=p.const if p.ptr == 0 and not p.dims else p.ptr_const)
        if f.body is None:
            self.scopes.pop()                  # prototype: no unused check
            return
        self.func = FuncCtx(f, sig.ret)
        self.switch_stack = []
        self.stmts(f.body.stmts)               # the body Block shares the parameter scope
        self.pop()                             # WRN-UNUSED-VAR for the outermost scope
        if sig.ret != VOID and f.name != "main" and not returns(f.body):
            cause = self.func.first_error_stmt or f.body.closed_by_repair                    # R8
            self.report("WRN-MISSING-RETURN", f.name_pos, found=f.name, caused_by=cause, name=f.name)
        self.func = None

    # ------------------------------------------------------------ statements
    def stmts(self, stmts: list) -> None:
        terminated = warned = False
        for s in stmts:
            if isinstance(s, (A.Case, A.Default)):
                terminated = warned = False    # a label makes the code after it reachable again
            if terminated and not warned:
                warned = True                  # one warning per block, at the first statement after
                if not isinstance(s, A.ErrorStmt):
                    self.report("WRN-UNREACHABLE-CODE", self.start(s), found=first_token(s))
            self.stmt(s)
            if isinstance(s, (A.Break, A.Continue)) or returns(s):
                terminated = True          # a return, break or continue, or anything that returns on every path

    def stmt(self, s: object) -> None:
        if isinstance(s, A.VarDeclStmt):
            self.define_type(s.type_def)
            for vd in s.decls:
                if s.is_typedef:
                    self.typedef_decl(vd)
                else:
                    self.local_var(vd)
        elif isinstance(s, A.Block):
            pushed_orphan = s.orphan_of is not None and self.error_kinds.get(s.orphan_of) in (
                "while", "for", "do", "switch", "unsupported")
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
        elif isinstance(s, A.DoWhile):
            self.loop_body(s.body)
            self.condition(s.cond)
        elif isinstance(s, A.For):
            self.push()                        # the for-init scope (C99 6.8.5p5)
            if isinstance(s.init, A.VarDeclStmt):
                self.define_type(s.init.type_def)
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
        elif isinstance(s, A.Switch):
            self.switch_stmt(s)
        elif isinstance(s, A.Case):
            self.case_label(s)
        elif isinstance(s, A.Default):
            self.default_label(s)
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

    def switch_stmt(self, s: A.Switch) -> None:
        t = self.expr(s.cond)
        if not is_err(t):
            if t == VOID:
                self.void_value(s.cond)
            elif not is_integer(t):
                self.report("SEM-SWITCH-NON-INT", self.start(s.cond), found=type_name(t), end=self.end(s.cond))
        self.switch_stack.append(SwitchCtx())
        self.loop_stack.append("switch")
        self.stmt(s.body)
        self.loop_stack.pop()
        self.switch_stack.pop()

    def case_label(self, s: A.Case) -> None:
        t = self.expr(s.value)
        if not self.switch_stack:
            self.report("SEM-CASE-OUTSIDE-SWITCH", self.start(s), found="case", end=Position(s.span.start_line, s.span.start_col + 3))
            return
        if is_err(t):
            return
        v = self.const_int(s.value)
        if v is NONCONST or not is_integer(t):
            self.report("SEM-CASE-NOT-CONSTANT", self.start(s.value), found=unparse(s.value), end=self.end(s.value))
            return
        ctx = self.switch_stack[-1]
        if isinstance(v, int):
            if v in ctx.seen:
                self.report("SEM-DUPLICATE-CASE", self.start(s.value), found=str(v), end=self.end(s.value),
                            prev_line=ctx.seen[v])
            else:
                ctx.seen[v] = s.span.start_line

    def default_label(self, s: A.Default) -> None:
        if not self.switch_stack:
            self.report("SEM-CASE-OUTSIDE-SWITCH", self.start(s), found="default",
                        end=Position(s.span.start_line, s.span.start_col + 6))
            return
        ctx = self.switch_stack[-1]
        if ctx.default_line is not None:
            self.report("SEM-DUPLICATE-CASE", self.start(s), found="default", end=Position(s.span.start_line, s.span.start_col + 6),
                        prev_line=ctx.default_line)
        else:
            ctx.default_line = s.span.start_line

    def loop_control(self, s: object) -> None:
        is_break = isinstance(s, A.Break)
        if "loop" in self.loop_stack or (is_break and "switch" in self.loop_stack):
            return
        word = "break" if is_break else "continue"
        top = self.loop_stack[-1] if self.loop_stack else None
        cause = top if top not in (None, "loop", "switch") else None                              # R7
        self.report("SEM-BREAK-OUTSIDE-LOOP", self.start(s), found=word, caused_by=cause)

    def condition(self, cond: object) -> None:
        t = self.expr(cond)
        self.require_value(t, cond, expected="an arithmetic value", allow_ptr=True)
        if isinstance(cond, A.Assign) and cond.op == "=":
            self.report("WRN-ASSIGN-IN-CONDITION", cond.op_pos, found="=", end=cond.op_pos)

    def return_stmt(self, s: A.Return) -> None:
        fn = self.func
        at = self.start(s)
        name = fn.decl.name
        if s.value is None:
            if fn.ret != VOID:
                self.report("SEM-RETURN-TYPE", at, found="nothing", end=Position(at.line, at.column + 5),
                            expected=[type_name(fn.ret)], name=name)
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
                      at: Position | None = None, op: str = "", allow_ptr: bool = False) -> object:
        """Check that an operand is a usable (arithmetic / integer / scalar) value. Returns the type to continue with."""
        if is_err(t):
            return t
        if t == VOID:
            return ErrorType(self.void_value(node).id)
        ok = (is_arith(t) and (not integer or is_integer(t))) or (allow_ptr and not integer and is_pointer(t))
        if not ok:
            loc = at or self.start(node)
            end = op_end(at, op) if at else self.end(node)
            rec = self.report("SEM-TYPE-MISMATCH", loc, found=type_name(t), expected=[expected], end=end)
            return ErrorType(rec.id)
        return decay(t)

    def void_value(self, node: object) -> ErrorRecord:
        if isinstance(node, A.Call) and isinstance(node.callee, A.Name):
            return self.report("SEM-VOID-VALUE", self.start(node.callee), found=node.callee.name)
        return self.report("SEM-VOID-VALUE", self.start(node), found=unparse(node), end=self.end(node))

    def is_null_const(self, node: object) -> bool:
        if isinstance(node, A.Name):
            sym = self.lookup(node.name)
            return sym is not None and sym.builtin and node.name == "NULL"
        if isinstance(node, A.Cast) and node.type.ptr == 1 and node.type.base == VOID:
            return self.is_null_const(node.operand)
        return isinstance(node, (A.IntLit, A.CharLit, A.Binary, A.Unary)) and self.const_int(node) == 0

    @staticmethod
    def strip_sign(t: object) -> object:
        if isinstance(t, str) and t.startswith(("unsigned ", "signed ")):
            return t.split(" ", 1)[1]
        return t

    def pointers_compatible(self, src: PointerType, dst: PointerType) -> bool:
        a, b = src.base, dst.base
        if a == VOID or b == VOID or a == b:
            return True
        if isinstance(a, str) and isinstance(b, str) and a in INTEGER_TYPES and b in INTEGER_TYPES:
            return self.strip_sign(a) == self.strip_sign(b)                # differing signedness: gcc only warns
        if isinstance(a, PointerType) and isinstance(b, PointerType):
            return self.pointers_compatible(a, b)
        if isinstance(a, ArrayType) and isinstance(b, ArrayType):
            return a.elem == b.elem and (a.size == b.size or a.size is None or b.size is None)
        return False

    def mismatch(self, t: object, target: object, *, at: Position, ctx: str, name: str, index: int) -> None:
        if ctx == "arg":
            self.report("SEM-ARG-TYPE", at, found=type_name(t), expected=[type_name(target)],
                        end=self.name_end(at, name), name=name, index=index)
        elif ctx == "return":
            self.report("SEM-RETURN-TYPE", at, found=type_name(t), expected=[type_name(target)],
                        end=Position(at.line, at.column + 5), name=name)
        else:
            end = self.name_end(at, name) if ctx == "init" else at
            self.report("SEM-TYPE-MISMATCH", at, found=type_name(t), expected=[type_name(target)], end=end)

    def convert(self, t: object, target: object, node: object, *, at: Position, ctx: str, name: str,
                index: int = 0) -> None:
        """Assignment / initialisation / argument / return conversion (spec §3)."""
        if is_err(t) or is_err(target):
            return
        if t == VOID:
            self.void_value(node)
            return
        if is_arith(target):
            if not is_arith(t):
                self.mismatch(t, target, at=at, ctx=ctx, name=name, index=index)
            elif t in FLOATING_TYPES and is_integer(target):
                end = (self.name_end(at, name) if ctx in ("init", "arg") else
                       Position(at.line, at.column + 5) if ctx == "return" else at)
                self.report("WRN-IMPLICIT-NARROWING", at, found=t, expected=[target if isinstance(target, str)
                                                                              else type_name(target)], end=end)
            return
        if isinstance(target, PointerType):
            src = decay(t)
            if isinstance(src, PointerType):
                if not self.pointers_compatible(src, target):
                    self.report("WRN-INCOMPATIBLE-POINTER", at, found=type_name(t), expected=[type_name(target)],
                                end=(self.name_end(at, name) if ctx in ("init", "arg") else
                                     Position(at.line, at.column + 5) if ctx == "return" else at))
                return
            if is_integer(t) and self.is_null_const(node):
                return
            self.mismatch(t, target, at=at, ctx=ctx, name=name, index=index)
            return
        if isinstance(target, StructType) and t == target:
            return
        self.mismatch(t, target, at=at, ctx=ctx, name=name, index=index)

    # ------------------------------------------------------------ constants
    def const_int(self, e: object) -> object:
        """Value of an integer constant expression: an int, UNKNOWN (constant, value not computed) or NONCONST."""
        if isinstance(e, A.IntLit):
            return e.value
        if isinstance(e, A.CharLit):
            return ord(e.value)
        if isinstance(e, A.Name):
            sym = self.lookup(e.name)
            if sym is not None and sym.kind in ("enumconst", "const") and isinstance(sym.type, (str, EnumType)):
                return sym.value if sym.value is not None else UNKNOWN
            return NONCONST
        if isinstance(e, A.SizeOf):
            return UNKNOWN
        if isinstance(e, A.Cast):
            inner = self.const_int(e.operand)
            return inner if is_integer(e.type.base) and e.type.ptr == 0 else (inner if inner is NONCONST else UNKNOWN)
        if isinstance(e, A.Unary) and not e.postfix and e.op in ("-", "+", "~", "!"):
            v = self.const_int(e.operand)
            if not isinstance(v, int):
                return v
            return {"-": -v, "+": v, "~": ~v, "!": int(not v)}[e.op]
        if isinstance(e, A.Binary) and e.op != ",":
            a, b = self.const_int(e.left), self.const_int(e.right)
            if a is NONCONST or b is NONCONST:
                return NONCONST
            if not isinstance(a, int) or not isinstance(b, int):
                return UNKNOWN
            return _fold(e.op, a, b)
        if isinstance(e, A.Ternary):
            c, a, b = self.const_int(e.cond), self.const_int(e.then), self.const_int(e.els)
            if NONCONST in (c, a, b):
                return NONCONST
            if isinstance(c, int) and isinstance(a, int) and isinstance(b, int):
                return a if c else b
            return UNKNOWN
        return NONCONST

    def is_const_init(self, e: object) -> bool:
        """sem.global_init: is ``e`` an initialiser a global (or static) variable may have?"""
        if isinstance(e, A.InitList):
            return all(self.is_const_init(i) for i in e.items)
        if isinstance(e, (A.IntLit, A.FloatLit, A.CharLit, A.StringLit, A.SizeOf)):
            return True
        if isinstance(e, A.Name):
            sym = self.lookup(e.name)
            return sym is not None and (sym.kind in ("enumconst", "const", "func") or
                                        (sym.kind == "global" and isinstance(sym.type, ArrayType)))
        if isinstance(e, A.Unary) and not e.postfix:
            if e.op == "&":
                return self.is_address_const(e.operand)
            return e.op in ("-", "+", "~", "!") and self.is_const_init(e.operand)
        if isinstance(e, A.Binary):
            return e.op != "," and self.is_const_init(e.left) and self.is_const_init(e.right)
        if isinstance(e, A.Ternary):
            return all(self.is_const_init(x) for x in (e.cond, e.then, e.els))
        if isinstance(e, A.Cast):
            return self.is_const_init(e.operand)
        return False

    def is_address_const(self, e: object) -> bool:
        if isinstance(e, A.Name):
            sym = self.lookup(e.name)
            return sym is not None and sym.kind in ("global", "func")
        if isinstance(e, A.Index):
            return self.is_address_const(e.base) and self.is_const_init(e.index)
        if isinstance(e, A.Member) and not e.arrow:
            return self.is_address_const(e.base)
        return False

    @staticmethod
    def first_error(e: object) -> A.ErrorExpr | None:
        if isinstance(e, A.ErrorExpr):
            return e
        for child in _children(e):
            found = Analyzer.first_error(child)
            if found is not None:
                return found
        return None

    # ------------------------------------------------------------ expressions
    def expr(self, e: object, *, write: bool = False) -> object:
        """Analyse an expression and return its type. ``write`` marks a plain '=' target (not a read)."""
        t = self.expr_inner(e, write=write)
        self.etype[id(e)] = t
        return t

    def expr_inner(self, e: object, *, write: bool = False) -> object:
        if isinstance(e, A.IntLit):
            return INT
        if isinstance(e, A.FloatLit):
            return DOUBLE
        if isinstance(e, A.CharLit):
            return CHAR
        if isinstance(e, A.StringLit):
            return ArrayType(CHAR, len(e.value) + 1, False, True)
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
        if isinstance(e, A.Member):
            return self.member(e)
        if isinstance(e, A.Cast):
            return self.cast(e)
        if isinstance(e, A.SizeOf):
            if isinstance(e.operand, A.TypeName):
                self.type_of_name(e.operand)
            else:
                self.expr(e.operand)
            return "unsigned long"
        if isinstance(e, A.Ternary):
            return self.ternary(e)
        if isinstance(e, A.InitList):
            for item in e.items:
                self.expr(item) if not isinstance(item, A.InitList) else self.expr_inner(item)
            return ErrorType("")
        raise TypeError(f"unknown expression node {e!r}")

    def type_of_name(self, tn: A.TypeName) -> object:
        return self.declared_type(tn.base, tn.ptr, False, tn.const, tn.dims, Position(tn.span.start_line, tn.span.start_col))

    def name(self, e: A.Name, *, write: bool = False) -> object:
        self.ensure_builtins(self.start(e))
        sym = self.lookup(e.name)
        if sym is None or sym.kind == "typedef":
            rec = self.report("SEM-UNDECLARED-VAR", self.start(e), found=e.name, caused_by=self.r5(e.name),
                              name=e.name)
            return ErrorType(rec.id)
        if not write:
            sym.read = True
        return sym.type

    def mark_read(self, e: object) -> None:
        if isinstance(e, A.Name):
            sym = self.lookup(e.name)
            if sym is not None:
                sym.read = True

    def index(self, e: A.Index, *, write: bool = False) -> object:
        base_t = self.expr(e.base, write=write)
        result: object
        if is_err(base_t):
            result = base_t
        elif isinstance(base_t, ArrayType):
            result = base_t.elem
        elif isinstance(base_t, PointerType):
            self.mark_read(e.base)
            result = base_t.base
            if result == VOID:
                result = ErrorType(self.report("SEM-VOID-VALUE", self.start(e.base), found=unparse(e.base),
                                               end=self.end(e.base)).id)
        else:
            label = e.base.name if isinstance(e.base, A.Name) else unparse(e.base)
            rec = self.report("SEM-NOT-ARRAY", self.start(e.base), found=label, end=self.end(e.base), name=label)
            result = ErrorType(rec.id)
        idx_t = self.expr(e.index)
        if not is_err(idx_t):
            if idx_t == VOID:
                self.void_value(e.index)
            elif not is_integer(idx_t):
                self.report("SEM-INDEX-NOT-INT", self.start(e.index), found=type_name(idx_t), end=self.end(e.index))
        return result

    def member(self, e: A.Member) -> object:
        bt = self.expr(e.base)
        if is_err(bt):
            return bt
        if bt == VOID:
            return ErrorType(self.void_value(e.base).id)
        st: object = bt
        if e.arrow:
            d = decay(bt)
            if not isinstance(d, PointerType):
                rec = self.report("SEM-ARROW-ON-NON-POINTER", self.start(e.base), found=type_name(bt),
                                  end=self.end(e.base), member=e.name)
                return ErrorType(rec.id)
            st = d.base
        if not isinstance(st, StructType):
            rec = self.report("SEM-MEMBER-ON-NON-STRUCT", self.start(e.base), found=type_name(bt),
                              end=self.end(e.base), member=e.name)
            return ErrorType(rec.id)
        info = self.structs[st.uid]
        if not info.complete:
            rec = self.report("SEM-INCOMPLETE-TYPE", self.start(e.base), found=unparse(e.base), end=self.end(e.base),
                              name=type_name(st), caused_by=self.r5(type_name(st)))
            return ErrorType(rec.id)
        if e.name not in info.members:
            rec = self.report("SEM-NO-SUCH-MEMBER", e.name_pos, found=e.name, name=type_name(st))
            return ErrorType(rec.id)
        return info.members[e.name]

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
        self.ensure_builtins(at)
        sym = self.lookup(name)
        if sym is None or sym.kind == "typedef":
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
        if sym.builtin and name == "printf":
            first = e.args[0] if e.args else None
            ft = self.expr(first) if first is not None else None
            if first is None or (not is_err(ft) and not (isinstance(decay(ft), PointerType)
                                                          and decay(ft).base in ("char", "signed char", "unsigned char"))):
                self.report("SEM-PRINTF-FORMAT", at, found=name)
            elif isinstance(first, A.ErrorExpr):
                self.report("SEM-PRINTF-FORMAT", at, found=name, caused_by=first.error_id)            # R3
            types = [ft] + [self.expr(a) for a in e.args[1:]] if first is not None else []
            self.variadic_extras(e, types, 1, name, at)
            return ftype.ret
        nparams = len(ftype.params)
        if len(e.args) < nparams or (len(e.args) > nparams and not ftype.variadic):
            expected = f"at least {nparams}" if ftype.variadic else str(nparams)
            self.report("SEM-ARG-COUNT", at, found=str(len(e.args)), expected=[expected],
                        end=self.name_end(at, name), name=name)
            for a in e.args:
                self.expr(a)
            return ftype.ret
        types = [self.expr(a) for a in e.args]
        for i, (a, t, p) in enumerate(zip(e.args, types, ftype.params), start=1):
            self.convert(t, p, a, at=at, ctx="arg", name=name, index=i)
        self.variadic_extras(e, types, nparams, name, at)
        return ftype.ret

    def variadic_extras(self, e: A.Call, types: list, fixed: int, name: str, at: Position) -> None:
        for i, (a, t) in enumerate(zip(e.args, types), start=1):
            if i <= fixed:
                continue
            if t == VOID:
                self.void_value(a)
            elif not is_err(t) and not is_scalar(t):
                self.report("SEM-ARG-TYPE", at, found=type_name(t), expected=["a number or pointer"],
                            name=name, index=i)

    def const_target(self, target: object) -> str | None:
        """Text of the const object that assigning to ``target`` would modify, or None."""
        if isinstance(target, A.Name):
            sym = self.lookup(target.name)
            return target.name if sym is not None and sym.const else None
        if isinstance(target, A.Index):
            bt = self.etype.get(id(target.base))
            if isinstance(bt, PointerType):
                return unparse(target) if bt.base_const else None
            if isinstance(bt, ArrayType):
                return unparse(target) if bt.const else self.const_target(target.base)
            return None
        if isinstance(target, A.Unary) and target.op == "*":
            bt = self.etype.get(id(target.operand))
            if isinstance(bt, PointerType):
                return unparse(target) if bt.base_const else None
            if isinstance(bt, ArrayType):
                return unparse(target) if bt.const else None
            return None
        if isinstance(target, A.Member):
            if target.arrow:
                bt = self.etype.get(id(target.base))
                return unparse(target) if isinstance(bt, PointerType) and bt.base_const else None
            return self.const_target(target.base)
        return None

    def check_const(self, target: object) -> None:
        name = self.const_target(target)
        if name is not None:
            self.report("SEM-ASSIGN-TO-CONST", self.start(target), found=name, end=self.end(target), name=name)

    def assign(self, e: A.Assign) -> object:
        plain = e.op == "="
        tt = self.expr(e.target, write=plain)              # '=' writes; compound ops read and write (plan 004)
        vt = self.expr(e.value)
        if is_err(tt):
            return tt
        if not (is_arith(tt) or isinstance(tt, (PointerType, StructType))):   # array name, function name, void...
            rec = self.report("SEM-TYPE-MISMATCH", e.op_pos, found=type_name(tt),
                              expected=["a variable or array element"], end=op_end(e.op_pos, e.op))
            return ErrorType(rec.id)
        self.check_const(e.target)
        if plain:
            self.convert(vt, tt, e.value, at=e.op_pos, ctx="assign", name="")
            return tt
        if not is_arith(tt) and not (isinstance(tt, PointerType) and e.op in ("+=", "-=")):
            rec = self.report("SEM-TYPE-MISMATCH", e.op_pos, found=type_name(tt), expected=["an arithmetic value"],
                              end=op_end(e.op_pos, e.op))
            return ErrorType(rec.id)
        integer = e.op in ("%=", "&=", "|=", "^=", "<<=", ">>=") or isinstance(tt, PointerType)
        vt = self.require_value(vt, e.value, "an integer" if integer else "an arithmetic value", integer=integer,
                                at=e.op_pos, op=e.op)
        if integer and not is_integer(tt) and not isinstance(tt, PointerType):
            self.report("SEM-TYPE-MISMATCH", e.op_pos, found=type_name(tt), expected=["an integer"],
                        end=op_end(e.op_pos, e.op))
            return tt
        if is_err(vt):
            return tt
        if is_arith(tt):
            result = usual_arith(tt, vt)
            if result in FLOATING_TYPES and is_integer(tt):
                self.report("WRN-IMPLICIT-NARROWING", e.op_pos, found=result, expected=[type_name(tt)],
                            end=op_end(e.op_pos, e.op))
        return tt

    def unary(self, e: A.Unary) -> object:
        if e.op in ("++", "--"):
            t = self.expr(e.operand)                       # read and write (plan 004)
            op_at = Position(e.span.end_line, e.span.end_col - 1) if e.postfix else self.start(e)
            r = self.require_value(t, e.operand, "an arithmetic value", at=op_at, op=e.op, allow_ptr=True)
            if not is_err(r):
                self.check_const(e.operand)
            return t if not is_err(r) else r
        if e.op == "&":
            return self.address_of(e)
        if e.op == "*":
            return self.deref(e)
        t = self.expr(e.operand)
        if e.op == "!":
            t = self.require_value(t, e.operand, "an arithmetic value", at=self.start(e), op=e.op, allow_ptr=True)
            return t if is_err(t) else INT
        if e.op == "~":
            t = self.require_value(t, e.operand, "an integer", integer=True, at=self.start(e), op=e.op)
            return t if is_err(t) else promote(t)
        t = self.require_value(t, e.operand, "an arithmetic value", at=self.start(e), op=e.op)
        if is_err(t):
            return t
        return promote(t) if is_integer(t) else t

    def address_of(self, e: A.Unary) -> object:
        t = self.expr(e.operand)
        if is_err(t):
            return t
        if t == VOID:
            return ErrorType(self.void_value(e.operand).id)
        if not self.is_lvalue_expr(e.operand):
            rec = self.report("SEM-ADDR-OF-NON-LVALUE", self.start(e), found=unparse(e.operand),
                              end=self.end(e.operand))
            return ErrorType(rec.id)
        return PointerType(t, self.const_of(e.operand))

    def const_of(self, e: object) -> bool:
        return self.const_target(e) is not None

    def is_lvalue_expr(self, e: object) -> bool:
        if isinstance(e, A.Name):
            sym = self.lookup(e.name)
            return sym is not None and sym.kind in ("var", "param", "global", "void")
        if isinstance(e, (A.Index, A.Member)):
            return True
        return isinstance(e, A.Unary) and e.op == "*" and not e.postfix

    def deref(self, e: A.Unary) -> object:
        t = self.expr(e.operand)
        if is_err(t):
            return t
        if t == VOID:
            return ErrorType(self.void_value(e.operand).id)
        d = decay(t)
        if not isinstance(d, PointerType):
            rec = self.report("SEM-DEREF-NON-POINTER", self.start(e), found=type_name(t) if not isinstance(e.operand, A.Name)
                              else e.operand.name, end=self.end(e.operand), type=type_name(t))
            return ErrorType(rec.id)
        self.mark_read(e.operand)
        if d.base == VOID:
            return VOID
        return d.base

    def binary(self, e: A.Binary) -> object:
        lt = self.expr(e.left)
        rt = self.expr(e.right)
        op = e.op
        if op == ",":
            return rt
        if op in ("&&", "||"):
            lt = self.require_value(lt, e.left, "an arithmetic value", at=e.op_pos, op=op, allow_ptr=True)
            if is_err(lt):
                return lt
            rt = self.require_value(rt, e.right, "an arithmetic value", at=e.op_pos, op=op, allow_ptr=True)
            return rt if is_err(rt) else INT
        if op in ("==", "!=", "<", "<=", ">", ">="):
            return self.comparison(e, lt, rt)
        if op in ("+", "-"):
            return self.additive(e, lt, rt)
        integer = op in ("%", "<<", ">>", "&", "|", "^")
        want = "an integer" if integer else "an arithmetic value"
        lt = self.require_value(lt, e.left, want, integer=integer, at=e.op_pos, op=op)
        if is_err(lt):
            return lt
        rt = self.require_value(rt, e.right, want, integer=integer, at=e.op_pos, op=op)
        if is_err(rt):
            return rt
        if op in ("<<", ">>"):
            return promote(lt)
        return usual_arith(lt, rt)

    def additive(self, e: A.Binary, lt: object, rt: object) -> object:
        op = e.op
        lt = self.require_value(lt, e.left, "an arithmetic value", at=e.op_pos, op=op, allow_ptr=True)
        if is_err(lt):
            return lt
        rt = self.require_value(rt, e.right, "an arithmetic value", at=e.op_pos, op=op, allow_ptr=True)
        if is_err(rt):
            return rt
        lp, rp = isinstance(lt, PointerType), isinstance(rt, PointerType)
        if not lp and not rp:
            return usual_arith(lt, rt)
        bad = None
        if lp and rp:
            if op == "+":
                bad = (rt, e.right)
            elif not self.pointers_compatible(lt, rt):
                bad = (rt, e.right)
            else:
                return "long"
        elif lp:
            if not is_integer(rt):
                bad = (rt, e.right)
            else:
                return lt
        else:                                           # integer op pointer
            if op == "-" or not is_integer(lt):
                bad = (lt, e.left)
            else:
                return rt
        found, node = bad
        rec = self.report("SEM-TYPE-MISMATCH", e.op_pos, found=type_name(found),
                          expected=["an integer" if lp != rp else "a number"], end=op_end(e.op_pos, op))
        return ErrorType(rec.id)

    def comparison(self, e: A.Binary, lt: object, rt: object) -> object:
        op = e.op
        lt = self.require_value(lt, e.left, "an arithmetic value", at=e.op_pos, op=op, allow_ptr=True)
        if is_err(lt):
            return lt
        rt = self.require_value(rt, e.right, "an arithmetic value", at=e.op_pos, op=op, allow_ptr=True)
        if is_err(rt):
            return rt
        lp, rp = isinstance(lt, PointerType), isinstance(rt, PointerType)
        if lp and rp:
            if not self.pointers_compatible(lt, rt) and not self.pointers_compatible(rt, lt):
                self.report("WRN-INCOMPATIBLE-POINTER", e.op_pos, found=type_name(rt), expected=[type_name(lt)],
                            end=op_end(e.op_pos, op))
        elif lp or rp:
            other, node = (rt, e.right) if lp else (lt, e.left)
            if not (is_integer(other) and self.is_null_const(node)):
                rec = self.report("SEM-TYPE-MISMATCH", e.op_pos, found=type_name(other),
                                  expected=["a pointer" if lp else "a number"], end=op_end(e.op_pos, op))
                return ErrorType(rec.id)
        return INT

    def cast(self, e: A.Cast) -> object:
        target = self.type_of_name(e.type)
        t = self.expr(e.operand)
        if is_err(t):
            return target
        if target == VOID:
            return VOID
        if t == VOID:
            self.void_value(e.operand)
            return target
        if not (is_scalar(target) and is_scalar(t)):
            self.report("SEM-TYPE-MISMATCH", self.start(e), found=type_name(t if is_scalar(target) else target),
                        expected=["a number or pointer"], end=self.end(e))
        return target

    def ternary(self, e: A.Ternary) -> object:
        ct = self.expr(e.cond)
        self.require_value(ct, e.cond, "an arithmetic value", allow_ptr=True)
        a, b = self.expr(e.then), self.expr(e.els)
        if is_err(a):
            return a
        if is_err(b):
            return b
        if a == VOID and b == VOID:
            return VOID
        if a == VOID:
            return ErrorType(self.void_value(e.then).id)
        if b == VOID:
            return ErrorType(self.void_value(e.els).id)
        if is_arith(a) and is_arith(b):
            return usual_arith(a, b)
        da, db = decay(a), decay(b)
        if isinstance(da, PointerType) and isinstance(db, PointerType):
            return da
        if isinstance(da, PointerType) and is_integer(b) and self.is_null_const(e.els):
            return da
        if isinstance(db, PointerType) and is_integer(a) and self.is_null_const(e.then):
            return db
        if isinstance(a, StructType) and a == b:
            return a
        rec = self.report("SEM-TYPE-MISMATCH", self.start(e.els), found=type_name(b), expected=[type_name(a)],
                          end=self.end(e.els))
        return ErrorType(rec.id)

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
def _fold(op: str, a: int, b: int) -> object:
    try:
        return {
            "+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
            "/": lambda: int(a / b) if abs(a) < 2 ** 52 else a // b, "%": lambda: a - b * int(a / b),
            "<<": lambda: a << b, ">>": lambda: a >> b, "&": lambda: a & b, "|": lambda: a | b, "^": lambda: a ^ b,
            "==": lambda: int(a == b), "!=": lambda: int(a != b), "<": lambda: int(a < b), "<=": lambda: int(a <= b),
            ">": lambda: int(a > b), ">=": lambda: int(a >= b), "&&": lambda: int(bool(a and b)),
            "||": lambda: int(bool(a or b)),
        }[op]()
    except (ZeroDivisionError, ValueError, OverflowError):
        return UNKNOWN


def _children(e: object) -> list:
    if isinstance(e, A.Unary):
        return [e.operand]
    if isinstance(e, A.Binary):
        return [e.left, e.right]
    if isinstance(e, A.Assign):
        return [e.target, e.value]
    if isinstance(e, A.Call):
        return [e.callee, *e.args]
    if isinstance(e, A.Index):
        return [e.base, e.index]
    if isinstance(e, A.Member):
        return [e.base]
    if isinstance(e, A.Cast):
        return [e.operand]
    if isinstance(e, A.SizeOf):
        return [] if isinstance(e.operand, A.TypeName) else [e.operand]
    if isinstance(e, A.Ternary):
        return [e.cond, e.then, e.els]
    if isinstance(e, A.InitList):
        return list(e.items)
    return []


def eof_position(prog: A.Program) -> Position:
    """The EOF token's position (docs/error-recovery.md §8); contract §4: Program.span ends at it."""
    return Position(prog.span.end_line, prog.span.end_col)


def op_end(at: Position, op: str) -> Position:
    """Inclusive end of an operator token that starts at ``at``."""
    return Position(at.line, at.column + max(len(op), 1) - 1)


def _has_break(s: object) -> bool:
    """Does ``s`` contain a ``break`` that leaves the enclosing switch (not one inside an inner loop or switch)?"""
    if isinstance(s, A.Break):
        return True
    if isinstance(s, A.Block):
        return any(_has_break(x) for x in s.stmts)
    if isinstance(s, A.If):
        return _has_break(s.then) or (s.els is not None and _has_break(s.els))
    return False


def returns(s: object) -> bool:
    """sem.return_paths: does ``s`` return on every path?

    A ``return`` does; a block does if ANY of its statements does (what follows is
    unreachable, sem.unreachable); an ``if`` does if it has an ``else`` and both
    branches do; a ``switch`` does if it has a ``default``, no ``break`` and its last
    statement returns. Loops never count.
    """
    if isinstance(s, A.Return):
        return True
    if isinstance(s, A.Block):
        return any(returns(x) for x in s.stmts)
    if isinstance(s, A.If):
        return s.els is not None and returns(s.then) and returns(s.els)
    if isinstance(s, A.Switch) and isinstance(s.body, A.Block):
        body = s.body.stmts
        return (any(isinstance(x, A.Default) for x in body) and not _has_break(s.body)
                and bool(body) and returns(body[-1]))
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
    if isinstance(e, A.Member):
        return f"{unparse(e.base)}{'->' if e.arrow else '.'}{e.name}"
    if isinstance(e, A.Cast):
        return f"({unparse_type(e.type)}){unparse(e.operand)}"
    if isinstance(e, A.SizeOf):
        return f"sizeof({unparse_type(e.operand)})" if isinstance(e.operand, A.TypeName) else f"sizeof {unparse(e.operand)}"
    if isinstance(e, A.Ternary):
        return f"{unparse(e.cond)} ? {unparse(e.then)} : {unparse(e.els)}"
    if isinstance(e, A.InitList):
        return "{" + ", ".join(unparse(i) for i in e.items) + "}"
    return "?"


def unparse_type(tn: A.TypeName) -> str:
    return tn.base + ("*" * tn.ptr) + "".join("[]" for _ in tn.dims)


def first_token(s: object) -> str:
    """Text of the first token of a statement (``found`` of WRN-UNREACHABLE-CODE)."""
    words = {A.Return: "return", A.Break: "break", A.Continue: "continue", A.If: "if", A.While: "while",
             A.For: "for", A.Block: "{", A.EmptyStmt: ";", A.Switch: "switch", A.DoWhile: "do",
             A.Case: "case", A.Default: "default"}
    for cls, w in words.items():
        if isinstance(s, cls):
            return w
    if isinstance(s, A.VarDeclStmt):
        return s.decls[0].type_name if s.decls else s.base
    if isinstance(s, A.ExprStmt):
        e = s.expr
        while True:
            if isinstance(e, A.Assign):
                e = e.target
            elif isinstance(e, A.Binary):
                e = e.left
            elif isinstance(e, A.Call):
                e = e.callee
            elif isinstance(e, (A.Index, A.Member)):
                e = e.base
            elif isinstance(e, A.Ternary):
                e = e.cond
            elif isinstance(e, A.Unary):
                if not e.postfix:
                    return e.op
                e = e.operand
            else:
                return unparse(e)
    return "?"


def analyze(program: A.Program, sink: ErrorSink, includes: object = None) -> None:
    """Run the semantic phase on ``program`` and report through ``sink``. Never raises on a partial AST.

    ``includes`` is the lexer's list of ``(header, position)`` pairs; for backward compatibility a single
    ``Position`` (or None) means '#include <stdio.h>' at that position (or no include).
    """
    if includes is None:
        incs: list = []
    elif isinstance(includes, Position):
        incs = [("stdio.h", includes)]
    else:
        incs = list(includes)
    Analyzer(sink, incs).program(program)
