"""cea.runner: gcc-builds and runs a program. Skipped when gcc is not installed."""
import pytest

from cea.gcc_fallback import gcc_available
from cea.runner import run_program

pytestmark = pytest.mark.skipif(not gcc_available(), reason="gcc is not installed")

HELLO = '#include <stdio.h>\nint main(void) {\n    printf("sum = %d\\n", 2 + 3);\n    return 0;\n}\n'
BAD = "int main(void) {\n    return undefined_name;\n}\n"
LOOP = "int main(void) {\n    while (1) {}\n    return 0;\n}\n"
EXITCODE = "int main(void) {\n    return 7;\n}\n"


def test_runs_a_program_and_captures_its_stdout():
    r = run_program(HELLO)
    assert r.gcc_available and r.compiled
    assert r.stdout == "sum = 5\n" and r.exit_code == 0 and not r.timed_out


def test_reports_a_build_failure_instead_of_running():
    r = run_program(BAD)
    assert r.compiled is False and r.stdout == "" and r.compile_output
    assert "undefined_name" in r.compile_output


def test_returns_the_program_exit_code():
    assert run_program(EXITCODE).exit_code == 7


def test_an_infinite_loop_times_out_and_is_killed():
    r = run_program(LOOP, timeout=1.5)
    assert r.compiled is True and r.timed_out is True
