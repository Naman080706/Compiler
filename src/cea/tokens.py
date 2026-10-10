"""Token kinds, the Token dataclass and the lexical tables of docs/language-spec.md section 1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    IDENT = auto()
    KEYWORD = auto()
    UNSUPPORTED_KEYWORD = auto()
    INT_LIT = auto()
    FLOAT_LIT = auto()
    CHAR_LIT = auto()
    STRING_LIT = auto()
    OP = auto()
    UNSUPPORTED_OP = auto()
    PUNCT = auto()
    EOF = auto()


TYPE_KEYWORDS = frozenset({"int", "float", "double", "char", "void"})
KEYWORDS = TYPE_KEYWORDS | frozenset({"if", "else", "while", "for", "return", "break", "continue"})
UNSUPPORTED_KEYWORDS = frozenset({
    "struct", "union", "enum", "typedef", "switch", "case", "default", "do", "goto",
    "sizeof", "long", "short", "unsigned", "signed", "const", "static", "extern",
    "auto", "register", "volatile",
})
OPERATORS = frozenset({
    "+", "-", "*", "/", "%", "=", "+=", "-=", "*=", "/=", "%=", "++", "--",
    "==", "!=", "<", "<=", ">", ">=", "&&", "||", "!",
})
UNSUPPORTED_OPS = frozenset({"&", "|", "^", "~", "<<", ">>", "->", ".", "?", ":"})
PUNCTUATORS = frozenset({";", ",", "(", ")", "{", "}", "[", "]"})
# escape = "\" , ( "n" | "t" | "0" | "'" | '"' | "\" ) ; key = the character after the backslash
ESCAPES = {"n": "\n", "t": "\t", "0": "\0", "'": "'", '"': '"', "\\": "\\"}


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str               # exact source text ("EOF" for EOF)
    line: int               # start, 1-based
    col: int
    end_line: int           # inclusive end; for EOF: the EOF position itself
    end_col: int
    lex_gap: str | None = None   # docs/error-recovery.md section 3
    value: object = None    # INT_LIT int, FLOAT_LIT float, CHAR_LIT str (1 char), STRING_LIT str (decoded)
