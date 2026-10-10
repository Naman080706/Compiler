"""Structural checks on tests/corpus (plan 003). Runs before any compiler code exists."""
import re

import pytest

import corpus_lib as cl

pytestmark = pytest.mark.corpus

FIELDS = {
    "description": str, "split": str, "injected_faults": list, "roots": list,
    "warnings": list, "cascading": bool, "fixable": bool, "gcc_rejects": bool, "notes": str,
}
NAME_RE = re.compile(r"^\d{3}-[a-z0-9]+(-[a-z0-9]+)*\.c$")
ALL_C = cl.c_files()


@pytest.fixture(scope="module")
def catalog():
    if not cl.CATALOG.exists():
        pytest.fail("docs/error-catalog.md is missing; it is created by plan 001")
    return cl.load_catalog()


def test_catalog_has_37_codes(catalog):
    assert len(catalog) == 37, sorted(catalog)


def test_corpus_folders_exist():
    for split in cl.SPLITS:
        assert (cl.CORPUS / split).is_dir(), f"missing tests/corpus/{split}/"


def test_every_c_file_has_sidecar():
    missing = [str(p.relative_to(cl.CORPUS)) for _, p in ALL_C if not cl.sidecar_for(p).exists()]
    assert not missing, f"no sidecar for: {missing}"


def test_every_sidecar_has_c_file():
    orphans = [str(p.relative_to(cl.CORPUS)) for _, p in cl.sidecar_files() if not cl.c_for(p).exists()]
    assert not orphans, f"sidecar without .c: {orphans}"


def test_numbers_unique_per_split():
    for split in cl.SPLITS:
        nums = [p.name[:3] for _, p in cl.c_files(split)]
        dupes = sorted({n for n in nums if nums.count(n) > 1})
        assert not dupes, f"{split}: duplicate numbers {dupes}"


def _check_loc_list(value, field, n_lines, catalog, want_severity):
    seen = set()
    for item in value:
        assert isinstance(item, dict) and set(item) == {"code", "line"}, \
            f"{field} items must be objects with exactly 'code' and 'line': {item!r}"
        code, line = item["code"], item["line"]
        assert isinstance(code, str), f"{field}: code must be str: {item!r}"
        assert isinstance(line, int) and not isinstance(line, bool), f"{field}: line must be int: {item!r}"
        assert code in catalog, f"{field}: {code} is not in docs/error-catalog.md"
        assert catalog[code]["severity"] == want_severity, \
            f"{field}: {code} has severity {catalog[code]['severity']}, expected {want_severity}"
        assert 1 <= line <= n_lines, f"{field}: line {line} outside 1..{n_lines} for {code}"
        assert (code, line) not in seen, f"{field}: duplicate entry {item!r}"
        seen.add((code, line))


@pytest.mark.parametrize("split,c_path", ALL_C, ids=[f"{s}/{p.name}" for s, p in ALL_C])
def test_sidecar_schema(split, c_path, catalog):
    assert NAME_RE.match(c_path.name), f"bad file name {c_path.name} (want NNN-short-slug.c)"
    side = cl.load_sidecar(c_path)
    assert set(side) == set(FIELDS), \
        f"fields differ: extra={sorted(set(side) - set(FIELDS))} missing={sorted(set(FIELDS) - set(side))}"
    for name, typ in FIELDS.items():
        assert isinstance(side[name], typ), f"{name} must be {typ.__name__}"
    assert side["description"].strip(), "description is empty"
    assert side["split"] == split, f"split is {side['split']!r} but the file is in {split}/"
    assert all(isinstance(f, str) and f.strip() for f in side["injected_faults"]), \
        "injected_faults must be non-empty strings"
    text = c_path.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n"), \
        "file must end with exactly one newline (no trailing blank lines)"
    n = cl.line_count(c_path)
    _check_loc_list(side["roots"], "roots", n, catalog, "fatal")
    _check_loc_list(side["warnings"], "warnings", n, catalog, "warning")
    if split == "valid":
        assert side["roots"] == [], "valid programs must have empty roots"
        assert side["injected_faults"] == [], "valid programs have no injected faults"
        assert side["cascading"] is False and side["fixable"] is False, \
            "valid programs have cascading=false and fixable=false"
        assert side["gcc_rejects"] is False, "a valid program must be accepted by gcc"
    else:
        assert side["injected_faults"], "faulty programs must list their injected faults"
        assert side["roots"] or side["warnings"], "a faulty program must expect at least one diagnostic"
    if any(r["code"].startswith(("LEX-", "SYN-")) for r in side["roots"]):
        assert side["warnings"] == [], "programs with a LEX/SYN root must not expect warnings"
    if side["cascading"]:
        assert side["roots"], "a cascading program needs at least one root"
    if split == "heldout":
        assert 15 <= n <= 40, f"heldout programs must be 15-40 lines, got {n}"


def _sidecars(split):
    return [cl.load_sidecar(p) for _, p in cl.c_files(split)]


def test_dev_covers_every_catalog_code(catalog):
    used = {e["code"] for s in _sidecars("dev") for e in s["roots"] + s["warnings"]}
    missing = sorted(set(catalog) - used)
    assert not missing, f"codes with no dev program: {missing}"


def test_dev_has_cascading_and_multi_fault_programs():
    dev = _sidecars("dev")
    cascading = sum(1 for s in dev if s["cascading"])
    multi = sum(1 for s in dev if len(s["injected_faults"]) in (2, 3))
    assert cascading >= 10, f"dev has {cascading} cascading programs, need >= 10"
    assert multi >= 3, f"dev has {multi} programs with 2-3 faults, need >= 3"


def test_heldout_size_and_coverage(catalog):
    held = _sidecars("heldout")
    assert len(held) == 20, f"heldout must hold exactly 20 programs, has {len(held)}"
    cascading = sum(1 for s in held if s["cascading"])
    assert cascading >= 8, f"heldout has {cascading} cascading programs, need >= 8"
    cats = {catalog[e["code"]]["category"] for s in held for e in s["roots"] + s["warnings"]}
    assert len(cats) >= 8, f"heldout covers {len(cats)} categories {sorted(cats)}, need >= 8"


def test_valid_size():
    valid = _sidecars("valid")
    assert len(valid) >= 10, f"valid has {len(valid)} programs, need >= 10"
    with_warnings = sum(1 for s in valid if s["warnings"])
    assert with_warnings >= 2, f"{with_warnings} valid programs expect warnings, need >= 2"
