"""Pipeline view (the "Pipeline" UI tab): the token stream, the parse tree and the declared
symbols for one source. All derived from an ordinary ``compile_source`` result (tokens + AST),
so no new compiler logic — just a readable serialisation of what the three phases already built.
Nothing here prints.
"""
from __future__ import annotations

import dataclasses

from cea.pipeline import compile_source
from cea.records import Position
from cea.tokens import TokenKind

DISPLAY_NAME = "input.c"
_SCALAR = (dataclasses.is_dataclass,)  # see _is_node
_SKIP_FIELDS = {"span", "name_pos", "error_id", "idents_in_span", "name_in_span"}
_LABEL_ATTRS = ("name", "ret_type", "type_name", "base", "op", "value", "kind", "text")


def _is_node(v: object) -> bool:
    """A child AST node to recurse into — a dataclass, but not a plain position/range."""
    return dataclasses.is_dataclass(v) and type(v).__name__ not in ("Span", "Position")


def _label(node: object) -> str:
    bits = []
    for attr in _LABEL_ATTRS:
        val = getattr(node, attr, None)
        if val not in (None, "", [], {}) and not _is_node(val):  # show scalars only; nodes are their own lines
            bits.append(f"{attr}={val!r}")
        if len(bits) >= 3:
            break
    name = type(node).__name__
    return f"{name}({', '.join(bits)})" if bits else name


def _child_nodes(node: object):
    """The child AST nodes of ``node``, in source order (the single definition of tree shape:
    tree_text, tree_json and _symbols all walk this, so the text and diagram views never diverge)."""
    for f in dataclasses.fields(node):
        if f.name in _SKIP_FIELDS:
            continue
        value = getattr(node, f.name)
        if _is_node(value):
            yield value
        elif isinstance(value, (list, tuple)):
            for item in value:
                if _is_node(item):
                    yield item


def tree_text(node: object, depth: int = 0) -> list[str]:
    """Indented lines of the AST rooted at ``node`` (skips spans and recovery bookkeeping)."""
    lines = ["  " * depth + _label(node)]
    for child in _child_nodes(node):
        lines += tree_text(child, depth + 1)
    return lines


def tree_json(node: object) -> dict:
    """The same AST as nested ``{label, children}`` for the diagram view. Pre-order matches
    ``tree_text`` line-for-line, so the animation can reveal both views by the same count."""
    return {"label": _label(node), "children": [tree_json(c) for c in _child_nodes(node)]}


def _symbols(node: object, out: list[dict]) -> None:
    """Every declared name anywhere in the tree: functions, parameters, variables (globals and locals)."""
    cls = type(node).__name__
    if cls in ("FunctionDecl", "VarDecl", "Param") and getattr(node, "name", ""):
        pos: Position = node.name_pos
        kind = {"FunctionDecl": "function", "Param": "parameter"}.get(
            cls, "global" if getattr(node, "is_global", False) else "local")
        type_name = getattr(node, "ret_type", None) or getattr(node, "type_name", "")
        out.append({"name": node.name, "type": type_name, "kind": kind, "line": pos.line})
    for child in _child_nodes(node):
        _symbols(child, out)


def analyze(source: str) -> dict:
    """The three views the Pipeline tab shows: tokens, the parse tree (text) and the symbol table."""
    result = compile_source(source, DISPLAY_NAME, engine="cea")
    tokens = [{"kind": t.kind.name, "text": t.text, "line": t.line, "col": t.col}
              for t in result.tokens if t.kind is not TokenKind.EOF]
    symbols: list[dict] = []
    _symbols(result.program, symbols)
    return {"tokens": tokens, "tree": "\n".join(tree_text(result.program)),
            "treeNodes": tree_json(result.program), "symbols": symbols}
