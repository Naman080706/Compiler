"""Three AST-driven tools the Lab UI exposes, all built on the parse tree we own:

* ``format_source`` (feature #1) — pretty-print the AST back to tidy, consistently
  indented C (an "unparser"). Literals are copied verbatim from the source by span, so
  hex, char and string escapes round-trip exactly; only layout changes.
* ``fold_constants`` (feature #5) — evaluate the maximal constant sub-expressions
  (``2 * 60 * 60`` -> ``7200``) and report each with the text it replaced.
* ``ast_diff`` (feature #2) — a *structural* diff of two programs: it diffs the parse
  trees, so pure reformatting / comment / whitespace changes show as no change.

Only our own compiler is used (``engine="cea"``); nothing here runs the program and
nothing prints. The formatter refuses a program that did not fully parse rather than
emit something it cannot faithfully reproduce.
"""
from __future__ import annotations

import difflib

from cea.introspect import tree_text
from cea.pipeline import compile_source

DISPLAY_NAME = "input.c"
INDENT = "    "

# Expression precedence (higher binds tighter); used to add the fewest parentheses.
PRIMARY, POSTFIX, UNARY = 18, 17, 16
_BIN = {
    "*": 15, "/": 15, "%": 15,
    "+": 14, "-": 14,
    "<<": 13, ">>": 13,
    "<": 12, "<=": 12, ">": 12, ">=": 12,
    "==": 11, "!=": 11,
    "&": 10, "^": 9, "|": 8, "&&": 7, "||": 6,
}
TERN, ASSIGN = 4, 3


class _Unsupported(Exception):
    """The AST holds a node (usually an error/recovery node) the formatter will not emit."""


def _slice(lines: list[str], span) -> str:
    """The exact source text of a 1-based inclusive span (single- or multi-line)."""
    sl, sc, el, ec = span.start_line, span.start_col, span.end_line, span.end_col
    if sl == el:
        return lines[sl - 1][sc - 1:ec]
    out = [lines[sl - 1][sc - 1:], *lines[sl:el - 1], lines[el - 1][:ec]]
    return "\n".join(out)


# ---------- feature #1: unparse (format) ----------

def _paren(child: tuple[str, int], min_prec: int) -> str:
    text, prec = child
    return f"({text})" if prec < min_prec else text


def _typename(tn) -> str:
    return tn.base + "*" * getattr(tn, "ptr", 0) + "[]" * len(getattr(tn, "dims", []) or [])


def _expr(node, lines) -> tuple[str, int]:
    """Return (text, precedence) for an expression node."""
    t = type(node).__name__
    if t in ("IntLit", "FloatLit", "CharLit", "StringLit"):
        return _slice(lines, node.span), PRIMARY
    if t == "Name":
        return node.name, PRIMARY
    if t == "Unary":
        inner = _paren(_expr(node.operand, lines), POSTFIX if node.postfix else UNARY)
        return (f"{inner}{node.op}", POSTFIX) if node.postfix else (f"{node.op}{inner}", UNARY)
    if t == "Binary":
        p = _BIN.get(node.op)
        if p is None:
            raise _Unsupported(node.op)
        left = _paren(_expr(node.left, lines), p)
        right = _paren(_expr(node.right, lines), p + 1)  # left-associative
        return f"{left} {node.op} {right}", p
    if t == "Assign":
        tgt = _paren(_expr(node.target, lines), ASSIGN + 1)
        val = _paren(_expr(node.value, lines), ASSIGN)
        return f"{tgt} {node.op} {val}", ASSIGN
    if t == "Ternary":
        c = _paren(_expr(node.cond, lines), TERN + 1)
        return f"{c} ? {_expr(node.then, lines)[0]} : {_paren(_expr(node.els, lines), TERN)}", TERN
    if t == "Call":
        callee = _paren(_expr(node.callee, lines), POSTFIX)
        return f"{callee}({', '.join(_expr(a, lines)[0] for a in node.args)})", POSTFIX
    if t == "Index":
        return f"{_paren(_expr(node.base, lines), POSTFIX)}[{_expr(node.index, lines)[0]}]", POSTFIX
    if t == "Member":
        return f"{_paren(_expr(node.base, lines), POSTFIX)}{'->' if node.arrow else '.'}{node.name}", POSTFIX
    if t == "Cast":
        return f"({_typename(node.type)}){_paren(_expr(node.operand, lines), UNARY)}", UNARY
    if t == "SizeOf":
        inner = _typename(node.operand) if type(node.operand).__name__ == "TypeName" else _expr(node.operand, lines)[0]
        return f"sizeof({inner})", UNARY
    if t == "InitList":
        return "{" + ", ".join(_expr(i, lines)[0] for i in node.items) + "}", PRIMARY
    raise _Unsupported(t)  # ErrorExpr or anything unexpected


def _vardecl(d, lines) -> str:
    s = "*" * d.ptr + d.name
    if d.is_array:
        s += f"[{_expr(d.array_size, lines)[0] if d.array_size is not None else ''}]"
    for dim in d.more_dims:
        s += f"[{_expr(dim, lines)[0] if dim is not None else ''}]"
    if d.init is not None:
        s += " = " + _expr(d.init, lines)[0]
    return s


def _structdef(sd, lines) -> str:
    head = f"{sd.kind} {sd.tag}".rstrip() if sd.tag else sd.kind
    body = [f"{INDENT}{m.type_name} {'*' * m.ptr}{m.name}"
            + "".join(f"[{_expr(x, lines)[0] if x is not None else ''}]" for x in (m.dims or []))
            + ";" for m in sd.members]
    return head + " {\n" + "\n".join(body) + "\n}"


def _vardeclstmt_inline(node, lines) -> str:
    """A declaration without the trailing ';' (for a for-loop init)."""
    base = node.base or (node.decls[0].type_name if node.decls else "")
    return f"{base} " + ", ".join(_vardecl(d, lines) for d in node.decls)


def _stmt(node, lines, depth) -> list[str]:
    pad = INDENT * depth
    t = type(node).__name__
    if t == "VarDeclStmt":
        if node.type_def is not None and not node.decls:
            kind = type(node.type_def).__name__
            if kind == "StructDef":
                return [pad + line for line in (_structdef(node.type_def, lines) + ";").split("\n")]
            raise _Unsupported(kind)
        prefix = "typedef " if node.is_typedef else ""
        return [pad + prefix + _vardeclstmt_inline(node, lines) + ";"]
    if t == "ExprStmt":
        return [pad + _expr(node.expr, lines)[0] + ";"]
    if t == "Return":
        return [pad + ("return;" if node.value is None else f"return {_expr(node.value, lines)[0]};")]
    if t == "Break":
        return [pad + "break;"]
    if t == "Continue":
        return [pad + "continue;"]
    if t == "EmptyStmt":
        return [pad + ";"]
    if t == "Block":
        return [pad + "{", *_block_body(node, lines, depth + 1), pad + "}"]
    if t == "If":
        return _if(node, lines, depth)
    if t == "While":
        return [pad + f"while ({_expr(node.cond, lines)[0]}) {{", *_body(node.body, lines, depth + 1), pad + "}"]
    if t == "DoWhile":
        return [pad + "do {", *_body(node.body, lines, depth + 1), pad + f"}} while ({_expr(node.cond, lines)[0]});"]
    if t == "For":
        init = "" if node.init is None else (
            _vardeclstmt_inline(node.init, lines) if type(node.init).__name__ == "VarDeclStmt"
            else _expr(node.init, lines)[0])
        cond = "" if node.cond is None else _expr(node.cond, lines)[0]
        step = "" if node.step is None else _expr(node.step, lines)[0]
        return [pad + f"for ({init}; {cond}; {step}) {{", *_body(node.body, lines, depth + 1), pad + "}"]
    if t == "Switch":
        return [pad + f"switch ({_expr(node.cond, lines)[0]}) {{", *_body(node.body, lines, depth + 1), pad + "}"]
    if t == "Case":
        return [pad + f"case {_expr(node.value, lines)[0]}:"]
    if t == "Default":
        return [pad + "default:"]
    raise _Unsupported(t)  # ErrorStmt or anything unexpected


def _block_body(block, lines, depth) -> list[str]:
    out: list[str] = []
    for s in block.stmts:
        out += _stmt(s, lines, depth)
    return out


def _body(stmt, lines, depth) -> list[str]:
    """The inner lines of a braced body: a Block's statements, or a lone statement indented."""
    if type(stmt).__name__ == "Block":
        return _block_body(stmt, lines, depth)
    return _stmt(stmt, lines, depth)


def _if(node, lines, depth) -> list[str]:
    pad = INDENT * depth
    out = [pad + f"if ({_expr(node.cond, lines)[0]}) {{", *_body(node.then, lines, depth + 1)]
    els = node.els
    while els is not None and type(els).__name__ == "If":  # chain else-if
        out.append(pad + f"}} else if ({_expr(els.cond, lines)[0]}) {{")
        out += _body(els.then, lines, depth + 1)
        els = els.els
    if els is None:
        out.append(pad + "}")
    else:
        out += [pad + "} else {", *_body(els, lines, depth + 1), pad + "}"]
    return out


def _function(fn, lines) -> list[str]:
    ret = ("const " if fn.ret_const else "") + fn.ret_type + "*" * fn.ret_ptr
    params = "void" if not fn.params else ", ".join(
        (("const " if p.const else "") + p.type_name + " " + "*" * p.ptr + p.name).rstrip() for p in fn.params)
    sig = f"{ret} {fn.name}({params})"
    if fn.body is None:
        return [sig + ";"]
    return [sig + " {", *_block_body(fn.body, lines, 1), "}"]


def unparse(program, source: str) -> str:
    """Pretty-print ``program`` (parsed from ``source``) back to formatted C."""
    lines = source.split("\n")
    # The AST has no nodes for preprocessor directives, so copy them verbatim (they sit at the top).
    # shortcut: directives are gathered to the top in source order; a #define between functions moves up.
    directives = [ln.rstrip() for ln in lines if ln.lstrip().startswith("#")]
    out: list[str] = []
    for decl in program.decls:
        t = type(decl).__name__
        if t == "FunctionDecl":
            if out:
                out.append("")        # blank line between top-level items
            out += _function(decl, lines)
        elif t == "VarDeclStmt":
            out += _stmt(decl, lines, 0)
        else:
            raise _Unsupported(t)     # ErrorStmt at top level
    head = ("\n".join(directives) + "\n\n") if directives else ""
    return head + "\n".join(out) + "\n"


def format_source(source: str) -> dict:
    """{ok, formatted, reason}. Refuses a program that did not fully parse."""
    result = compile_source(source, DISPLAY_NAME, engine="cea")
    try:
        return {"ok": True, "formatted": unparse(result.program, source), "reason": ""}
    except _Unsupported:
        return {"ok": False, "formatted": "",
                "reason": "This program did not fully parse — fix the errors first, then format."}


# ---------- feature #5: constant folding ----------

_OPS_INT_ONLY = {"<<", ">>", "&", "|", "^", "%"}


def _apply(op: str, a, b):
    both_int = isinstance(a, int) and isinstance(b, int)
    if op in _OPS_INT_ONLY and not both_int:
        return None
    if op == "+": return a + b
    if op == "-": return a - b
    if op == "*": return a * b
    if op == "/":
        if b == 0: return None
        if both_int:
            q = abs(a) // abs(b)
            return q if (a < 0) == (b < 0) else -q
        return a / b
    if op == "%":
        if b == 0: return None
        r = abs(a) % abs(b)
        return r if a >= 0 else -r
    if op == "<<": return a << b
    if op == ">>": return a >> b
    if op == "&": return a & b
    if op == "|": return a | b
    if op == "^": return a ^ b
    if op in ("<", "<=", ">", ">=", "==", "!="):
        return int({"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}[op])
    if op == "&&": return int(bool(a) and bool(b))
    if op == "||": return int(bool(a) or bool(b))
    return None


def _const(node):
    """The numeric value of a constant expression, or None if it is not a compile-time constant."""
    t = type(node).__name__
    if t == "IntLit": return node.value
    if t == "FloatLit": return node.value
    if t == "CharLit": return ord(node.value) if len(node.value) == 1 else None
    if t == "Unary" and not node.postfix:
        v = _const(node.operand)
        if v is None: return None
        if node.op == "-": return -v
        if node.op == "+": return +v
        if node.op == "!": return int(not v)
        if node.op == "~": return ~v if isinstance(v, int) else None
        return None
    if t == "Binary":
        a, b = _const(node.left), _const(node.right)
        return None if a is None or b is None else _apply(node.op, a, b)
    if t == "Ternary":
        c = _const(node.cond)
        return None if c is None else _const(node.then if c else node.els)
    return None


def _is_fold_op(node) -> bool:
    """A node worth reporting: it has at least one operator (not a bare literal)."""
    t = type(node).__name__
    return t == "Binary" or t == "Ternary" or (t == "Unary" and not node.postfix and node.op in "-+!~")


def _collect_folds(node, lines, out, seen):
    """Record the *maximal* constant sub-expressions (do not descend into a folded one)."""
    from cea.introspect import _child_nodes
    if _is_fold_op(node):
        v = _const(node)
        if v is not None:
            try:                       # the unparsed form is balanced; a raw span can clip outer parens
                text = _expr(node, lines)[0]
            except _Unsupported:
                text = _slice(lines, node.span)
            out.append({"line": node.span.start_line, "text": text, "value": _fmt(v)})
            return
    for child in _child_nodes(node):
        _collect_folds(child, lines, out, seen)


def _fmt(v) -> str:
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, float) and v.is_integer():
        return repr(v)
    return str(v)


def fold_constants(source: str) -> dict:
    """{folds: [{line, text, value}]} — the constant expressions the compiler can pre-compute."""
    result = compile_source(source, DISPLAY_NAME, engine="cea")
    lines = source.split("\n")
    folds: list[dict] = []
    _collect_folds(result.program, lines, folds, set())
    return {"folds": folds}


# ---------- feature #2: structural (AST) diff ----------

_TAG = {"  ": "same", "+ ": "add", "- ": "remove"}


def ast_diff(source_a: str, source_b: str) -> dict:
    """{rows: [{tag, text}]} diffing the two parse trees, so formatting-only edits show nothing."""
    a = tree_text(compile_source(source_a, DISPLAY_NAME, engine="cea").program)
    b = tree_text(compile_source(source_b, DISPLAY_NAME, engine="cea").program)
    rows = []
    for line in difflib.ndiff(a, b):
        tag = _TAG.get(line[:2])
        if tag is not None:
            rows.append({"tag": tag, "text": line[2:]})
    changed = any(r["tag"] != "same" for r in rows)
    return {"rows": rows, "changed": changed}
