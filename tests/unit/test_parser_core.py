"""Parser core: cursor, expect(), catalog code selection (rules 0-5), bracket
stack, caused_by precedence and rule_ref (plan 006 step 2)."""
import dataclasses

import pytest

from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


def make(src):
    sink = ErrorSink(src)
    return P.Parser(lex(src, sink).tokens, sink), sink


def at_text(p, text):
    """Move the cursor to the first token with this text."""
    p.pos = next(i for i, t in enumerate(p.toks) if t.text == text)
    return p


def test_cursor_and_match_track_brackets():
    p, _ = make("( [ { } ] )")
    for t in "([{":
        p.match(t)
    assert [b.text for b in p.brackets] == ["(", "[", "{"]
    for t in "}])":
        p.match(t)
    assert p.brackets == [] and p.cur.kind is P.K.EOF
    assert p.consume().kind is P.K.EOF and p.pos == len(p.toks) - 1   # EOF is never passed


def test_match_semicolon_and_brace_close_region():
    p, _ = make("; }")
    p.recovering = "E-0009"
    p.match(";")
    assert p.recovering is None
    p.recovering = "E-0009"
    p.match("}")
    assert p.recovering is None


def test_expect_failure_raises_after_one_record():
    p, sink = make("x")
    p.rules.append("if_stmt")
    with pytest.raises(P.ParseError) as ei:
        p.expect("(")
    (rec,) = sink.records
    assert ei.value.error_id == rec.id == "E-0001" and ei.value.code == rec.code == "SYN-EXPECTED-TOKEN"
    assert (rec.line, rec.column, rec.found, rec.expected, rec.rule_ref) == (1, 1, "x", ["("], "if_stmt")
    assert rec.message == "Expected '(' but found 'x'"


@pytest.mark.parametrize("src,found,expected,code", [
    ("goto", "goto", [";"], "SYN-UNSUPPORTED-FEATURE"),         # rule 0 beats rule 2
    ("f(a, ...)", "...", [")"], "SYN-UNSUPPORTED-FEATURE"),        # rule 0: UNSUPPORTED_OP
    ("int * p", "*", [P.IDENT], "SYN-EXPECTED-TOKEN"),             # a pointer declarator is ordinary now
    ("x * p", "*", [P.IDENT], "SYN-EXPECTED-TOKEN"),               # '*' after a non-type is ordinary
    ("x", "EOF", [";"], "SYN-UNEXPECTED-EOF"),                     # rule 1 beats rule 2
    ("x y", "y", [";"], "SYN-MISSING-SEMICOLON"),                  # rule 2
    ("x y", "y", [")"], "SYN-UNBALANCED-BRACKET"),                 # rule 3: only closing brackets
    ("x y", "y", ["]"], "SYN-UNBALANCED-BRACKET"),
    ("x y", "y", ["}"], "SYN-UNBALANCED-BRACKET"),
    ("x )", ")", [P.EXPR], "SYN-UNBALANCED-BRACKET"),              # rule 3: stray closer, no opener
    ("x y", "y", [P.EXPR], "SYN-EXPECTED-EXPRESSION"),             # rule 4
    ("x y", "y", [P.TYPE], "SYN-EXPECTED-TYPE"),                   # rule 4
    ("x y", "y", ["("], "SYN-EXPECTED-TOKEN"),                     # rule 5
    ("x y", "y", [",", ")"], "SYN-EXPECTED-TOKEN"),                # ',' is not a closing bracket
    ("x y", "y", [P.IDENT], "SYN-EXPECTED-TOKEN"),
])
def test_select_code_rules_0_to_5(src, found, expected, code):
    p, _ = make(src)
    at_text(p, found) if found != "EOF" else setattr(p, "pos", len(p.toks) - 1)
    assert p.select_code(p.cur, expected) == code


def test_stray_closer_uses_only_matched_openers():
    p, _ = make("( )")
    p.pos = 1
    assert p.select_code(p.cur, [P.EXPR]) == "SYN-UNBALANCED-BRACKET"   # '(' was never matched
    p.pos = 0
    p.match("(")
    assert p.select_code(p.cur, [P.EXPR]) == "SYN-EXPECTED-EXPRESSION"  # now it has an opener


def test_bracket_detail_names_opener_or_says_nothing_opened_it():
    p, _ = make("( x )")
    p.match("(")                                                           # '(' on line 1 is open
    assert p.bracket_detail(p.cur, [")"]) == "expected ')' to close '(' from line 1"
    assert p.bracket_detail(p.cur, ["]"]) == "expected ']' but no '[' is open"
    p.pos = 2
    assert p.bracket_detail(p.cur, [P.EXPR]) == "nothing opened it"         # stray closer


def test_probe_stray_closing_brace_message():
    src = "int main(void) { return 0; }\n}\n"
    sink = ErrorSink(src)
    P.parse(lex(src, sink), sink)
    (rec,) = sink.records
    assert rec.code == "SYN-UNBALANCED-BRACKET" and (rec.line, rec.column) == (2, 1)
    assert rec.message == "Unbalanced bracket at '}': nothing opened it"
    assert "?" not in rec.message


def test_caused_by_precedence_r2_then_r1_then_r9():
    p, sink = make("int main(void) { int x = 5 @ 2; }")      # '2' carries lex_gap E-0001
    tok = at_text(p, "2").cur
    assert tok.lex_gap == "E-0001"
    p.block_orphans.append("E-0005")
    p.unsupported_ids.add("E-0005")
    p.recovering = "E-0003"
    assert p.caused_by(tok) == "E-0003"                       # R2
    p.recovering = None
    assert p.caused_by(tok) == "E-0001"                       # R1
    assert p.caused_by(dataclasses.replace(tok, lex_gap=None)) == "E-0005"   # R9
    p.unsupported_ids.clear()
    assert p.caused_by(dataclasses.replace(tok, lex_gap=None)) is None


def test_rule_ref_is_innermost_rule_and_unwinds():
    class Probe(P.Parser):
        @P.rule("statement")
        def outer(self):
            return self.inner()

        @P.rule("primary")
        def inner(self):
            self.fail([P.EXPR])

    sink = ErrorSink("x")
    probe = Probe(lex("x", sink).tokens, sink)
    with pytest.raises(P.ParseError):
        probe.outer()
    assert sink.records[0].rule_ref == "primary" and probe.rules == []


def test_eof_record_is_zero_width_and_opens_region():
    p, sink = make("x")
    p.pos = 1
    p.rules.append("block")
    rid = p.report("SYN-UNEXPECTED-EOF", p.cur, ["}"])
    rec = sink.records[0]
    assert (rec.line, rec.column, rec.span_end.line, rec.span_end.column) == (1, 2, 1, 2)
    assert rec.found == "EOF" and rec.message == "File ended inside the block; expected '}'"
    assert p.recovering == rid


def test_production_codes_and_rule_names_match_the_docs():
    from cea.catalog import load_catalog, load_grammar_rules
    cat = load_catalog()
    assert P.PRODUCTION_CODES == {c for c, e in cat.items() if e.rule_ref == "<production>"}
    used = {name for name in dir(P.Parser)
            if getattr(getattr(P.Parser, name), "__wrapped__", None) is not None}
    assert used <= load_grammar_rules(), used - load_grammar_rules()
    assert set(P.RULE_PHRASES) <= load_grammar_rules()
