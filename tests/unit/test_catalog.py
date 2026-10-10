"""Unit tests for cea.catalog: parsing docs/error-catalog.md (plan 005, step 1)."""
from collections import Counter

import pytest

from cea.catalog import PRODUCTION, CatalogEntry, load_catalog, load_grammar_rules

PRODUCTION_CODES = {
    "SYN-MISSING-SEMICOLON", "SYN-UNBALANCED-BRACKET", "SYN-EXPECTED-TOKEN",
    "SYN-EXPECTED-EXPRESSION", "SYN-EXPECTED-TYPE", "SYN-UNEXPECTED-EOF",
    "SYN-UNSUPPORTED-FEATURE",
}
WARNING_CODES = {
    "WRN-UNUSED-VAR", "WRN-UNREACHABLE-CODE", "WRN-IMPLICIT-NARROWING",
    "WRN-MISSING-RETURN", "WRN-ASSIGN-IN-CONDITION",
}


def test_catalog_has_37_codes():
    assert len(load_catalog()) == 37


def test_codes_per_phase():
    phases = Counter(e.phase for e in load_catalog().values())
    assert phases == {"lexical": 7, "syntax": 8, "semantic": 22}


def test_severity_comes_from_the_table():
    cat = load_catalog()
    assert {c for c, e in cat.items() if e.severity == "warning"} == WARNING_CODES
    assert {e.severity for e in cat.values()} == {"fatal", "warning"}


def test_code_prefix_matches_phase():
    prefix_phase = {"LEX": "lexical", "SYN": "syntax", "SEM": "semantic", "WRN": "semantic"}
    for code, e in load_catalog().items():
        assert e.code == code
        assert e.phase == prefix_phase[code[:3]], code


def test_backticks_are_stripped():
    cat = load_catalog()
    assert cat["LEX-INVALID-CHAR"].rule_ref == "token"
    assert cat["SEM-UNDECLARED-VAR"].rule_ref == "sem.declare_before_use"
    assert all("`" not in e.rule_ref for e in cat.values())


def test_production_rows():
    cat = load_catalog()
    assert {c for c, e in cat.items() if e.rule_ref == PRODUCTION} == PRODUCTION_CODES
    assert cat["SYN-INVALID-ASSIGN-TARGET"].rule_ref == "assignment"


@pytest.mark.parametrize("code,template", [
    ("LEX-INVALID-CHAR", "Unexpected character '{found}'"),
    ("LEX-UNSUPPORTED-DIRECTIVE", "Only '#include <stdio.h>' is supported; '{found}' is not"),
    ("SYN-UNBALANCED-BRACKET",
     "Expected '{expected}' to close '{opener}' from line {open_line} but found '{found}'"),
    ("SYN-EXPECTED-TOKEN", "Expected {expected} but found '{found}'"),
    ("WRN-ASSIGN-IN-CONDITION", "Assignment used as a condition; did you mean '=='?"),
])
def test_message_templates(code, template):
    assert load_catalog()[code].message_template == template


def test_category_column():
    cat = load_catalog()
    assert cat["LEX-UNTERMINATED-COMMENT"].category == "unclosed-delimiter"
    assert cat["SEM-REDECLARED"].category == "redeclaration"


def test_table_order_is_kept():
    codes = list(load_catalog())
    assert codes[0] == "LEX-INVALID-CHAR" and codes[-1] == "WRN-ASSIGN-IN-CONDITION"


def test_cached_entries_are_shared_but_dict_is_a_copy():
    a, b = load_catalog(), load_catalog()
    assert a is not b
    assert a["LEX-INVALID-CHAR"] is b["LEX-INVALID-CHAR"]


def test_explicit_path(tmp_path):
    p = tmp_path / "cat.md"
    p.write_text(
        "| Code | Phase | Severity | Category | rule_ref | Message template | Example trigger |\n"
        "|---|---|---|---|---|---|---|\n"
        "| LEX-X | lexical | fatal | malformed-token | `token` | Bad '{found}' | `@` |\n",
        encoding="utf-8",
    )
    assert load_catalog(p) == {
        "LEX-X": CatalogEntry("LEX-X", "lexical", "fatal", "malformed-token", "token", "Bad '{found}'"),
    }


def test_row_with_wrong_cell_count_raises(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text("| LEX-X | lexical | fatal | token | Bad |\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_catalog(p)


def test_grammar_rule_names():
    rules = load_grammar_rules()
    assert len(rules) == 36
    assert {"program", "statement", "var_decl", "assignment", "primary"} <= rules
    assert "token" not in rules          # lexical rules (section 1) are not syntax rule_refs
