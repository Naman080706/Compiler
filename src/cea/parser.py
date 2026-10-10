"""Recursive-descent parser for the course C subset, with error recovery.

Grammar: docs/language-spec.md section 2 (each method below is named after the
EBNF rule it parses; that name is the runtime ``rule_ref`` of a syntax record).
Recovery: docs/error-recovery.md sections 4 and 5 (as amended by plan 004):
phrase repairs (4.2 missing ';', 4.3 missing ')' before '{', 4.7 missing '}'),
panic mode with sync sets (4.4), the uncertain region (4.5), the progress
guarantee (4.6), error nodes and broken declarations (5), and the caused_by
rules for syntax records: R2, then R1, then R9 (7).
Code selection: docs/error-catalog.md, "Choosing among syntax codes", rules 0-5.

The only public entry point is ``parse()``. ``ParseError``, ``BlockRepair`` and
``Parser`` are internal. Nothing here prints.
"""
from __future__ import annotations

import functools
import sys
from dataclasses import dataclass
from typing import Callable, NoReturn, TypeVar

from cea import ast as A
from cea.diagnostics import ErrorSink
from cea.lexer import LexResult
from cea.records import Position
from cea.tokens import TYPE_KEYWORDS, Token, TokenKind

# Each nesting level of an expression costs about 30 Python frames (11 rule methods
# plus their decorator wrappers), so parse() raises the recursion limit to this
# value for its own duration (restored afterwards).
RECURSION_LIMIT = 20_000

# Tests set this to True: the loop guard (error-recovery 4.6 point 3) then raises
# ProgressError instead of silently skipping a token.
STRICT_PROGRESS = False

K = TokenKind
SYMBOLIC = (K.KEYWORD, K.OP, K.PUNCT)
EXPR = "expression"      # expected-set class: the start of an expression (catalog rule 4)
TYPE = "type"            # expected-set class: a type_spec (catalog rule 4)
IDENT = "identifier"     # expected-set class: an IDENT (falls to catalog rule 5)
ASSIGN_OPS = ("=", "+=", "-=", "*=", "/=", "%=")
OPENER_OF = {")": "(", "]": "[", "}": "{"}
STMT_KEYWORDS = ("if", "while", "for", "return", "break", "continue")
SYNC_STMT_STOP = frozenset({"}", "{", *STMT_KEYWORDS, *TYPE_KEYWORDS})   # plus EOF (checked by kind)
# Codes whose catalog rule_ref is "<production>": the parser passes the current grammar rule.
PRODUCTION_CODES = frozenset({
    "SYN-MISSING-SEMICOLON", "SYN-UNBALANCED-BRACKET", "SYN-EXPECTED-TOKEN",
    "SYN-EXPECTED-EXPRESSION", "SYN-EXPECTED-TYPE", "SYN-UNEXPECTED-EOF", "SYN-UNSUPPORTED-FEATURE",
})
# Noun phrases for the {context} placeholder of SYN-MISSING-SEMICOLON and SYN-UNEXPECTED-EOF.
RULE_PHRASES = {
    "program": "the program", "top_decl": "the declaration", "function_def": "the function declaration",
    "params": "the parameter list", "param_list": "the parameter list", "param": "the parameter",
    "global_decl": "the declaration", "type_spec": "the type", "declarator": "the declarator",
    "array_suffix": "the array size", "block": "the block", "statement": "the statement",
    "var_decl": "the declaration", "var_core": "the declaration", "if_stmt": "the if statement",
    "while_stmt": "the while loop", "for_stmt": "the for loop header", "for_init": "the for loop header",
    "return_stmt": "the return statement", "break_stmt": "the break statement",
    "continue_stmt": "the continue statement", "expr_stmt": "the expression statement",
}
EXPRESSION_RULES = ("expression", "assignment", "logic_or", "logic_and", "equality", "comparison",
                    "term", "factor", "unary", "postfix", "primary", "arg_list")


class ParseError(Exception):
    """Raised after a syntax record is created (error-recovery 4.4). Internal."""

    def __init__(self, error_id: str, code: str) -> None:
        super().__init__(error_id)
        self.error_id = error_id
        self.code = code
        self.in_for_header = False   # set by for_stmt: use for-header panic


class BlockRepair(Exception):
    """The 4.7 missing-'}' repair. Not a ParseError, so statement() does not catch it."""

    def __init__(self, error_id: str) -> None:
        super().__init__(error_id)
        self.error_id = error_id
        self.node: A.Stmt | None = None   # the innermost closed construct, handed outwards


class ProgressError(AssertionError):
    """Raised by the loop guard when STRICT_PROGRESS is True."""


@dataclass
class _TopCtx:
    """What top_decl() has consumed so far (for its catch point)."""
    func_name: Token | None = None
    func_name_index: int = -1
    func_node: A.FunctionDecl | None = None


F = TypeVar("F", bound=Callable)


def rule(name: str) -> Callable[[F], F]:
    """Decorator: push the grammar rule name while the method runs (runtime rule_ref)."""
    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(self: "Parser", *args, **kwargs):
            self.rules.append(name)
            try:
                return fn(self, *args, **kwargs)
            finally:
                self.rules.pop()
        return wrapper  # type: ignore[return-value]
    return deco


def is_type_kw(tok: Token) -> bool:
    return tok.kind is K.KEYWORD and tok.text in TYPE_KEYWORDS


def parse(lex_result: LexResult, sink: ErrorSink) -> A.Program:
    """Parse the token stream; always returns a complete Program (never raises on bad input)."""
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, RECURSION_LIMIT))
    try:
        return Parser(lex_result.tokens, sink).program()
    finally:
        sys.setrecursionlimit(old)


class Parser:
    # ======================================================= core (step 2)
    def __init__(self, tokens: list[Token], sink: ErrorSink) -> None:
        self.toks = tokens
        self.pos = 0
        self.sink = sink
        self.rules: list[str] = []
        self.brackets: list[Token] = []          # openers consumed by successful matches (4.1)
        self.recovering: str | None = None       # uncertain-region owner (4.5)
        self.block_orphans: list[str | None] = []  # orphan_of of each Block being parsed (R9)
        self.unsupported_ids: set[str] = set()   # error ids of ErrorStmts with kind_hint 'unsupported'
        self.stop_index = -1                     # token index where the last panic stopped (orphan test)
        self.decl_log: list[tuple[int, str, str]] = []   # (IDENT index, name, type) of consumed declarators
        self.partial_decl: A.VarDeclStmt | None = None   # var_decl/global_decl being parsed
        self.name_index: dict[int, int] = {}     # id(VarDecl) -> its IDENT token index
        self.top_ctx = _TopCtx()
        self.paren: dict[int, A.Expr] = {}       # parenthesised expressions (not lvalues); keeps them alive

    @property
    def cur(self) -> Token:
        return self.toks[self.pos]

    def peek(self, k: int) -> Token:
        return self.toks[min(self.pos + k, len(self.toks) - 1)]

    @property
    def prev(self) -> Token:
        return self.toks[self.pos - 1]

    @staticmethod
    def is_(tok: Token, text: str) -> bool:
        return tok.kind in SYMBOLIC and tok.text == text

    def at(self, text: str) -> bool:
        return self.is_(self.cur, text)

    def at_any(self, texts: tuple[str, ...]) -> bool:
        return self.cur.kind in SYMBOLIC and self.cur.text in texts

    def consume(self) -> Token:
        """Advance one token without any bookkeeping (used for skipping and for keywords)."""
        tok = self.toks[self.pos]
        if tok.kind is not K.EOF:
            self.pos += 1
        return tok

    def match(self, text: str) -> Token:
        """Consume the current token, which the caller has checked is `text` (a successful match)."""
        tok = self.consume()
        if text in ("(", "[", "{"):
            self.brackets.append(tok)
        elif text in OPENER_OF and self.brackets and self.brackets[-1].text == OPENER_OF[text]:
            self.brackets.pop()
        if text in (";", "}"):
            self.recovering = None           # 4.5 (iii)
        return tok

    def expect(self, text: str) -> Token:
        if self.at(text):
            return self.match(text)
        self.fail([text])

    def expect_ident(self) -> Token:
        if self.cur.kind is K.IDENT:
            return self.consume()
        self.fail([IDENT])

    def span(self, i: int, j: int) -> A.Span:
        a, b = self.toks[i], self.toks[max(i, j)]
        return A.Span(a.line, a.col, b.end_line, b.end_col)

    @staticmethod
    def join(a: A.Span, b: A.Span) -> A.Span:
        return A.Span(a.start_line, a.start_col, b.end_line, b.end_col)

    def span_from(self, start: int) -> A.Span:
        """Span from token `start` to the last consumed token."""
        return self.span(start, self.pos - 1)

    def select_code(self, tok: Token, expected: list[str]) -> str:
        """Catalog "Choosing among syntax codes", rules 0-5, in order."""
        if tok.kind in (K.UNSUPPORTED_KEYWORD, K.UNSUPPORTED_OP) or (
                self.is_(tok, "*") and self.pos > 0 and is_type_kw(self.prev)):
            return "SYN-UNSUPPORTED-FEATURE"                                   # rule 0
        if tok.kind is K.EOF:
            return "SYN-UNEXPECTED-EOF"                                        # rule 1
        if expected == [";"]:
            return "SYN-MISSING-SEMICOLON"                                     # rule 2
        if (expected and all(e in OPENER_OF for e in expected)) or self.stray_closer(tok):
            return "SYN-UNBALANCED-BRACKET"                                    # rule 3
        if EXPR in expected:
            return "SYN-EXPECTED-EXPRESSION"                                   # rule 4
        if TYPE in expected:
            return "SYN-EXPECTED-TYPE"                                         # rule 4
        return "SYN-EXPECTED-TOKEN"                                            # rule 5

    def stray_closer(self, tok: Token) -> bool:
        return (tok.kind is K.PUNCT and tok.text in OPENER_OF
                and all(b.text != OPENER_OF[tok.text] for b in self.brackets))

    def caused_by(self, tok: Token) -> str | None:
        """R2, then R1, then R9 (error-recovery 7, amended by plan 004)."""
        if self.recovering is not None:
            return self.recovering                                             # R2
        if tok.lex_gap is not None:
            return tok.lex_gap                                                 # R1
        if self.block_orphans and self.block_orphans[-1] in self.unsupported_ids:
            return self.block_orphans[-1]                                      # R9
        return None

    def message_args(self, code: str, tok: Token, expected: list[str]) -> dict[str, object]:
        if code in ("SYN-MISSING-SEMICOLON", "SYN-UNEXPECTED-EOF"):
            r = self.rules[-1] if self.rules else "program"
            return {"context": "the expression" if r in EXPRESSION_RULES else RULE_PHRASES.get(r, "the " + r.replace("_", " "))}
        if code == "SYN-UNBALANCED-BRACKET":
            want = OPENER_OF.get(expected[0]) if expected and expected[0] in OPENER_OF else None
            if want is None:                                  # rule 3 via a stray closer
                return {"opener": OPENER_OF.get(tok.text, "?"), "open_line": "?"}
            for b in reversed(self.brackets):
                if b.text == want:
                    return {"opener": b.text, "open_line": b.line}
            return {"opener": want, "open_line": "?"}
        if code == "SYN-UNSUPPORTED-FEATURE":
            if tok.text == "*":
                return {"feature": "A pointer ('*' after a type)"}
            if tok.kind is K.UNSUPPORTED_OP:
                return {"feature": f"The operator '{tok.text}'"}
            return {"feature": f"'{tok.text}'"}
        return {}

    def report(self, code: str, tok: Token, expected: list[str], *,
               at: tuple[int, int] | None = None) -> str:
        """Create one syntax record through the sink; returns its id."""
        if at is not None or tok.kind is K.EOF:
            line, col = at if at is not None else (tok.line, tok.col)
            span_end = Position(line, col)                      # zero-width (8)
        else:
            line, col = tok.line, tok.col
            span_end = Position(tok.end_line, tok.end_col)
        rule_ref = (self.rules[-1] if self.rules else "program") if code in PRODUCTION_CODES else None
        rec = self.sink.report(code, line, col, found=tok.text, expected=expected, span_end=span_end,
                               caused_by=self.caused_by(tok), rule_ref=rule_ref,
                               **self.message_args(code, tok, expected))
        if code == "SYN-UNEXPECTED-EOF" and self.recovering is None:
            self.recovering = rec.id                              # 4.5: an EOF error opens the region
        return rec.id

    def fail(self, expected: list[str]) -> NoReturn:
        tok = self.cur
        code = self.select_code(tok, expected)
        raise ParseError(self.report(code, tok, expected), code)

    # =================================================== recovery (steps 4-9)
    def expect_semi(self) -> Token | None:
        """expect(';') with the 4.2 missing-';' repair."""
        tok = self.cur
        if self.is_(tok, ";"):
            return self.match(";")
        after = (self.prev.end_line, self.prev.end_col + 1)
        if tok.kind is not K.EOF and tok.line > self.prev.end_line:
            self.report("SYN-MISSING-SEMICOLON", tok, [";"], at=after)        # 4.2: repair, no panic
            return None
        code = self.select_code(tok, [";"])
        rid = self.report(code, tok, [";"], at=after if code == "SYN-MISSING-SEMICOLON" else None)
        raise ParseError(rid, code)

    def expect_header_close(self) -> None:
        """expect(')') closing an if/while/for header, with the 4.3 missing-')'-before-'{' repair."""
        if self.at(")"):
            self.match(")")
            return
        if self.at("{"):
            code = self.select_code(self.cur, [")"])                          # rule 3
            self.report(code, self.cur, [")"])
            if self.brackets and self.brackets[-1].text == "(":
                self.brackets.pop()                                           # as if ')' matched
            return
        self.fail([")"])

    def check_missing_brace(self) -> None:
        """4.7: `type IDENT (` at the start of a statement proves a missing '}'."""
        t0, t1, t2 = self.cur, self.peek(1), self.peek(2)
        if is_type_kw(t0) and t1.kind is K.IDENT and self.is_(t2, "("):
            code = self.select_code(t0, ["}"])                                # rule 3
            raise BlockRepair(self.report(code, t0, ["}"]))

    def open_region(self, error_id: str) -> None:
        if self.recovering is None:
            self.recovering = error_id

    def panic_stmt(self) -> str | None:
        """Statement-level panic (4.4). Returns stopped_before (None if a ';' was consumed)."""
        while True:
            tok = self.cur
            if tok.kind is K.EOF or (tok.kind in SYMBOLIC and tok.text in SYNC_STMT_STOP):
                self.stop_index = self.pos
                return tok.text
            self.consume()
            if self.is_(tok, ";"):
                self.recovering = None                                        # 4.5 (i)
                return None

    def panic_for_header(self, base: int) -> str:
        """For-header panic (4.4). `base` = bracket depth before the header's '('."""
        d = sum(1 for b in self.brackets[base:] if b.text == "(")
        while True:
            tok = self.cur
            if tok.kind is K.EOF or (tok.kind in SYMBOLIC and tok.text in SYNC_STMT_STOP):
                self.stop_index = self.pos
                return tok.text
            self.consume()
            if self.is_(tok, "("):
                d += 1
            elif self.is_(tok, ")"):
                d -= 1
                if d == 0:
                    self.stop_index = self.pos
                    return self.cur.text

    def first_on_line(self, i: int) -> bool:
        return i == 0 or self.toks[i - 1].line < self.toks[i].line

    def panic_top(self) -> str:
        """Top-level panic (4.4). Returns the text of the token it stopped before."""
        depth = 0
        while True:
            tok = self.cur
            if tok.kind is K.EOF:
                self.stop_index = self.pos
                return tok.text
            if is_type_kw(tok) and depth == 0 and self.first_on_line(self.pos):
                self.recovering = None                                        # 4.5 (ii)
                self.stop_index = self.pos
                return tok.text
            self.consume()
            if self.is_(tok, "{"):
                depth += 1
            elif self.is_(tok, "}"):
                depth = max(0, depth - 1)

    @staticmethod
    def kind_hint(tok: Token) -> str:
        if tok.kind is K.UNSUPPORTED_KEYWORD:
            return "unsupported"
        if tok.kind is K.KEYWORD:
            if tok.text in TYPE_KEYWORDS:
                return "decl"
            if tok.text in STMT_KEYWORDS:
                return tok.text
        return "expr"

    def idents(self, i: int, j: int) -> set[str]:
        return {t.text for t in self.toks[i:j] if t.kind is K.IDENT}

    def error_stmt(self, e: ParseError, start: int, kind: str, stopped: str | None,
                   names: list[tuple[str, str]]) -> A.ErrorStmt:
        if kind == "unsupported":
            self.unsupported_ids.add(e.error_id)
        return A.ErrorStmt(span=self.span_from(start), error_id=e.error_id, kind_hint=kind,
                           declared_names=names, idents_in_span=self.idents(start, self.pos),
                           stopped_before=stopped)

    def recover_top(self, e: ParseError, start: int, first: Token, stopped: str):
        ctx = self.top_ctx
        if ctx.func_node is not None:                       # error after the header: broken function
            ctx.func_node.error_id = e.error_id
            ctx.func_node.idents_in_span = self.idents(ctx.func_name_index, self.pos)
            ctx.func_node.span = self.span_from(start)
            return ctx.func_node
        if ctx.func_name is not None:                       # error inside the header (5)
            names = [(ctx.func_name.text, "function")]
            names += [n for n in self.declared_names(start, self.pos, e.code)
                      if n[1] == "<unsupported>" and n[0] != ctx.func_name.text]
            return self.error_stmt(e, start, "top", stopped, names)
        if self.partial_decl is not None and self.partial_decl.decls:
            return self.broken_decl(self.partial_decl, e, start)
        kind = "unsupported" if first.kind is K.UNSUPPORTED_KEYWORD else "top"
        return self.error_stmt(e, start, kind, stopped, self.declared_names(start, self.pos, e.code))

    def declared_names(self, start: int, end: int, code: str) -> list[tuple[str, str]]:
        """ErrorStmt.declared_names: consumed `type_spec IDENT` pairs, plus (plan 004) the
        declarator-like names of an unsupported-feature error, in source order, no duplicates."""
        found = [(i, n, t) for (i, n, t) in self.decl_log if start <= i < end]
        if code == "SYN-UNSUPPORTED-FEATURE":
            for i in range(max(start, 1), end):
                tok, before, after = self.toks[i], self.toks[i - 1], self.toks[i + 1]
                if (tok.kind is K.IDENT
                        and (is_type_kw(before) or self.is_(before, "*") or before.kind is K.IDENT)
                        and after.kind in SYMBOLIC and after.text in ("=", ";", ",", "[")):
                    found.append((i, tok.text, "<unsupported>"))
        out: list[tuple[str, str]] = []
        for _, name, typ in sorted(found):
            if name not in [n for n, _ in out]:
                out.append((name, typ))
        return out

    def broken_decl(self, stmt: A.VarDeclStmt, e: ParseError, start: int) -> A.VarDeclStmt:
        """Section 5: keep the declaration; the last declarator gets error_id and idents_in_span."""
        last = stmt.decls[-1]
        name_i = self.name_index[id(last)]
        last.error_id = e.error_id
        last.idents_in_span = self.idents(name_i, self.pos)
        last.span = self.span_from(name_i)
        stmt.span = self.span_from(start)
        return stmt

    def guard(self, before: int) -> None:
        return None

    def is_lvalue(self, e: A.Expr) -> bool:
        return True

    def invalid_target(self, op: Token) -> NoReturn:
        raise NotImplementedError("plan 006 step 9")

    # ==================================================== grammar (step 3)
    @rule("program")
    def program(self) -> A.Program:
        decls: list = []
        while self.cur.kind is not K.EOF:
            before = self.pos
            decls.append(self.top_decl())
            self.guard(before)
        eof = self.toks[-1]                    # contract: 1:1 .. the EOF position
        return A.Program(decls, A.Span(1, 1, eof.line, eof.col))

    @rule("top_decl")
    def top_decl(self) -> A.FunctionDecl | A.VarDeclStmt | A.ErrorStmt:
        start, depth, first = self.pos, len(self.brackets), self.cur
        saved_ctx, saved_partial = self.top_ctx, self.partial_decl
        self.top_ctx, self.partial_decl = _TopCtx(), None
        try:
            type_tok = self.type_spec()
            if self.cur.kind is K.IDENT and self.is_(self.peek(1), "("):
                return self.function_def(type_tok, start)
            return self.global_decl(type_tok, start)
        except ParseError as e:                                            # catch point (c)
            del self.brackets[depth:]
            self.open_region(e.error_id)
            stopped = self.panic_top()
            return self.recover_top(e, start, first, stopped)
        finally:
            self.top_ctx, self.partial_decl = saved_ctx, saved_partial

    @rule("function_def")
    def function_def(self, type_tok: Token, start: int) -> A.FunctionDecl:
        name = self.consume()                               # IDENT (checked by top_decl)
        self.top_ctx.func_name, self.top_ctx.func_name_index = name, self.pos - 1
        self.match("(")
        params = self.params()
        self.expect(")")
        node = A.FunctionDecl(type_tok.text, name.text, Position(name.line, name.col), params, None,
                              self.span_from(start))
        self.top_ctx.func_node = node
        if self.at("{"):
            try:
                node.body = self.block()
            except BlockRepair as r:                        # 4.7: body closed by the repair
                node.body = r.node if isinstance(r.node, A.Block) else None
        else:
            self.expect_semi()                              # site S1
        node.span = self.span_from(start)
        return node

    @rule("params")
    def params(self) -> list[A.Param]:
        if self.at(")"):
            return []
        if self.at("void") and self.is_(self.peek(1), ")"):
            self.consume()
            return []
        return self.param_list()

    @rule("param_list")
    def param_list(self) -> list[A.Param]:
        out = [self.param()]
        while True:
            if self.at(","):
                self.consume()
                out.append(self.param())
            elif self.at(")"):
                return out
            else:
                self.fail([",", ")"])

    @rule("param")
    def param(self) -> A.Param:
        t = self.type_spec()
        name = self.expect_ident()
        return A.Param(t.text, name.text, Position(name.line, name.col),
                       A.Span(t.line, t.col, name.end_line, name.end_col))

    @rule("global_decl")
    def global_decl(self, type_tok: Token, start: int) -> A.VarDeclStmt:
        stmt = A.VarDeclStmt([], self.span_from(start))
        self.partial_decl = stmt
        self.declarator(type_tok.text, stmt, is_global=True)
        while self.at(","):
            self.consume()
            self.declarator(type_tok.text, stmt, is_global=True)
        self.expect_semi()                                  # site S2
        stmt.span = self.span_from(start)
        return stmt

    @rule("type_spec")
    def type_spec(self) -> Token:
        if is_type_kw(self.cur):
            return self.consume()
        self.fail([TYPE])

    @rule("declarator")
    def declarator(self, type_name: str, stmt: A.VarDeclStmt, is_global: bool) -> A.VarDecl:
        name = self.expect_ident()
        name_i = self.pos - 1
        node = A.VarDecl(type_name, name.text, Position(name.line, name.col), None, None, is_global,
                         self.span(name_i, name_i))
        stmt.decls.append(node)
        self.decl_log.append((name_i, name.text, type_name))
        self.name_index[id(node)] = name_i
        if self.at("["):
            self.array_suffix(node)
        if self.at("="):
            self.consume()
            node.init = self.guarded_expression(node, "init")       # CP-INIT
        node.span = self.span_from(name_i)
        return node

    @rule("array_suffix")
    def array_suffix(self, node: A.VarDecl) -> None:
        self.match("[")
        node.array_size = self.guarded_expression(node, "array_size")   # CP-SIZE
        self.expect("]")

    def guarded_expression(self, node: A.VarDecl, field: str) -> A.Expr:
        """CP-INIT / CP-SIZE (4.4 b): the failed expression becomes an ErrorExpr on the
        declaration; the ParseError is re-raised so the enclosing statement()/top_decl()
        runs the panic and returns the (broken) declaration."""
        start = self.pos
        try:
            return self.expression()
        except ParseError as e:
            setattr(node, field, A.ErrorExpr(self.span(start, self.pos - 1), e.error_id))
            raise

    @rule("block")
    def block(self) -> A.Block:
        start, depth = self.pos, len(self.brackets)
        orphan = self.recovering if self.stop_index == self.pos else None    # section 5 orphan_of
        self.match("{")
        node = A.Block([], self.span(start, start), orphan_of=orphan)
        self.block_orphans.append(orphan)
        try:
            while not (self.at("}") or self.cur.kind is K.EOF):
                before = self.pos
                node.stmts.append(self.statement())
                self.guard(before)
            if self.at("}"):
                self.match("}")
            else:
                self.report("SYN-UNEXPECTED-EOF", self.cur, ["}"])         # 4.4 EOF: no raise
            node.span = self.span_from(start)
            return node
        except BlockRepair as r:                                           # 4.7 propagation
            if r.node is not None:
                node.stmts.append(r.node)
            node.span = self.span_from(start)
            node.closed_by_repair = r.error_id
            r.node = node
            raise
        finally:
            self.block_orphans.pop()
            del self.brackets[depth:]

    @rule("statement")
    def statement(self) -> A.Stmt:
        start, depth, first = self.pos, len(self.brackets), self.cur
        saved_partial = self.partial_decl
        self.partial_decl = None
        try:
            self.check_missing_brace()                                     # 4.7 first
            return self.statement_body()
        except ParseError as e:                                            # catch point (a)
            kind = self.kind_hint(first)
            self.open_region(e.error_id)
            if e.in_for_header:
                stopped = self.panic_for_header(depth)
            else:
                stopped = self.panic_stmt()
            del self.brackets[depth:]
            if kind == "decl" and self.partial_decl is not None and self.partial_decl.decls:
                return self.broken_decl(self.partial_decl, e, start)
            return self.error_stmt(e, start, kind, stopped, self.declared_names(start, self.pos, e.code))
        finally:
            self.partial_decl = saved_partial

    def statement_body(self) -> A.Stmt:
        t = self.cur
        if t.kind is K.UNSUPPORTED_KEYWORD:
            self.fail([])                                                  # rule 0
        if is_type_kw(t):
            return self.var_decl()
        if t.kind is K.KEYWORD and t.text in STMT_KEYWORDS:
            return getattr(self, t.text + "_stmt")()
        if self.at("{"):
            return self.block()
        if self.at(";"):
            return self.empty_stmt()
        return self.expr_stmt()

    @rule("var_decl")
    def var_decl(self) -> A.VarDeclStmt:
        start = self.pos
        stmt = self.var_core(register=True)
        self.expect_semi()                                                 # site S3
        stmt.span = self.span_from(start)
        return stmt

    @rule("var_core")
    def var_core(self, register: bool) -> A.VarDeclStmt:
        start = self.pos
        type_tok = self.type_spec()
        stmt = A.VarDeclStmt([], self.span_from(start))
        if register:
            self.partial_decl = stmt
        self.declarator(type_tok.text, stmt, is_global=False)
        while self.at(","):
            self.consume()
            self.declarator(type_tok.text, stmt, is_global=False)
        stmt.span = self.span_from(start)
        return stmt

    @rule("if_stmt")
    def if_stmt(self) -> A.If:
        start = self.pos
        self.consume()                                                     # 'if'
        self.expect("(")
        cond = self.expression()
        self.expect_header_close()
        try:
            then = self.statement()
        except BlockRepair as r:
            if r.node is not None:
                r.node = A.If(cond, r.node, None, self.span_from(start))
            raise
        els = None
        if self.at("else"):
            self.consume()
            try:
                els = self.statement()
            except BlockRepair as r:
                r.node = A.If(cond, then, r.node, self.span_from(start))
                raise
        return A.If(cond, then, els, self.span_from(start))

    @rule("while_stmt")
    def while_stmt(self) -> A.While:
        start = self.pos
        self.consume()                                                     # 'while'
        self.expect("(")
        cond = self.expression()
        self.expect_header_close()
        try:
            body = self.statement()
        except BlockRepair as r:
            if r.node is not None:
                r.node = A.While(cond, r.node, self.span_from(start))
            raise
        return A.While(cond, body, self.span_from(start))

    @rule("for_stmt")
    def for_stmt(self) -> A.For:
        start = self.pos
        self.consume()                                                     # 'for'
        self.expect("(")
        try:
            init = None if self.at(";") else self.for_init()
            self.expect_semi()                                             # site S4
            cond = None if self.at(";") else self.expression()
            self.expect_semi()                                             # site S5
            step = None if self.at(")") else self.expression()
            self.expect_header_close()
        except ParseError as e:
            e.in_for_header = True
            raise
        try:
            body = self.statement()
        except BlockRepair as r:
            if r.node is not None:
                r.node = A.For(init, cond, step, r.node, self.span_from(start))
            raise
        return A.For(init, cond, step, body, self.span_from(start))

    @rule("for_init")
    def for_init(self) -> A.VarDeclStmt | A.Expr:
        if is_type_kw(self.cur):
            return self.var_core(register=False)
        return self.expression()

    @rule("return_stmt")
    def return_stmt(self) -> A.Return:
        start = self.pos
        self.consume()                                                     # 'return'
        value = None if self.at(";") else self.expression()
        self.expect_semi()                                                 # site S6
        return A.Return(value, self.span_from(start))

    @rule("break_stmt")
    def break_stmt(self) -> A.Break:
        start = self.pos
        self.consume()
        self.expect_semi()                                                 # site S7
        return A.Break(self.span_from(start))

    @rule("continue_stmt")
    def continue_stmt(self) -> A.Continue:
        start = self.pos
        self.consume()
        self.expect_semi()                                                 # site S8
        return A.Continue(self.span_from(start))

    @rule("expr_stmt")
    def expr_stmt(self) -> A.ExprStmt:
        start = self.pos
        e = self.expression()
        self.expect_semi()                                                 # site S9
        return A.ExprStmt(e, self.span_from(start))

    @rule("empty_stmt")
    def empty_stmt(self) -> A.EmptyStmt:
        start = self.pos
        self.match(";")                                                    # site S10
        return A.EmptyStmt(self.span_from(start))

    @rule("expression")
    def expression(self) -> A.Expr:
        return self.assignment()

    @rule("assignment")
    def assignment(self) -> A.Expr:
        left = self.logic_or()
        if self.at_any(ASSIGN_OPS):
            op = self.cur
            if not self.is_lvalue(left):
                self.invalid_target(op)
            self.consume()
            value = self.assignment()
            return A.Assign(op.text, left, value, Position(op.line, op.col), self.join(left.span, value.span))
        return left

    def binary(self, ops: tuple[str, ...], sub: Callable[[], A.Expr]) -> A.Expr:
        left = sub()
        while self.at_any(ops):
            op = self.consume()
            right = sub()
            left = A.Binary(op.text, left, right, Position(op.line, op.col), self.join(left.span, right.span))
        return left

    @rule("logic_or")
    def logic_or(self) -> A.Expr:
        return self.binary(("||",), self.logic_and)

    @rule("logic_and")
    def logic_and(self) -> A.Expr:
        return self.binary(("&&",), self.equality)

    @rule("equality")
    def equality(self) -> A.Expr:
        return self.binary(("==", "!="), self.comparison)

    @rule("comparison")
    def comparison(self) -> A.Expr:
        return self.binary(("<", "<=", ">", ">="), self.term)

    @rule("term")
    def term(self) -> A.Expr:
        return self.binary(("+", "-"), self.factor)

    @rule("factor")
    def factor(self) -> A.Expr:
        return self.binary(("*", "/", "%"), self.unary)

    @rule("unary")
    def unary(self) -> A.Expr:
        if self.at_any(("!", "-", "+", "++", "--")):
            op = self.consume()
            operand = self.unary()
            if op.text in ("++", "--") and not self.is_lvalue(operand):
                self.invalid_target(op)
            return A.Unary(op.text, operand, False,
                           A.Span(op.line, op.col, operand.span.end_line, operand.span.end_col))
        return self.postfix()

    @rule("postfix")
    def postfix(self) -> A.Expr:
        e = self.primary()
        while True:
            if self.at("("):
                self.match("(")
                args = [] if self.at(")") else self.arg_list()             # 4.1 lookahead commitment
                close = self.expect(")")
                e = A.Call(e, args, A.Span(e.span.start_line, e.span.start_col, close.end_line, close.end_col))
            elif self.at("["):
                self.match("[")
                idx = self.expression()
                close = self.expect("]")
                e = A.Index(e, idx, A.Span(e.span.start_line, e.span.start_col, close.end_line, close.end_col))
            else:
                break
        if self.at_any(("++", "--")):
            op = self.cur
            if not self.is_lvalue(e):
                self.invalid_target(op)
            self.consume()
            e = A.Unary(op.text, e, True, A.Span(e.span.start_line, e.span.start_col, op.end_line, op.end_col))
        return e

    @rule("arg_list")
    def arg_list(self) -> list[A.Expr]:
        out = [self.assignment()]
        while True:
            if self.at(","):
                self.consume()
                out.append(self.assignment())
            elif self.at(")"):
                return out
            else:
                self.fail([",", ")"])

    @rule("primary")
    def primary(self) -> A.Expr:
        t = self.cur
        lit = {K.INT_LIT: A.IntLit, K.FLOAT_LIT: A.FloatLit, K.CHAR_LIT: A.CharLit, K.STRING_LIT: A.StringLit}
        if t.kind in lit:
            self.consume()
            return lit[t.kind](t.value, A.Span(t.line, t.col, t.end_line, t.end_col))
        if t.kind is K.IDENT:
            self.consume()
            return A.Name(t.text, A.Span(t.line, t.col, t.end_line, t.end_col))
        if self.at("("):
            self.match("(")
            e = self.expression()
            self.expect(")")
            self.paren[id(e)] = e
            return e
        self.fail([EXPR])
