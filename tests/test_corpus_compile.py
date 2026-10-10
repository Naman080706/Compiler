"""Corpus-versus-compiler contract test (plan 003).

Skipped until milestone 1 provides ``cea.pipeline.compile_source``. The full
interface contract is written in tests/corpus/README.md.
"""
import pytest

pipeline = pytest.importorskip("cea.pipeline")

import corpus_lib as cl  # noqa: E402

RECORD_ATTRS = ("id", "code", "line", "column", "severity", "phase", "root_id", "caused_by")


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
    # Deliberately a SUBSET check: every expected root and warning must be
    # reported with the same (code, line). Exact equality between the expected
    # roots and the records the compiler marks as roots (root_id == id) is
    # deferred to the F2 clustering milestone, which will tighten this test.
    missing = [e for e in side["roots"] + side["warnings"] if (e["code"], e["line"]) not in got]
    assert not missing, f"not reported as (code, line): {missing}; got {sorted(got)}"
    if side["split"] == "valid":
        fatal = [(r.code, r.line) for r in result.errors if r.severity == "fatal"]
        assert not fatal, f"valid program produced fatal errors: {fatal}"
