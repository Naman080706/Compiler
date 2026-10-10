"""Cross-check tests/corpus against gcc (plan 003). Stdlib only.

For every tests/corpus/<split>/*.c this runs
    gcc -std=c99 -pedantic-errors -fsyntax-only <file>
and checks two things:
  1. The design rule "accepted => valid C99": a program whose sidecar has
     empty "roots" (all of valid/, plus warning-only faulty programs) MUST be
     accepted by gcc (exit code 0).
  2. The sidecar's "gcc_rejects" equals what gcc actually did.
It prints a summary and exits 1 on any mismatch, otherwise 0.
If gcc is not on PATH it prints a skip message and exits 0.

Usage: python -I tools/gcc_check.py [corpus_dir]     (default: tests/corpus)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLITS = ("dev", "heldout", "valid")
GCC_ARGS = ["-std=c99", "-pedantic-errors", "-fsyntax-only"]


def main(argv):
    gcc = shutil.which("gcc")
    if gcc is None:
        print("SKIP: gcc not found on PATH; corpus not cross-checked")
        return 0
    corpus = Path(argv[1]) if len(argv) > 1 else ROOT / "tests" / "corpus"
    problems, checked, rejected = [], 0, 0
    for split in SPLITS:
        for c_path in sorted((corpus / split).glob("*.c")):
            rel = f"{split}/{c_path.name}"
            side_path = c_path.with_name(c_path.stem + ".expected.json")
            if not side_path.exists():
                problems.append(f"{rel}: missing sidecar {side_path.name}")
                continue
            side = json.loads(side_path.read_text(encoding="utf-8"))
            proc = subprocess.run([gcc, *GCC_ARGS, str(c_path)],
                                  capture_output=True, text=True, timeout=60)
            gcc_rejects = proc.returncode != 0
            checked += 1
            rejected += gcc_rejects
            first = next((ln for ln in proc.stderr.splitlines() if "error" in ln), "")
            if not side.get("roots") and gcc_rejects:
                problems.append(f"{rel}: no expected roots but gcc REJECTS it "
                                f"(breaks 'accepted => valid C99'): {first}")
            if side.get("gcc_rejects") != gcc_rejects:
                verdict = "rejects" if gcc_rejects else "accepts"
                problems.append(f"{rel}: sidecar gcc_rejects={side.get('gcc_rejects')} "
                                f"but gcc {verdict} it {first}".rstrip())
    for p in problems:
        print("MISMATCH:", p)
    print(f"gcc_check: {checked} files checked, {rejected} rejected by gcc, "
          f"{checked - rejected} accepted, {len(problems)} mismatches")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
