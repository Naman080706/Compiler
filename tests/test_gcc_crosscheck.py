"""Runs tools/gcc_check.py: the corpus against gcc -std=c99 -pedantic-errors (plan 003)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.gcc
@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not on PATH")
def test_gcc_agrees_with_sidecars():
    proc = subprocess.run(
        [sys.executable, "-I", str(ROOT / "tools" / "gcc_check.py")],
        capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
