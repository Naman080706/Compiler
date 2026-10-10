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


# ---------------------------------------------------------------- step 5: comments and directives

@pytest.mark.parametrize("source,expected", [
    # (text, line, col) of every non-EOF token
    ("a // c\nb", [("a", 1, 1), ("b", 2, 1)]),
    ("a // c", [("a", 1, 1)]),
    ("a /* x\ny */ b", [("a", 1, 1), ("b", 2, 6)]),
    ("a/**/b", [("a", 1, 1), ("b", 1, 6)]),
    ("/*/ */x", [("x", 1, 7)]),
    ("/* a /* b */ c */", [("c", 1, 14), ("*", 1, 16), ("/", 1, 17)]),
    ("a / b", [("a", 1, 1), ("/", 1, 3), ("b", 1, 5)]),
    ("a /= b", [("a", 1, 1), ("/=", 1, 3), ("b", 1, 6)]),
    ("x = 1; // done\r\ny", [("x", 1, 1), ("=", 1, 3), ("1", 1, 5), (";", 1, 6), ("y", 2, 1)]),
])
def test_comments_are_skipped(source, expected):
    result, records = run(source)
    assert records == []
    assert [(t.text, t.line, t.col) for t in result.tokens[:-1]] == expected


@pytest.mark.parametrize("source,stdio", [
    ("#include <stdio.h>\nint x;", Position(1, 1)),
    ("#include<stdio.h>", Position(1, 1)),
    ("#  include   <stdio.h>  \n", Position(1, 1)),
    ("# include <stdio.h>", Position(1, 1)),
    ("   #include <stdio.h>\n", Position(1, 4)),
    ("\t#include <stdio.h>", Position(1, 2)),
    ("#include <stdio.h>\r\nint x;\r\n", Position(1, 1)),
    ("int x;\n#include <stdio.h>\n#include <stdio.h>\n", Position(2, 1)),
    # comments are whitespace: a trailing // comment or a /* */ closed on the line is allowed
    ("#include <stdio.h> // io", Position(1, 1)),
    ("#include <stdio.h>// io\nint x;", Position(1, 1)),
    ("#include <stdio.h> /* io */", Position(1, 1)),
    ("#include <stdio.h>/* a */ /* b */  // c\r\nint x;", Position(1, 1)),
])
def test_accepted_stdio_include(source, stdio):
    result, records = run(source)
    assert records == []
    assert result.stdio_include == stdio
    assert all(t.text != "#" and t.text != "include" for t in result.tokens)


def test_include_alone_gives_only_eof():
    result, records = run("#include <stdio.h>\n")
    assert records == []
    assert [(t.kind, t.line, t.col) for t in result.tokens] == [(TokenKind.EOF, 1, 1)]


@pytest.mark.parametrize("source,found,span_end", [
    ("#include <math.h>\n", "#include <math.h>", Position(1, 17)),
    ("#define N 10\n", "#define N 10", Position(1, 12)),
    ('#include "stdio.h"', '#include "stdio.h"', Position(1, 18)),
    ("#include < stdio.h >", "#include < stdio.h >", Position(1, 20)),
    ("#include <stdio.h> x", "#include <stdio.h> x", Position(1, 20)),
    ("#include <stdio.h> /* io */ x", "#include <stdio.h> /* io */ x", Position(1, 29)),
    ("#include <stdio.h> /* never closed here", "#include <stdio.h> /* never closed here",
     Position(1, 39)),
    ("#\n", "#", Position(1, 1)),
    ("#pragma once   \r\n", "#pragma once", Position(1, 12)),
])
def test_unsupported_directive(source, found, span_end):
    result, records = run(source)
    [rec] = records
    assert (rec.code, rec.line, rec.column, rec.found, rec.span_end) == \
        ("LEX-UNSUPPORTED-DIRECTIVE", 1, 1, found, span_end)
    assert rec.message == f"Only '#include <stdio.h>' is supported; '{found}' is not"
    assert result.stdio_include is None


def test_unclosed_block_comment_after_include_stays_inside_the_directive():
    # The directive owns the whole line, so the /* opens no comment: line 2 is lexed normally.
    result, records = run("#include <stdio.h> /* open\nint x; */")
    assert [(r.code, r.line, r.column) for r in records] == [("LEX-UNSUPPORTED-DIRECTIVE", 1, 1)]
    assert [t.text for t in result.tokens] == ["int", "x", ";", "*", "/", "EOF"]


def test_unsupported_directive_does_not_set_lex_gap():
    result, records = run("#define N 10\nint x;")
    assert [r.code for r in records] == ["LEX-UNSUPPORTED-DIRECTIVE"]
    assert [(t.text, t.lex_gap) for t in result.tokens] == \
        [("int", None), ("x", None), (";", None), ("EOF", None)]


def test_hash_after_code_is_an_invalid_char():
    result, records = run("int x; # 2\n")
    [rec] = records
    assert (rec.code, rec.line, rec.column, rec.found) == ("LEX-INVALID-CHAR", 1, 8, "#")
    assert [(t.text, t.lex_gap) for t in result.tokens] == \
        [("int", None), ("x", None), (";", None), ("2", "E-0001"), ("EOF", None)]


# ---------------------------------------------------------------- step 6: error recovery and lex_gap

@pytest.mark.parametrize("source,code,line,col,found,span_end,gap_token", [
    # gap_token = (text, line, col) of the one token that must carry lex_gap = "E-0001"
    ("x = 5 @ 2;", "LEX-INVALID-CHAR", 1, 7, "@", (1, 7), ("2", 1, 9)),
    ("$a", "LEX-INVALID-CHAR", 1, 1, "$", (1, 1), ("a", 1, 2)),
    ("a `b", "LEX-INVALID-CHAR", 1, 3, "`", (1, 3), ("b", 1, 4)),
    ("a \\ b", "LEX-INVALID-CHAR", 1, 3, "\\", (1, 3), ("b", 1, 5)),
    ("caf\u00e9 = 1;", "LEX-INVALID-CHAR", 1, 4, "\u00e9", (1, 4), ("=", 1, 6)),
    ('printf("hi);\nx', "LEX-UNTERMINATED-STRING", 1, 8, '"hi);', (1, 12), ("x", 2, 1)),
    ('printf("hi);\r\nx', "LEX-UNTERMINATED-STRING", 1, 8, '"hi);', (1, 12), ("x", 2, 1)),
    ('"abc', "LEX-UNTERMINATED-STRING", 1, 1, '"abc', (1, 4), ("EOF", 1, 1)),
    ('x "', "LEX-UNTERMINATED-STRING", 1, 3, '"', (1, 3), ("EOF", 1, 2)),
    ('"abc\\\ny', "LEX-UNTERMINATED-STRING", 1, 1, '"abc\\', (1, 5), ("y", 2, 1)),
    ("c = 'ab';", "LEX-BAD-CHAR-LITERAL", 1, 5, "'ab'", (1, 8), (";", 1, 9)),
    ("c = '';", "LEX-BAD-CHAR-LITERAL", 1, 5, "''", (1, 6), (";", 1, 7)),
    ("c = '\\n\\n';", "LEX-BAD-CHAR-LITERAL", 1, 5, "'\\n\\n'", (1, 10), (";", 1, 11)),
    ("c = 'a;\nx", "LEX-BAD-CHAR-LITERAL", 1, 5, "'a;", (1, 7), ("x", 2, 1)),
    ("c = '\\';\nx", "LEX-BAD-CHAR-LITERAL", 1, 5, "'\\';", (1, 8), ("x", 2, 1)),
    ("c = '", "LEX-BAD-CHAR-LITERAL", 1, 5, "'", (1, 5), ("EOF", 1, 4)),
    ("c = '\\q';", "LEX-INVALID-ESCAPE", 1, 6, "\\q", (1, 8), (";", 1, 9)),
    ("x /* never closed\n\n", "LEX-UNTERMINATED-COMMENT", 1, 3, "/*", (1, 17), ("EOF", 1, 2)),
    ("x\n/* a\r\nb\r\n", "LEX-UNTERMINATED-COMMENT", 2, 1, "/*", (3, 1), ("EOF", 1, 2)),
    ("/*", "LEX-UNTERMINATED-COMMENT", 1, 1, "/*", (1, 2), ("EOF", 1, 1)),
    ("n = 12abc;", "LEX-MALFORMED-NUMBER", 1, 5, "12abc", (1, 9), (";", 1, 10)),
    ("n = 1.2.3;", "LEX-MALFORMED-NUMBER", 1, 5, "1.2.3", (1, 9), (";", 1, 10)),
    ("n = 12.;", "LEX-MALFORMED-NUMBER", 1, 5, "12.", (1, 7), (";", 1, 8)),
    ("n = 10x;", "LEX-MALFORMED-NUMBER", 1, 5, "10x", (1, 7), (";", 1, 8)),
    ("n = 1e5;", "LEX-MALFORMED-NUMBER", 1, 5, "1e5", (1, 7), (";", 1, 8)),
    ("n = 0x1F;", "LEX-MALFORMED-NUMBER", 1, 5, "0x1F", (1, 8), (";", 1, 9)),
    ("n = 3_000;", "LEX-MALFORMED-NUMBER", 1, 5, "3_000", (1, 9), (";", 1, 10)),
    ("n = 1..2;", "LEX-MALFORMED-NUMBER", 1, 5, "1..2", (1, 8), (";", 1, 9)),
    ("n = 2.5x;", "LEX-MALFORMED-NUMBER", 1, 5, "2.5x", (1, 8), (";", 1, 9)),
    ("n = 5.", "LEX-MALFORMED-NUMBER", 1, 5, "5.", (1, 6), ("EOF", 1, 4)),
])
def test_one_lexical_error_and_lex_gap(source, code, line, col, found, span_end, gap_token):
    result, records = run(source)
    [rec] = records
    assert (rec.id, rec.code, rec.line, rec.column, rec.found) == ("E-0001", code, line, col, found)
    assert (rec.span_end.line, rec.span_end.column) == span_end
    assert (rec.phase, rec.severity, rec.caused_by, rec.expected) == ("lexical", "fatal", None, [])
    gapped = [(t.text, t.line, t.col, t.lex_gap) for t in result.tokens if t.lex_gap is not None]
    assert gapped == [gap_token + ("E-0001",)]


LEX_CASES = [
    ("LEX-INVALID-CHAR", "@", "token"),
    ("LEX-UNTERMINATED-STRING", '"a', "STRING_LIT"),
    ("LEX-BAD-CHAR-LITERAL", "'ab'", "CHAR_LIT"),
    ("LEX-UNTERMINATED-COMMENT", "/* a", "BLOCK_COMMENT"),
    ("LEX-MALFORMED-NUMBER", "1x", "number"),
    ("LEX-INVALID-ESCAPE", '"\\q"', "escape"),
    ("LEX-UNSUPPORTED-DIRECTIVE", "#define X", "directive"),
]


@pytest.mark.parametrize("code,source,rule_ref", LEX_CASES, ids=[c[0] for c in LEX_CASES])
def test_every_lex_code_is_reachable(code, source, rule_ref):
    [rec] = run(source)[1]
    assert (rec.code, rec.rule_ref, rec.phase) == (code, rule_ref, "lexical")


def test_invalid_escape_in_string_keeps_the_token():
    result, records = run('x = "a\\qb";')
    [rec] = records
    assert (rec.code, rec.line, rec.column, rec.found) == ("LEX-INVALID-ESCAPE", 1, 7, "\\q")
    assert rec.span_end == Position(1, 8)
    assert rec.message == "Unknown escape sequence '\\q'"
    s = result.tokens[2]
    assert (s.kind, s.text, s.value, s.lex_gap) == (TokenKind.STRING_LIT, '"a\\qb"', "ab", None)
    assert all(t.lex_gap is None for t in result.tokens)


def test_string_with_bad_escape_and_no_close_gives_two_records():
    result, records = run('"a\\q\ny')
    assert [(r.id, r.code, r.line, r.column) for r in records] == [
        ("E-0001", "LEX-INVALID-ESCAPE", 1, 3),
        ("E-0002", "LEX-UNTERMINATED-STRING", 1, 1),
    ]
    assert [(t.text, t.lex_gap) for t in result.tokens] == [("y", "E-0002"), ("EOF", None)]


def test_lex_gap_is_the_last_record_and_is_used_once():
    result, records = run("@ $ a b @")
    assert [r.id for r in records] == ["E-0001", "E-0002", "E-0003"]
    assert [(t.text, t.lex_gap) for t in result.tokens] == \
        [("a", "E-0002"), ("b", None), ("EOF", "E-0003")]


def test_lexing_continues_after_an_error():
    result, records = run("int x = 5 @ 2;\nint y;")
    assert len(records) == 1
    assert [t.text for t in result.tokens] == ["int", "x", "=", "5", "2", ";", "int", "y", ";", "EOF"]


# Traces T5 and T6 of docs/error-recovery.md section 9 (lexical part only).
T5 = "int main(void) {\n    int x = 5 @ 2;\n    return x;\n}\n"
T6 = ('#include <stdio.h>\nint main(void) {\n    int count = 0;\n    printf("total\\q\\n", count);\n'
      "    count = count + 1\n    result = count;\n    return 0;\n}\n")


def test_trace_t5_lexical_record():
    result, records = run(T5)
    assert [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by) for r in records] == \
        [("E-0001", "LEX-INVALID-CHAR", "2:15", "@", None)]
    assert records[0].snippet == "int main(void) {\n    int x = 5 @ 2;\n    return x;"
    assert [(t.text, t.line, t.col, t.lex_gap) for t in result.tokens if t.lex_gap] == \
        [("2", 2, 17, "E-0001")]


def test_trace_t6_lexical_record():
    result, records = run(T6)
    assert [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by) for r in records] == \
        [("E-0001", "LEX-INVALID-ESCAPE", "4:18", "\\q", None)]
    assert result.stdio_include == Position(1, 1)
    assert all(t.lex_gap is None for t in result.tokens)
    strings = [t for t in result.tokens if t.kind is TokenKind.STRING_LIT]
    assert [(s.line, s.col, s.value) for s in strings] == [(4, 12, "total\n")]
    assert (result.tokens[-1].line, result.tokens[-1].col) == (8, 2)


# ---------------------------------------------------------------- corpus: dev/001-007 and valid/

DEV_LEX = sorted((CORPUS / "dev").glob("00[1-7]-*.c"))
VALID = sorted((CORPUS / "valid").glob("*.c"))


def _read_raw(path):
    """File text with its newlines untouched (CRLF when git checked it out that way)."""
    return path.read_bytes().decode("utf-8")


def _sidecar(path):
    return json.loads(path.with_name(path.stem + ".expected.json").read_text(encoding="utf-8"))


def test_corpus_files_found():
    assert len(DEV_LEX) == 7
    assert len(VALID) >= 10


@pytest.mark.parametrize("c_path", DEV_LEX, ids=[p.name for p in DEV_LEX])
def test_dev_lexical_program_gives_its_root(c_path):
    _, records = run(_read_raw(c_path))
    assert [{"code": r.code, "line": r.line} for r in records] == _sidecar(c_path)["roots"]


@pytest.mark.parametrize("c_path", VALID, ids=[p.name for p in VALID])
def test_valid_program_has_no_lexical_record(c_path):
    text = _read_raw(c_path)
    result, records = run(text)
    assert records == []
    assert result.stdio_include == Position(1, 1)
    assert result.tokens[-1].line == len(text.splitlines())


@pytest.mark.parametrize("c_path", DEV_LEX + VALID, ids=[p.name for p in DEV_LEX + VALID])
def test_crlf_and_lf_give_the_same_result(c_path):
    lf = _read_raw(c_path).replace("\r\n", "\n")
    crlf = lf.replace("\n", "\r\n")
    (res_lf, rec_lf), (res_crlf, rec_crlf) = run(lf), run(crlf)
    assert res_lf == res_crlf
    assert [(r.code, r.line, r.column, r.found, r.span_end, r.snippet) for r in rec_lf] == \
        [(r.code, r.line, r.column, r.found, r.span_end, r.snippet) for r in rec_crlf]
