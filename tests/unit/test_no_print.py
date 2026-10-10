"""PRD F1: "No phase may print directly to the console" (plan 005, step 7).

Only src/cea/cli.py (plan 007) may call print( or write to sys.stdout / sys.stderr.
Every other module reports through cea.diagnostics.ErrorSink.
"""
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "src" / "cea"
ALLOWED = {"cli.py"}
FORBIDDEN = re.compile(r"\bprint\s*\(|\bsys\.(stdout|stderr)\b")
FOUNDATION = {"__init__.py", "catalog.py", "records.py", "diagnostics.py", "tokens.py", "lexer.py"}


def test_foundation_modules_exist():
    assert FOUNDATION <= {p.name for p in PKG.glob("*.py")}


def test_no_module_except_cli_prints():
    offenders = []
    for path in sorted(PKG.glob("*.py")):
        if path.name in ALLOWED:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "console output outside cli.py:\n" + "\n".join(offenders)


def test_the_check_catches_a_print():
    assert FORBIDDEN.search('    print("debug")')
    assert FORBIDDEN.search("sys.stderr.write('x')")
    assert not FORBIDDEN.search('printf("%d", x)  # a C call inside a docstring')
