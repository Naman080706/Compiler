"""Pipeline, PRD acceptance (F1, F4), determinism and CLI tests (plan 007)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cea.pipeline import CompileResult, compile_source

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "corpus"


def _c_files(split):
    """(split, path) for every .c file of one corpus split. Never called with "heldout" (held-out rule)."""
    return [(split, p) for p in sorted((CORPUS / split).glob("*.c"))]


def _sidecar(c_path):
    return json.loads(c_path.with_name(c_path.stem + ".expected.json").read_text(encoding="utf-8"))
T6 = ("#include <stdio.h>\nint main(void) {\n    int count = 0;\n    printf(\"total\\q\\n\", count);\n"
      "    count = count + 1\n    result = count;\n    return 0;\n}\n")


def test_f1_acceptance_one_record_per_phase():
    result = compile_source(T6, "t6.c")
    assert [(r.phase, r.code, r.line, r.column) for r in result.errors] == [
        ("lexical", "LEX-INVALID-ESCAPE", 4, 18),
        ("syntax", "SYN-MISSING-SEMICOLON", 5, 22),
        ("semantic", "SEM-UNDECLARED-VAR", 6, 5),
    ]
    assert not result.ok
    assert result.summary() == "3 fatal, 0 warnings"


def test_f4_acceptance_warnings_only_file_still_compiles():
    path = CORPUS / "valid" / "011-narrowing-warning.c"
    result = compile_source(path.read_text(encoding="utf-8"), path.name)
    assert [(r.code, r.severity) for r in result.errors] == [("WRN-IMPLICIT-NARROWING", "warning")]
    assert result.ok is True
    assert result.summary() == "0 fatal, 1 warning"


def test_compile_result_shape():
    result = compile_source("int main(void) {\n    return 0;\n}\n", "ok.c")
    assert isinstance(result, CompileResult)
    assert result.errors == [] and result.ok and result.summary() == "0 fatal, 0 warnings"
    assert result.tokens[-1].text == "EOF" and result.program.decls


@pytest.mark.parametrize("source", ["", "\n", "}", "int", "int main(", "@@@", "/*", "\"", "int main(void) { {{{ ",
                                    "int x = ;", "void main(void) { return 1; }", "for while if ; ) ] }"])
def test_compile_source_never_raises(source):
    result = compile_source(source, "junk.c")
    by_id = {r.id: r for r in result.errors}
    assert all(by_id[r.root_id].root_id == r.root_id and r.root_id <= r.id for r in result.errors)
    ids = [r.id for r in result.errors]
    assert ids == [f"E-{n:04d}" for n in range(1, len(ids) + 1)]
    assert all(r.caused_by is None or r.caused_by < r.id for r in result.errors)


DEV_AND_VALID = _c_files("dev") + _c_files("valid")


@pytest.mark.parametrize("split,c_path", DEV_AND_VALID, ids=[f"{s}/{p.name}" for s, p in DEV_AND_VALID])
def test_records_are_deterministic(split, c_path):
    text = c_path.read_text(encoding="utf-8")
    first = [r.to_dict() for r in compile_source(text, c_path.name).errors]
    second = [r.to_dict() for r in compile_source(text, c_path.name).errors]
    assert first == second


@pytest.mark.parametrize("split,c_path", _c_files("valid"), ids=[p.name for _, p in _c_files("valid")])
def test_valid_programs_report_exactly_their_expected_warnings(split, c_path):
    side = _sidecar(c_path)
    result = compile_source(c_path.read_text(encoding="utf-8"), c_path.name)
    assert sorted((r.code, r.line) for r in result.errors) == sorted((w["code"], w["line"]) for w in side["warnings"])


def _run_cli(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "cea", *args], capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=ROOT)


def test_cli_json_with_fatal_error_exits_1():
    path = CORPUS / "dev" / "060-one-per-phase.c"
    proc = _run_cli(str(path), "--json")
    assert proc.returncode == 1, proc.stderr
    data = json.loads(proc.stdout)
    assert data["file"] == path.name and data["ok"] is False and data["summary"] == "3 fatal, 0 warnings"
    assert [e["phase"] for e in data["errors"]] == ["lexical", "syntax", "semantic"]
    first = data["errors"][0]
    for key in ("id", "phase", "code", "severity", "line", "column", "found", "expected", "snippet", "root_id",
                "rule_ref", "language", "caused_by", "span_end", "message"):
        assert key in first
    assert first["span_end"].keys() == {"line", "column"}


def test_cli_json_has_clusters_array():
    proc = _run_cli(str(CORPUS / "dev" / "043-loop-counter-never-declared.c"), "--json")
    assert proc.returncode == 1, proc.stderr
    data = json.loads(proc.stdout)
    assert len(data["errors"]) == 9                                    # --json stays complete
    assert data["clusters"] == [{"root_id": "E-0001",
                                 "symptom_ids": [f"E-{n:04d}" for n in range(2, 10)]}]


def test_cli_text_shows_roots_with_related_count():
    proc = _run_cli(str(CORPUS / "dev" / "043-loop-counter-never-declared.c"))
    assert proc.returncode == 1, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("E-0001 043-loop-counter-never-declared.c:6:10: fatal [SEM-UNDECLARED-VAR]")
    assert lines[0].endswith("(+8 related)")
    assert lines[-1] == "9 fatal, 0 warnings"


def test_cli_all_lists_every_record():
    proc = _run_cli(str(CORPUS / "dev" / "043-loop-counter-never-declared.c"), "--all")
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 10 and not any("related" in ln for ln in lines)


def test_cli_root_without_symptoms_has_no_count():
    proc = _run_cli(str(CORPUS / "dev" / "063-fault-plus-warning.c"))
    lines = proc.stdout.strip().splitlines()
    assert [ln.split()[0] for ln in lines[:-1]] == ["E-0001", "E-0002"]
    assert not any("related" in ln for ln in lines)


def test_cli_warnings_only_exits_0():
    proc = _run_cli(str(CORPUS / "valid" / "011-narrowing-warning.c"))
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert "WRN-IMPLICIT-NARROWING" in lines[0] and ":7:" in lines[0]
    assert lines[-1] == "0 fatal, 1 warning"


def test_cli_clean_file_exits_0_with_json():
    proc = _run_cli(str(CORPUS / "valid" / "001-sum-of-marks.c"), "--json")
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["errors"] == []


def test_cli_missing_file_exits_2():
    proc = _run_cli("does-not-exist.c")
    assert proc.returncode == 2
    assert "cannot read" in proc.stderr
