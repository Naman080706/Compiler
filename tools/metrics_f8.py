"""F8 metric: what share of fixable errors get a VERIFIED patch within 3 attempts? (PRD F8 acceptance: >= 80%)

Units: every dev corpus program whose sidecar says ``"fixable": true`` and that has at least one
fatal root; the unit is that program's first fatal root cluster (by line and column). Each unit
runs ``cea.verifier.verify_fix`` (3 attempts, 10 s budget). Only the dev split is read.

LLM choice (``--llm``):
- ``oracle`` (default): a FakeLLM that replies with the known fix from tools/f8_oracle_fixes.json.
  It exists ONLY to test the pipeline (prompt, patch application, compile, guardrails). The fixes
  were found by an automated search over the compiler plus hand-written entries, so the number it
  prints says nothing about a real model.
- ``env``: the real LLM from ``cea.llm.client_from_env()`` (CEA_LLM_* variables or .env). Only this
  gives numbers for the PRD's 80% target.

Usage (from the project root):  python tools/metrics_f8.py [--llm oracle|env] [--verbose]
Exit status: 0 when the share is >= 80%, else 1.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cea.agent import Agent  # noqa: E402
from cea.llm import FakeLLM, LLMError, client_from_env  # noqa: E402
from cea.pipeline import compile_source  # noqa: E402
from cea.verifier import MAX_ATTEMPTS, verify_fix  # noqa: E402

DEV = ROOT / "tests" / "corpus" / "dev"
ORACLE = ROOT / "tools" / "f8_oracle_fixes.json"
TARGET = 80.0


def units():
    """(file name, source, first fatal root record) for every fixable dev program with a fatal root."""
    for side in sorted(DEV.glob("*.expected.json")):
        if not json.loads(side.read_text(encoding="utf-8"))["fixable"]:
            continue
        c_path = side.with_name(side.name[: -len(".expected.json")] + ".c")
        source = c_path.read_text(encoding="utf-8")
        fatal = [c.root for c in compile_source(source, c_path.name, engine="cea").clusters if c.root.severity == "fatal"]
        if fatal:
            yield c_path.name, source, fatal[0]


def oracle_llm(fix: dict | None) -> FakeLLM:
    if fix is None:
        return FakeLLM()                                     # no known fix: every call fails
    return FakeLLM(default=json.dumps(fix))


def measure(mode: str, verbose: bool = False):
    known = json.loads(ORACLE.read_text(encoding="utf-8")) if mode == "oracle" else {}
    total = verified = 0
    attempts = []
    failures = []
    for name, source, record in units():
        total += 1
        llm = oracle_llm(known.get(name)) if mode == "oracle" else client_from_env()
        try:
            fix = verify_fix(Agent(llm), record, source, max_attempts=MAX_ATTEMPTS)
        except LLMError as exc:
            failures.append((name, f"LLM error: {exc}"))
            continue
        if fix.verified:
            verified += 1
            attempts.append(fix.attempts)
        else:
            failures.append((name, fix.reason))
    return total, verified, attempts, failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--llm", choices=("oracle", "env"), default="oracle")
    ap.add_argument("--verbose", action="store_true", help="list every unit that got no verified fix, with the reason")
    args = ap.parse_args(argv)
    if args.llm == "env":
        try:
            client_from_env()
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    total, verified, attempts, failures = measure(args.llm)
    pct = 100.0 * verified / total if total else 0.0
    print(f"F8 metric, split=dev, fixable roots = {total}, LLM = {args.llm}")
    print(f"verified within {MAX_ATTEMPTS} attempts: {verified}/{total} = {pct:.1f}% (target >= {TARGET:.0f}%)")
    if attempts:
        print("attempts used by verified fixes: " + ", ".join(
            f"{n} attempt(s): {attempts.count(n)}" for n in sorted(set(attempts))))
    if args.llm == "oracle":
        print("NOTE: oracle mode replays known fixes through a FakeLLM. It tests the pipeline only; "
              "REAL numbers need a real LLM (run with --llm env).")
    for name, why in failures if args.verbose else []:
        print(f"  no verified fix: {name}: {why}")
    return 0 if pct >= TARGET else 1


if __name__ == "__main__":
    sys.exit(main())
