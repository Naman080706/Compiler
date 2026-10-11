"""tools/evaluate.py with a scripted FakeLLM on the dev split only (no network, no held-out read)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "evaluate.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=ROOT)


def test_fake_run_writes_results_labelled_pipeline_only(tmp_path):
    proc = run("--llm", "fake", "--splits", "dev", "--latency-n", "3", "--out-dir", str(tmp_path))
    assert proc.returncode == 0, proc.stderr
    res = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert res["meta"]["pipeline_only"] is True
    dev = res["splits"]["dev"]
    assert dev["f2"]["single_fault"]["reduction_pct"] >= 70
    assert dev["root_accuracy"]["program_exact_pct"] == 100.0
    assert dev["f7"]["nonexistent_citations"] == 0
    assert dev["latency"]["requests"] == 3
    md = (tmp_path / "results.md").read_text(encoding="utf-8")
    assert "PIPELINE-ONLY, NOT A REAL-MODEL RESULT" in md


def test_heldout_refused_without_flag(tmp_path):
    proc = run("--llm", "fake", "--splits", "heldout", "--out-dir", str(tmp_path))
    assert proc.returncode == 2 and "REFUSED" in proc.stderr
    assert not (tmp_path / "results.json").exists()
