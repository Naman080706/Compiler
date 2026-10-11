"""Parser against the corpus (plan 006): every dev program with a SYN root
reports it, the dev syntax records are exactly as traced, and single-token
deletions of every valid program never crash or trip the progress guard.
tests/corpus/heldout/ is deliberately never read here (corpus README section 5)."""
import json
from pathlib import Path

import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import LexResult, lex

ROOT = Path(__file__).resolve().parents[2]
DEV = sorted((ROOT / "tests" / "corpus" / "dev").glob("*.c"))
VALID = sorted((ROOT / "tests" / "corpus" / "valid").glob("*.c"))


def sidecar(path):
    return json.loads(path.with_name(path.stem + ".expected.json").read_text(encoding="utf-8"))


SYN_DEV = [p for p in DEV if any(r["code"].startswith("SYN-") for r in sidecar(p)["roots"])]

# Exact syntax records (code, line:col, found, caused_by) observed for every dev
# program with at least one syntax record; matches each sidecar's "notes" trace.
DEV_SYNTAX = {
    "002": [("SYN-EXPECTED-EXPRESSION", "12:5", "return", "E-0001")],
    "003": [("SYN-EXPECTED-EXPRESSION", "5:22", ";", "E-0001")],
    "005": [("SYN-EXPECTED-EXPRESSION", "4:20", ";", "E-0001")],
    "008": [("SYN-MISSING-SEMICOLON", "8:22", "count", None)],
    "009": [("SYN-UNBALANCED-BRACKET", "6:20", "{", None)],
    "010": [("SYN-EXPECTED-TOKEN", "6:11", "count", None)],
    "011": [("SYN-EXPECTED-EXPRESSION", "12:21", ";", None)],
    "012": [("SYN-EXPECTED-TYPE", "3:9", "a", None)],
    "013": [("SYN-UNEXPECTED-EOF", "12:14", "EOF", None)],
    "014": [("SYN-INVALID-ASSIGN-TARGET", "12:7", "=", None)],
    "015": [("SYN-UNSUPPORTED-FEATURE", "8:24", "goto", None), ("SYN-UNSUPPORTED-FEATURE", "10:1", "done", None)],
    "040": [("SYN-MISSING-SEMICOLON", "5:18", "int", None)],
    "041": [("SYN-UNBALANCED-BRACKET", "10:1", "int", None)],
    "042": [("SYN-UNEXPECTED-EOF", "12:2", "EOF", None)],
    "044": [("SYN-EXPECTED-EXPRESSION", "6:22", ";", None)],
    "045": [("SYN-EXPECTED-TOKEN", "7:11", "count", None)],
    "046": [("SYN-EXPECTED-EXPRESSION", "9:5", "if", "E-0001")],
    "048": [("SYN-MISSING-SEMICOLON", "3:15", "int", None)],
    "049": [("SYN-UNSUPPORTED-FEATURE", "8:9", "(", None)],
    "050": [("SYN-UNBALANCED-BRACKET", "7:28", "{", None)],
    "051": [("SYN-MISSING-SEMICOLON", "6:19", "i", None)],
    "052": [("SYN-UNSUPPORTED-FEATURE", "3:13", "(", None)],
    "060": [("SYN-MISSING-SEMICOLON", "8:27", "return", None)],
    "083": [("SYN-UNSUPPORTED-FEATURE", "4:15", ":", None)],
    "084": [("SYN-UNSUPPORTED-FEATURE", "3:18", "...", None)],
    "062": [("SYN-EXPECTED-EXPRESSION", "4:20", ";", None)],
}


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def records_for(path):
    src = path.read_text(encoding="utf-8")
    sink = ErrorSink(src)
    P.parse(lex(src, sink), sink)
    return sink.records


def test_syn_dev_selection_is_not_empty():
    assert len(SYN_DEV) >= 20, [p.name for p in SYN_DEV]


@pytest.mark.parametrize("path", SYN_DEV, ids=[p.name for p in SYN_DEV])
def test_dev_syn_roots_are_reported(path):
    got = {(r.code, r.line) for r in records_for(path) if r.phase == "syntax"}
    want = [(r["code"], r["line"]) for r in sidecar(path)["roots"] if r["code"].startswith("SYN-")]
    assert all(w in got for w in want), f"want {want}, got {sorted(got)}"


@pytest.mark.parametrize("path", DEV, ids=[p.name for p in DEV])
def test_dev_syntax_records_exact(path):
    got = [(r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
           for r in records_for(path) if r.phase == "syntax"]
    assert got == DEV_SYNTAX.get(path.name[:3], [])


def _deletion_cases():
    cases = []
    for path in VALID:
        src = path.read_text(encoding="utf-8")
        n = len(lex(src, ErrorSink(src)).tokens) - 1          # every token except EOF
        cases.append(pytest.param(path, n, id=path.name))
    return cases


@pytest.mark.parametrize("path,n_tokens", _deletion_cases())
def test_single_token_deletion_never_crashes(path, n_tokens):
    src = path.read_text(encoding="utf-8")
    base = lex(src, ErrorSink(src))
    for i in range(n_tokens):
        sink = ErrorSink(src)
        toks = base.tokens[:i] + base.tokens[i + 1:]
        prog = P.parse(LexResult(toks, base.stdio_include), sink)      # must not raise (incl. ProgressError)
        assert isinstance(prog, A.Program)
        ids = [r.id for r in sink.records]
        for r in sink.records:
            assert r.phase == "syntax" and r.code.startswith("SYN-")
            assert r.caused_by is None or r.caused_by in ids[:ids.index(r.id)], (i, r)
