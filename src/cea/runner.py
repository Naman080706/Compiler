"""Compile the source with gcc and run it, capturing the program's output (the "Run" feature).

This is the ONE place the system executes student code — everything else is static
analysis and never runs anything. gcc builds a real executable in a throwaway temp
directory; the program then runs with:

- no stdin (``stdin`` is /dev/null), so it can never block waiting for input;
- a wall-clock timeout (``RUN_TIMEOUT``), after which the process is killed, so an
  infinite loop cannot hang the server;
- an output-size cap (``MAX_OUTPUT_BYTES``), so a runaway ``printf`` cannot exhaust memory.

The temp directory (source and executable) is deleted when the call returns. This runs
the student's own program locally for a teaching tool; it is not a hardened sandbox.
Nothing here prints.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cea.gcc_fallback import gcc_path

RUN_TIMEOUT = 5.0                 # seconds of wall-clock for the program itself
BUILD_TIMEOUT = 30.0              # seconds for gcc to build it
MAX_OUTPUT_BYTES = 64 * 1024      # cap on captured stdout / stderr
SOURCE_NAME = "input.c"
EXE_NAME = "program.exe" if os.name == "nt" else "program"
# -w: warnings are already shown by /api/compile; -lm: link the math library (sqrt, pow, ...).
BUILD_ARGS = ["-std=c99", "-O0", "-w"]


@dataclass
class RunResult:
    gcc_available: bool
    compiled: bool
    compile_output: str           # gcc's message when the build failed
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool
    truncated: bool

    def to_dict(self) -> dict:
        return {
            "gcc_available": self.gcc_available, "compiled": self.compiled,
            "compile_output": self.compile_output, "stdout": self.stdout, "stderr": self.stderr,
            "exit_code": self.exit_code, "timed_out": self.timed_out, "truncated": self.truncated,
        }


def _cap(text: str | None) -> tuple[str, bool]:
    text = text or ""
    data = text.encode("utf-8", "replace")
    if len(data) > MAX_OUTPUT_BYTES:
        return data[:MAX_OUTPUT_BYTES].decode("utf-8", "ignore") + "\n...(output truncated)", True
    return text, False


def run_program(source: str, *, timeout: float = RUN_TIMEOUT) -> RunResult:
    """Build ``source`` with gcc and run the result, returning its captured output."""
    gcc = gcc_path()
    if gcc is None:
        return RunResult(False, False, "", "", "", None, False, False)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / SOURCE_NAME
        src.write_text(source, encoding="utf-8", newline="")
        exe = Path(tmp) / EXE_NAME
        try:
            build = subprocess.run([gcc, *BUILD_ARGS, src.name, "-o", exe.name, "-lm"], cwd=tmp,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=BUILD_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return RunResult(True, False, f"the program could not be built: {exc}", "", "", None, False, False)
        if build.returncode != 0 or not exe.exists():
            return RunResult(True, False, build.stderr or build.stdout or "compilation failed", "", "", None, False, False)
        try:
            proc = subprocess.run([str(exe)], cwd=tmp, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            out, t1 = _cap(exc.stdout if isinstance(exc.stdout, str) else "")
            err, _ = _cap(exc.stderr if isinstance(exc.stderr, str) else "")
            return RunResult(True, True, "", out, err, None, True, t1)
        except OSError as exc:
            return RunResult(True, True, "", "", f"the program could not be run: {exc}", None, False, False)
        out, t1 = _cap(proc.stdout)
        err, t2 = _cap(proc.stderr)
        return RunResult(True, True, "", out, err, proc.returncode, False, t1 or t2)
