"""Unit tests for cea.diagnostics.ErrorSink, the error interceptor (plan 005, step 2)."""
import json

import pytest

from cea.catalog import CatalogEntry
from cea.diagnostics import ErrorSink, render_expected, split_lines
from cea.records import Position

FIVE_LINES = "l1\nl2\nl3\nl4\nl5\n"


def test_ids_root_id_language_in_creation_order():
    sink = ErrorSink("x\n")
    a = sink.report("LEX-INVALID-CHAR", 1, 1, found="@")
    b = sink.report("SEM-UNDECLARED-VAR", 1, 1, found="x", name="x", caused_by="E-0001")
    assert [r.id for r in sink.records] == ["E-0001", "E-0002"]
    assert (a.root_id, b.root_id) == ("E-0001", "E-0002")
    assert (a.language, b.language) == ("c", "c")
    assert (a.caused_by, b.caused_by) == (None, "E-0001")


def test_ids_have_four_digits_past_nine():
    sink = ErrorSink("x")
    for _ in range(10):
        sink.report("LEX-INVALID-CHAR", 1, 1, found="@")
    assert sink.records[-1].id == "E-0010"


@pytest.mark.parametrize("code,phase,severity,rule_ref", [
    ("LEX-MALFORMED-NUMBER", "lexical", "fatal", "number"),
    ("SYN-INVALID-ASSIGN-TARGET", "syntax", "fatal", "assignment"),
    ("SEM-UNDECLARED-VAR", "semantic", "fatal", "sem.declare_before_use"),
    ("WRN-UNUSED-VAR", "semantic", "warning", "sem.unused_declaration"),
])
def test_phase_severity_rule_ref_come_from_the_catalog(code, phase, severity, rule_ref):
    rec = ErrorSink("x").report(code, 1, 1, found="x", name="x")
    assert (rec.phase, rec.severity, rec.rule_ref) == (phase, severity, rule_ref)


@pytest.mark.parametrize("source,line,snippet", [
    (FIVE_LINES, 1, "l1\nl2"),
    (FIVE_LINES, 3, "l2\nl3\nl4"),
    (FIVE_LINES, 5, "l4\nl5"),
    (FIVE_LINES.replace("\n", "\r\n"), 3, "l2\nl3\nl4"),
    ("only", 1, "only"),
    ("", 1, ""),
    ("a\n\tb  \nc", 2, "a\n\tb  \nc"),
])
def test_snippet_is_up_to_three_unmodified_lines(source, line, snippet):
    assert ErrorSink(source).report("LEX-INVALID-CHAR", line, 1, found="@").snippet == snippet


@pytest.mark.parametrize("source,lines", [
    ("", [""]),
    ("a", ["a"]),
    ("a\n", ["a"]),
    ("a\r\nb\r\n", ["a", "b"]),
    ("a\rb", ["a", "b"]),
    ("a\n\n", ["a", ""]),
])
def test_split_lines(source, lines):
    assert split_lines(source) == lines


@pytest.mark.parametrize("template,expected,phase,rendered", [
    ("Expected {expected} but found '{found}'", [";"], "syntax", "';'"),
    ("Expected {expected} but found '{found}'", [")", ";"], "syntax", "')' or ';'"),
    ("Expected '{expected}' to close", [")"], "syntax", ")"),
    ("Expected '{expected}' to close", [")", "]"], "syntax", ") or ]"),
    ("Expected {expected}", [], "syntax", ""),
    ("expects {expected} argument(s)", ["2"], "semantic", "2"),
    ("where {expected} is required", ["int", "double"], "semantic", "int or double"),
    ("got {expected}", ["x"], "lexical", "x"),
])
def test_render_expected_quoting_rule(template, expected, phase, rendered):
    assert render_expected(template, expected, phase) == rendered


@pytest.mark.parametrize("code,kwargs,message", [
    ("LEX-INVALID-CHAR", dict(found="@"), "Unexpected character '@'"),
    ("LEX-INVALID-ESCAPE", dict(found="\\q"), "Unknown escape sequence '\\q'"),
    ("SYN-EXPECTED-TOKEN", dict(found="x", expected=["("], rule_ref="if_stmt"),
     "Expected '(' but found 'x'"),
    ("SYN-UNBALANCED-BRACKET",
     dict(found="{", expected=[")"], rule_ref="while_stmt", opener="(", open_line=3),
     "Expected ')' to close '(' from line 3 but found '{'"),
    ("SYN-MISSING-SEMICOLON", dict(found="result", expected=[";"], rule_ref="expr_stmt",
                                   context="the expression statement"),
     "Expected ';' after the expression statement but found 'result'"),
    ("SYN-UNEXPECTED-EOF", dict(found="EOF", expected=["}"], rule_ref="block", context="a block"),
     "File ended inside a block; expected '}'"),
    ("SEM-UNDECLARED-VAR", dict(found="result", name="result"),
     "Variable 'result' is used before it is declared"),
    ("WRN-UNREACHABLE-CODE", dict(found="printf"), "This statement can never run"),
    # semantic templates: {expected} and {found} are inserted raw (no quotes added)
    ("SEM-ARG-COUNT", dict(found="1", expected=["2"], name="add"),
     "'add' expects 2 argument(s) but got 1"),
    ("SEM-TYPE-MISMATCH", dict(found="double", expected=["int"]),
     "Cannot use double where int is required"),
    ("SEM-ARG-TYPE", dict(found="char", expected=["double"], index=2, name="area"),
     "Argument 2 of 'area' must be double but is char"),
    ("SEM-RETURN-TYPE", dict(found="int", expected=["void"], name="log_it"),
     "Function 'log_it' returns void but this returns int"),
    ("WRN-IMPLICIT-NARROWING", dict(found="double", expected=["int"]),
     "double value converted to int; the fractional part is lost"),
])
def test_message_is_the_filled_template(code, kwargs, message):
    assert ErrorSink("x").report(code, 1, 1, **kwargs).message == message


def test_missing_placeholder_raises_key_error():
    with pytest.raises(KeyError):
        ErrorSink("x").report("SEM-UNDECLARED-VAR", 1, 1, found="y")        # no name=


def test_unknown_code_raises_key_error():
    with pytest.raises(KeyError):
        ErrorSink("x").report("LEX-NOPE", 1, 1, found="@")


def test_production_code_requires_rule_ref():
    with pytest.raises(ValueError):
        ErrorSink("x").report("SYN-EXPECTED-EXPRESSION", 1, 1, found=";")


def test_rule_ref_must_be_a_grammar_rule():
    with pytest.raises(ValueError):
        ErrorSink("x").report("SYN-EXPECTED-EXPRESSION", 1, 1, found=";", rule_ref="not_a_rule")
    rec = ErrorSink("x").report("SYN-EXPECTED-EXPRESSION", 1, 1, found=";", rule_ref="var_decl")
    assert rec.rule_ref == "var_decl"


def test_expected_must_not_be_a_bare_string():
    with pytest.raises(TypeError):
        ErrorSink("x").report("SYN-EXPECTED-TOKEN", 1, 1, found="x", expected="(", rule_ref="if_stmt")


def test_positions_are_one_based():
    with pytest.raises(ValueError):
        ErrorSink("x").report("LEX-INVALID-CHAR", 0, 1, found="@")


def test_failed_report_creates_no_record_and_uses_no_id():
    sink = ErrorSink("x")
    with pytest.raises(KeyError):
        sink.report("SEM-UNDECLARED-VAR", 1, 1, found="y")
    assert sink.records == []
    assert sink.report("LEX-INVALID-CHAR", 1, 1, found="@").id == "E-0001"


@pytest.mark.parametrize("found,span_end", [
    ("count", Position(3, 9)),
    ("@", Position(3, 5)),
    ("", Position(3, 5)),
])
def test_default_span_end(found, span_end):
    assert ErrorSink(FIVE_LINES).report("LEX-INVALID-CHAR", 3, 5, found=found).span_end == span_end


@pytest.mark.parametrize("code,found,kwargs", [
    ("SYN-UNEXPECTED-EOF", "EOF", dict(expected=["}"], rule_ref="block", context="a block")),
    ("SYN-EXPECTED-EXPRESSION", "EOF", dict(rule_ref="assignment")),
    ("SYN-MISSING-SEMICOLON", "result", dict(expected=[";"], rule_ref="expr_stmt", context="x")),
    ("SEM-MISSING-MAIN", "EOF", {}),
])
def test_default_span_end_is_zero_width_for_eof_and_missing_semicolon(code, found, kwargs):
    rec = ErrorSink(FIVE_LINES).report(code, 5, 3, found=found, **kwargs)
    assert rec.span_end == Position(5, 3)


def test_explicit_span_end_and_expected_list():
    rec = ErrorSink(FIVE_LINES).report("SYN-EXPECTED-TOKEN", 2, 1, found="x", expected=("(", ")"),
                                       rule_ref="if_stmt", span_end=Position(4, 2))
    assert rec.span_end == Position(4, 2)
    assert rec.expected == ["(", ")"]


@pytest.mark.parametrize("fatal,warnings,text", [
    (0, 0, "0 fatal, 0 warnings"),
    (1, 0, "1 fatal, 0 warnings"),
    (0, 1, "0 fatal, 1 warning"),
    (1, 1, "1 fatal, 1 warning"),
    (2, 3, "2 fatal, 3 warnings"),
])
def test_summary(fatal, warnings, text):
    sink = ErrorSink("x")
    for _ in range(fatal):
        sink.report("LEX-INVALID-CHAR", 1, 1, found="@")
    for _ in range(warnings):
        sink.report("WRN-UNUSED-VAR", 1, 1, found="t", name="t")
    assert sink.summary() == text


def test_records_property_is_a_copy():
    sink = ErrorSink("x")
    sink.report("LEX-INVALID-CHAR", 1, 1, found="@")
    sink.records.clear()
    assert len(sink.records) == 1


def test_custom_catalog_is_used():
    cat = {"LEX-X": CatalogEntry("LEX-X", "lexical", "warning", "malformed-token", "token", "Bad {found}")}
    rec = ErrorSink("x", catalog=cat).report("LEX-X", 1, 1, found="@")
    assert (rec.severity, rec.message) == ("warning", "Bad @")


def test_record_serialises_to_json():
    rec = ErrorSink(FIVE_LINES).report("LEX-INVALID-CHAR", 2, 1, found="@")
    assert json.loads(json.dumps(rec.to_dict()))["span_end"] == {"line": 2, "column": 1}
