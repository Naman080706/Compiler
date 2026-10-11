"""Corpus-versus-compiler contract test (plans 003, 009).

The full interface contract is written in tests/corpus/README.md §6.
Since plan 009 (F2 clustering), dev and valid programs are checked EXACTLY:
the (code, line) list of fatal roots (records with root_id == id) must equal
the sidecar's ``roots``. Warnings keep the subset check.
"""
import pytest

pipeline = pytest.importorskip("cea.pipeline")

import corpus_lib as cl  # noqa: E402

RECORD_ATTRS = ("id", "code", "line", "column", "severity", "phase", "root_id", "caused_by")
EXACT_ROOT_SPLITS = ("dev", "valid")   # heldout keeps the subset check until milestone 5


def _cases():
    cases = []
    for split, c_path in cl.c_files():
        marks = [pytest.mark.corpus]
        if split == "heldout":
            marks.append(pytest.mark.heldout)  # deselected by default (addopts); milestone 5 only
        cases.append(pytest.param(c_path, id=f"{split}/{c_path.name}", marks=marks))
    return cases


@pytest.mark.parametrize("c_path", _cases())
def test_expected_diagnostics_are_reported(c_path):
    side = cl.load_sidecar(c_path)
    result = pipeline.compile_source(c_path.read_text(encoding="utf-8"), c_path.name)
    for rec in result.errors:
        for attr in RECORD_ATTRS:
            assert hasattr(rec, attr), f"error record lacks attribute {attr!r}: {rec!r}"
    got = {(rec.code, rec.line) for rec in result.errors}
    # Every expected root and warning must be reported with the same (code, line).
    missing = [e for e in side["roots"] + side["warnings"] if (e["code"], e["line"]) not in got]
    assert not missing, f"not reported as (code, line): {missing}; got {sorted(got)}"
    if side["split"] in EXACT_ROOT_SPLITS:
        # F2 (plan 009): the fatal roots the compiler displays are exactly the sidecar roots.
        # Compared as sorted lists, so a duplicated (code, line) root would also be caught.
        fatal_roots = sorted((r.code, r.line) for r in result.errors if r.root_id == r.id and r.severity == "fatal")
        expected = sorted((e["code"], e["line"]) for e in side["roots"])
        detail = [(r.id, r.code, r.line, r.found, r.caused_by, r.root_id) for r in result.errors]
        assert fatal_roots == expected, f"fatal roots {fatal_roots} != sidecar roots {expected}; records {detail}"
    if side["split"] == "valid":
        fatal = [(r.code, r.line) for r in result.errors if r.severity == "fatal"]
        assert not fatal, f"valid program produced fatal errors: {fatal}"
