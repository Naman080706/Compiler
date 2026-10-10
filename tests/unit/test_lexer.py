"""Unit tests for cea.lexer (plan 005, steps 4-6)."""
import json
from pathlib import Path

import pytest

from cea.diagnostics import ErrorSink
from cea.lexer import lex
from cea.records import Position
from cea.tokens import TokenKind

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "corpus"


def run(source):
    """Lex `source`; return (LexResult, records)."""
    sink = ErrorSink(source)
    result = lex(source, sink)
    return result, sink.records


def toks(source):
    """(kind name, text) of every non-EOF token; asserts there are no records."""
    result, records = run(source)
    assert records == [], [(r.code, r.line, r.column) for r in records]
    return [(t.kind.name, t.text) for t in result.tokens[:-1]]


# ---------------------------------------------------------------- step 4: tokens and literals

@pytest.mark.parametrize("source,expected", [
    ("int x = 5;", [("KEYWORD", "int"), ("IDENT", "x"), ("OP", "="), ("INT_LIT", "5"), ("PUNCT", ";")]),
    ("struct sizeof whilex _a1 A9", [("UNSUPPORTED_KEYWORD", "struct"), ("UNSUPPORTED_KEYWORD", "sizeof"),
                                    ("IDENT", "whilex"), ("IDENT", "_a1"), ("IDENT", "A9")]),
    ("a+++b", [("IDENT", "a"), ("OP", "++"), ("OP", "+"), ("IDENT", "b")]),
    ("i-->0", [("IDENT", "i"), ("OP", "--"), ("OP", ">"), ("INT_LIT", "0")]),
    ("x<<=2", [("IDENT", "x"), ("UNSUPPORTED_OP", "<<"), ("OP", "="), ("INT_LIT", "2")]),
    ("x>>1", [("IDENT", "x"), ("UNSUPPORTED_OP", ">>"), ("INT_LIT", "1")]),
    ("p->q", [("IDENT", "p"), ("UNSUPPORTED_OP", "->"), ("IDENT", "q")]),
    ("s.f", [("IDENT", "s"), ("UNSUPPORTED_OP", "."), ("IDENT", "f")]),
    ("a&&b||!c", [("IDENT", "a"), ("OP", "&&"), ("IDENT", "b"), ("OP", "||"), ("OP", "!"), ("IDENT", "c")]),
    ("a&b|c^~d", [("IDENT", "a"), ("UNSUPPORTED_OP", "&"), ("IDENT", "b"), ("UNSUPPORTED_OP", "|"),
                  ("IDENT", "c"), ("UNSUPPORTED_OP", "^"), ("UNSUPPORTED_OP", "~"), ("IDENT", "d")]),
    ("a?b:c", [("IDENT", "a"), ("UNSUPPORTED_OP", "?"), ("IDENT", "b"), ("UNSUPPORTED_OP", ":"), ("IDENT", "c")]),
    ("a==b!=c<=d>=e<f>g", [("IDENT", "a"), ("OP", "=="), ("IDENT", "b"), ("OP", "!="), ("IDENT", "c"),
                           ("OP", "<="), ("IDENT", "d"), ("OP", ">="), ("IDENT", "e"), ("OP", "<"),
                           ("IDENT", "f"), ("OP", ">"), ("IDENT", "g")]),
    ("+= -= *= /= %=", [("OP", "+="), ("OP", "-="), ("OP", "*="), ("OP", "/="), ("OP", "%=")]),
    ("a*b/c%d-e", [("IDENT", "a"), ("OP", "*"), ("IDENT", "b"), ("OP", "/"), ("IDENT", "c"),
                   ("OP", "%"), ("IDENT", "d"), ("OP", "-"), ("IDENT", "e")]),
    ("(){}[],;", [("PUNCT", c) for c in "(){}[],;"]),
    (".5", [("UNSUPPORTED_OP", "."), ("INT_LIT", "5")]),
])
def test_token_kinds_and_maximal_munch(source, expected):
    assert toks(source) == expected


@pytest.mark.parametrize("source,kind,value", [
    ("42", "INT_LIT", 42),
    ("0", "INT_LIT", 0),
    ("007", "INT_LIT", 7),
    ("3.14", "FLOAT_LIT", 3.14),
    ("10.0", "FLOAT_LIT", 10.0),
    ("'a'", "CHAR_LIT", "a"),
    ("'\"'", "CHAR_LIT", '"'),
    ("' '", "CHAR_LIT", " "),
    ("'\\n'", "CHAR_LIT", "\n"),
    ("'\\t'", "CHAR_LIT", "\t"),
    ("'\\0'", "CHAR_LIT", "\0"),
    ("'\\''", "CHAR_LIT", "'"),
    ("'\\\"'", "CHAR_LIT", '"'),
    ("'\\\\'", "CHAR_LIT", "\\"),
    ('"hi"', "STRING_LIT", "hi"),
    ('""', "STRING_LIT", ""),
    ('"a\\tb\\n"', "STRING_LIT", "a\tb\n"),
    ('"say \\"x\\""', "STRING_LIT", 'say "x"'),
    ('"it\'s"', "STRING_LIT", "it's"),
    ('"\\\\"', "STRING_LIT", "\\"),
    ('"// not a comment"', "STRING_LIT", "// not a comment"),
])
def test_literal_values(source, kind, value):
    result, records = run(source)
    assert records == []
    [tok, eof] = result.tokens
    assert (tok.kind.name, tok.text, tok.value) == (kind, source, value)
    assert eof.kind is TokenKind.EOF


@pytest.mark.parametrize("source,expected", [
    # (text, line, col, end_line, end_col) of every token, EOF last
    ("int  x;\n\tif", [("int", 1, 1, 1, 3), ("x", 1, 6, 1, 6), (";", 1, 7, 1, 7),
                       ("if", 2, 2, 2, 3), ("EOF", 2, 4, 2, 4)]),
    ('x = "ab";', [("x", 1, 1, 1, 1), ("=", 1, 3, 1, 3), ('"ab"', 1, 5, 1, 8), (";", 1, 9, 1, 9),
                   ("EOF", 1, 10, 1, 10)]),
    ("return 0;", [("return", 1, 1, 1, 6), ("0", 1, 8, 1, 8), (";", 1, 9, 1, 9), ("EOF", 1, 10, 1, 10)]),
    ("return 0;\n", [("return", 1, 1, 1, 6), ("0", 1, 8, 1, 8), (";", 1, 9, 1, 9), ("EOF", 1, 10, 1, 10)]),
    ("a\n\n\n", [("a", 1, 1, 1, 1), ("EOF", 1, 2, 1, 2)]),
    ("", [("EOF", 1, 1, 1, 1)]),
    ("  \n\t\n", [("EOF", 1, 1, 1, 1)]),
    ("int a;\r\nint b;\r\n", [("int", 1, 1, 1, 3), ("a", 1, 5, 1, 5), (";", 1, 6, 1, 6),
                              ("int", 2, 1, 2, 3), ("b", 2, 5, 2, 5), (";", 2, 6, 2, 6), ("EOF", 2, 7, 2, 7)]),
    ("a\r\n\r\nb", [("a", 1, 1, 1, 1), ("b", 3, 1, 3, 1), ("EOF", 3, 2, 3, 2)]),
    ("a\rb", [("a", 1, 1, 1, 1), ("b", 2, 1, 2, 1), ("EOF", 2, 2, 2, 2)]),
    ("\t\tx", [("x", 1, 3, 1, 3), ("EOF", 1, 4, 1, 4)]),
])
def test_positions(source, expected):
    result, records = run(source)
    assert records == []
    assert [(t.text, t.line, t.col, t.end_line, t.end_col) for t in result.tokens] == expected


def test_exactly_one_eof_token_last():
    result, _ = run("int main(void) { return 0; }")
    assert [t.kind for t in result.tokens].count(TokenKind.EOF) == 1
    assert result.tokens[-1].kind is TokenKind.EOF and result.tokens[-1].text == "EOF"
    assert all(t.lex_gap is None for t in result.tokens)


def test_no_stdio_include_without_directive():
    assert run("int x;")[0].stdio_include is None
