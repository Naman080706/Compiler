"""tools/metrics_f2.py (plan 009): the F2 metric over the dev cascade set, and the held-out guard."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "metrics_f2.py"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=ROOT)


def test_dev_metrics_totals():
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.splitlines()
    assert out[0] == "F2 metric, split=dev, cascade set = 15 programs"
    assert "TOTAL raw=50 displayed=20 reduction=60.0%" in out
    assert "SINGLE-FAULT raw=40 displayed=11 reduction=72.5%" in out
    assert "part (b): 11/11 single-fault programs display exactly 1 root" in out
    assert out[-1] == "mismatches: 0"


def test_heldout_is_refused_without_the_flag():
    proc = _run("--split", "heldout")
    assert proc.returncode == 2
    assert "REFUSED" in proc.stderr and proc.stdout == ""
