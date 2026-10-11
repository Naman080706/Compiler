"""tools/metrics_f8.py: the F8 metric in oracle mode (FakeLLM replaying known fixes; pipeline test only)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "metrics_f8.py"


def test_oracle_mode_runs_and_says_real_numbers_need_a_real_llm():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.splitlines()
    assert out[0].startswith("F8 metric, split=dev, fixable roots = ") and out[0].endswith("LLM = oracle")
    assert out[1].startswith("verified within 3 attempts: ") and "(target >= 80%)" in out[1]
    assert any("REAL numbers need a real LLM" in line for line in out)
