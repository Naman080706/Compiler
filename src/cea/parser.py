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
