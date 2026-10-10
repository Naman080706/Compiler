"""Unit tests for cea.records (plan 005, step 1)."""
import dataclasses
import json

import pytest

from cea.records import ErrorRecord, Position

FIELD_ORDER = [
    "id", "phase", "code", "severity", "line", "column", "found", "expected", "snippet",
    "root_id", "rule_ref", "language", "caused_by", "span_end", "message",
]


def _record(**over):
    base = dict(
        id="E-0001", phase="lexical", code="LEX-INVALID-CHAR", severity="fatal", line=2,
        column=15, found="@", expected=[], snippet="a\nb\nc", root_id="E-0001", rule_ref="token",
        language="c", caused_by=None, span_end=Position(2, 15), message="Unexpected character '@'",
    )
    base.update(over)
    return ErrorRecord(**base)


def test_field_names_and_order_follow_the_contract():
    assert [f.name for f in dataclasses.fields(ErrorRecord)] == FIELD_ORDER


def test_position_is_frozen_and_hashable():
    p = Position(3, 4)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.line = 5
    assert {p, Position(3, 4)} == {p}


def test_to_dict_is_json_ready():
    d = _record(expected=[";"], caused_by="E-0000").to_dict()
    assert list(d) == FIELD_ORDER
    assert d["span_end"] == {"line": 2, "column": 15}
    assert d["expected"] == [";"]
    assert json.loads(json.dumps(d)) == d
