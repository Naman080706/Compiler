"""cea.rules (plan 011): deterministic rule lookup from docs/language-spec.md."""
import pytest

from cea.catalog import PRODUCTION, load_catalog, load_grammar_rules
from cea.rules import RuleText, load_rules, rule_text


def test_rule_counts_by_kind():
    kinds = [r.kind for r in load_rules().values()]
    assert (kinds.count("lexical"), kinds.count("grammar"), kinds.count("semantic")) == (18, 36, 16)


def test_every_grammar_rule_name_resolves_as_grammar():
    for name in load_grammar_rules():
        assert rule_text(name).kind == "grammar", name


def test_every_catalog_rule_ref_resolves():
    refs = {e.rule_ref for e in load_catalog().values() if e.rule_ref != PRODUCTION}
    missing = sorted(r for r in refs if rule_text(r) is None)
    assert not missing


@pytest.mark.parametrize("ref,kind,text", [
    ("var_decl", "grammar", 'var_decl       = var_core , ";" ;'),
    ("statement", "grammar", "statement      = var_decl | if_stmt | while_stmt | for_stmt | return_stmt\n"
                             "               | break_stmt | continue_stmt | block | expr_stmt | empty_stmt ;"),
    ("STRING_LIT", "lexical", "STRING_LIT          = '\"' , { string_char | escape } , '\"' ;  (* may not span lines *)"),
])
def test_ebnf_rule_text(ref, kind, text):
    assert rule_text(ref) == RuleText(ref, kind, text)


def test_semantic_rule_has_paragraph_and_example():
    r = rule_text("sem.declare_before_use")
    assert r.kind == "semantic"
    assert r.text.startswith("Variables must be declared before use;")
    assert "```c" in r.text and r.text.endswith("```")
    assert "### " not in r.text


def test_include_line_inside_example_does_not_cut_the_rule():
    r = rule_text("sem.builtins")
    assert "#include <stdio.h>" in r.text and "printf(x);" in r.text and r.text.endswith("```")


@pytest.mark.parametrize("ref", ["", "nonexistent", "sem.nothing", "<production>", "##"])
def test_unknown_rule_is_none(ref):
    assert rule_text(ref) is None
