"""The lexical phase: source text -> tokens, with recovery (docs/error-recovery.md section 3).

Rule: record the error, skip the bad input, continue; never pass an error token
to the parser. A skipped lexeme sets `lex_gap` on the next token so the parser
can link a cascade to it (rule R1). Newlines are CRLF, LF or a lone CR; a CR is
never a column. A tab counts as one column.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from cea.diagnostics import ErrorSink
from cea.records import Position
from cea.tokens import (
    ESCAPES, KEYWORDS, OPERATORS, PUNCTUATORS, UNSUPPORTED_KEYWORDS, Token, TokenKind,
    UNSUPPORTED_OPS,
)

_WHITESPACE = frozenset(" \t\f\v\r\n")
_NEWLINES = frozenset("\r\n")
_LETTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")
_DIGITS = frozenset("0123456789")
_IDENT_CHARS = _LETTERS | _DIGITS
_NUMBER_RUN = _IDENT_CHARS | {"."}          # the maximal run skipped for LEX-MALFORMED-NUMBER
# Maximal munch: longest symbols first; ties broken alphabetically for determinism.
_SYMBOLS = sorted(OPERATORS | UNSUPPORTED_OPS | PUNCTUATORS, key=lambda s: (-len(s), s))
# After the header name only blanks and comments may follow (comments are whitespace,
# language-spec section 1). A /* comment must be closed on the same line.
_STDIO_INCLUDE = re.compile(r"#[ \t]*include[ \t]*<stdio\.h>(?:[ \t]|/\*.*?\*/)*(?://.*)?")


@dataclass
class LexResult:
    tokens: list[Token]                 # always ends with exactly one EOF token
    stdio_include: Position | None      # the '#' of the first accepted '#include <stdio.h>', else None


def lex(source: str, sink: ErrorSink) -> LexResult:
    """Tokenise the whole of `source`, reporting lexical errors to `sink`. Never raises on bad input."""
    return _Lexer(source, sink).run()


def _positions(source: str) -> list[tuple[int, int]]:
    """(line, column) of every index of `source`, plus one entry for the end of the text.

    The CR and LF of a CRLF pair share one position; the character after any
    newline is at column 1 of the next line.
    """
    pos: list[tuple[int, int]] = []
    line, col, i, n = 1, 1, 0, len(source)
    while i < n:
        ch = source[i]
        pos.append((line, col))
        if ch == "\r" and i + 1 < n and source[i + 1] == "\n":
            pos.append((line, col))
            i += 2
            line, col = line + 1, 1
            continue
        if ch in _NEWLINES:
            line, col = line + 1, 1
        else:
            col += 1
        i += 1
    pos.append((line, col))
    return pos


class _Lexer:
    def __init__(self, source: str, sink: ErrorSink):
        self.src = source
        self.n = len(source)
        self.sink = sink
        self.pos = _positions(source)
        self.i = 0
        self.tokens: list[Token] = []
        self.pending_gap: str | None = None
        self.stdio_include: Position | None = None

    # ---- driver
    def run(self) -> LexResult:
        src = self.src
        while self.i < self.n:
            ch = src[self.i]
            if ch in _WHITESPACE:
                self.i += 1
            elif ch in _LETTERS:
                self._ident()
            elif ch in _DIGITS:
                self._number()
            elif ch == '"':
                self._string()
            elif ch == "'":
                self._char()
            else:
                self._symbol()
        self._emit_eof()
        return LexResult(self.tokens, self.stdio_include)

    # ---- helpers
    def _eol(self, i: int) -> int:
        """Index of the first newline character at or after i, or len(source)."""
        while i < self.n and self.src[i] not in _NEWLINES:
            i += 1
        return i

    def _emit(self, kind: TokenKind, start: int, end: int, value: object = None) -> None:
        """Emit src[start:end] (end exclusive) as a token; it takes and clears the pending lex_gap."""
        line, col = self.pos[start]
        end_line, end_col = self.pos[end - 1]
        self.tokens.append(Token(kind, self.src[start:end], line, col, end_line, end_col,
                                 self.pending_gap, value))
        self.pending_gap = None

    def _error(self, code: str, at: int, last: int, found: str, sets_gap: bool = True) -> None:
        """Report `code` at index `at`; `last` is the index of the last skipped character (span_end)."""
        line, col = self.pos[at]
        end_line, end_col = self.pos[last]
        record = self.sink.report(code, line, col, found=found, span_end=Position(end_line, end_col))
        if sets_gap:
            self.pending_gap = record.id

    def _emit_eof(self) -> None:
        if self.tokens:
            last = self.tokens[-1]
            line, col = last.end_line, last.end_col + 1
        else:
            line, col = 1, 1
        self.tokens.append(Token(TokenKind.EOF, "EOF", line, col, line, col, self.pending_gap))
        self.pending_gap = None

    # ---- tokens
    def _ident(self) -> None:
        start = j = self.i
        while j < self.n and self.src[j] in _IDENT_CHARS:
            j += 1
        text = self.src[start:j]
        if text in KEYWORDS:
            kind = TokenKind.KEYWORD
        elif text in UNSUPPORTED_KEYWORDS:
            kind = TokenKind.UNSUPPORTED_KEYWORD
        else:
            kind = TokenKind.IDENT
        self._emit(kind, start, j)
        self.i = j

    def _number(self) -> None:
        src, n = self.src, self.n
        start = j = self.i
        while j < n and src[j] in _DIGITS:
            j += 1
        kind = TokenKind.INT_LIT
        if j + 1 < n and src[j] == "." and src[j + 1] in _DIGITS:
            j += 2
            while j < n and src[j] in _DIGITS:
                j += 1
            kind = TokenKind.FLOAT_LIT
        if j < n and src[j] in _NUMBER_RUN:
            # A letter, '_' or a second '.' directly after the number: 12abc, 1.2.3, 12.
            while j < n and src[j] in _NUMBER_RUN:
                j += 1
            self._error("LEX-MALFORMED-NUMBER", start, j - 1, found=src[start:j])
        else:
            text = src[start:j]
            self._emit(kind, start, j, int(text) if kind is TokenKind.INT_LIT else float(text))
        self.i = j

    def _string(self) -> None:
        src, n = self.src, self.n
        start = self.i
        j = start + 1
        chars: list[str] = []
        while True:
            if j >= n or src[j] in _NEWLINES:
                # Skipped: from '"' up to (not including) the end of the line.
                self._error("LEX-UNTERMINATED-STRING", start, j - 1, found=src[start:j])
                self.i = j
                return
            c = src[j]
            if c == '"':
                self._emit(TokenKind.STRING_LIT, start, j + 1, "".join(chars))
                self.i = j + 1
                return
            if c == "\\" and j + 1 < n and src[j + 1] not in _NEWLINES:
                e = src[j + 1]
                if e in ESCAPES:
                    chars.append(ESCAPES[e])
                else:
                    # Only the two-character escape is dropped; the literal is still emitted.
                    self._error("LEX-INVALID-ESCAPE", j, j + 1, found=src[j:j + 2], sets_gap=False)
                j += 2
                continue
            chars.append(c)
            j += 1

    def _char(self) -> None:
        src = self.src
        start = self.i
        eol = self._eol(start)
        k = start + 1
        while k < eol and src[k] != "'":                     # a backslash hides the next character
            k += 2 if src[k] == "\\" and k + 1 < eol else 1
        if k >= eol:                                          # unclosed on its line
            self._error("LEX-BAD-CHAR-LITERAL", start, eol - 1, found=src[start:eol])
            self.i = eol
            return
        body = src[start + 1:k]
        if len(body) == 1 and body != "\\":
            self._emit(TokenKind.CHAR_LIT, start, k + 1, body)
        elif len(body) == 2 and body[0] == "\\":
            if body[1] in ESCAPES:
                self._emit(TokenKind.CHAR_LIT, start, k + 1, ESCAPES[body[1]])
            else:                                             # whole literal skipped, no token
                self._error("LEX-INVALID-ESCAPE", start + 1, k, found=body)
        else:                                                 # '' or more than one character
            self._error("LEX-BAD-CHAR-LITERAL", start, k, found=src[start:k + 1])
        self.i = k + 1

    def _symbol(self) -> None:
        start = self.i
        for sym in _SYMBOLS:
            if self.src.startswith(sym, start):
                if sym in PUNCTUATORS:
                    kind = TokenKind.PUNCT
                elif sym in OPERATORS:
                    kind = TokenKind.OP
                else:
                    kind = TokenKind.UNSUPPORTED_OP
                self._emit(kind, start, start + len(sym))
                self.i = start + len(sym)
                return
        self._error("LEX-INVALID-CHAR", start, start, found=self.src[start])
        self.i = start + 1
