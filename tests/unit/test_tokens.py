"""Unit tests for cea.tokens: the tables must equal docs/language-spec.md section 1 (plan 005, step 3)."""
import dataclasses
import re
from pathlib import Path

import pytest

from cea.tokens import (
    ESCAPES, KEYWORDS, OPERATORS, PUNCTUATORS, TYPE_KEYWORDS, UNSUPPORTED_KEYWORDS,
    UNSUPPORTED_OPS, Token, TokenKind,
)

SPEC = Path(__file__).resolve().parents[2] / "docs" / "language-spec.md"


def _spec_strings(rule):
    """The double-quoted strings in one rule of the lexical ebnf block of language-spec.md."""
    text = SPEC.read_text(encoding="utf-8")
    start = text.index("```ebnf")
    block = text[start:text.index("```", start + 7)]
    m = re.search(rf"^{rule}\s*=(.*?);\s*$", block, re.M | re.S)
    assert m, f"rule {rule} not found in the lexical grammar"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def test_token_kinds_in_contract_order():
    assert [k.name for k in TokenKind] == [
        "IDENT", "KEYWORD", "UNSUPPORTED_KEYWORD", "INT_LIT", "FLOAT_LIT", "CHAR_LIT",
        "STRING_LIT", "OP", "UNSUPPORTED_OP", "PUNCT", "EOF",
    ]


@pytest.mark.parametrize("table,rule,size", [
    (KEYWORDS, "KEYWORD", 28),
    (UNSUPPORTED_KEYWORDS, "UNSUPPORTED_KEYWORD", 4),
    (OPERATORS, "OPERATOR", 37),
    (UNSUPPORTED_OPS, "UNSUPPORTED_OP", 1),
    (PUNCTUATORS, "PUNCT", 8),
])
def test_tables_match_the_spec(table, rule, size):
    assert table == _spec_strings(rule)
    assert len(table) == size


def test_type_keywords():
    assert TYPE_KEYWORDS == {"int", "float", "double", "char", "void", "long", "short", "unsigned", "signed",
                             "struct", "union", "enum", "typedef", "const", "static", "extern"}
    assert TYPE_KEYWORDS <= KEYWORDS


def test_tables_are_disjoint():
    assert not KEYWORDS & UNSUPPORTED_KEYWORDS
    assert not OPERATORS & UNSUPPORTED_OPS
    assert not (OPERATORS | UNSUPPORTED_OPS) & PUNCTUATORS


def test_escapes():
    assert ESCAPES == {"n": "\n", "t": "\t", "0": "\0", "'": "'", '"': '"', "\\": "\\"}


def test_token_defaults_and_frozen():
    t = Token(TokenKind.IDENT, "x", 1, 1, 1, 1)
    assert (t.lex_gap, t.value) == (None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.text = "y"
