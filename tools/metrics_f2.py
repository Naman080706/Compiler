"""F2 clustering metric: raw vs displayed error counts over the cascade set (plan 009).

The cascade set is the corpus programs whose sidecar has ``"cascading": true``
(plans/README.md, "F2 metric definition"). For each one this prints the raw
record count, the displayed count (number of F2 roots = clusters) and the
expected displayed count, then the totals and the reduction. Expected
displayed is 1 for a single-fault file (plan 002 section 10, part (b)); for a
multi-fault file it is every expected F2 root: the sidecar ``roots`` plus the
sidecar ``warnings`` (a warning with no cause is its own root). Stdlib only.

Usage (from the project root):
    python tools/metrics_f2.py                       # dev split (default)
    python tools/metrics_f2.py --split heldout --i-am-milestone-5

The held-out split is evaluation-only (tests/corpus/README.md section 5): without
``--i-am-milestone-5`` this script refuses before reading any held-out file.
Exit status: 0 on success, 2 on refusal or a usage error.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cea.pipeline import compile_source  # noqa: E402

CORPUS = ROOT / "tests" / "corpus"


def measure(split):
    """Rows (name, raw, displayed, expected_displayed, single_fault) for the cascade set of one split."""
    rows = []
    for c_path in sorted((CORPUS / split).glob("*.c")):
        side = json.loads(c_path.with_name(c_path.stem + ".expected.json").read_text(encoding="utf-8"))
        if not side["cascading"]:
            continue
        result = compile_source(c_path.read_text(encoding="utf-8"), c_path.name, engine="cea")
        single = len(side["injected_faults"]) == 1
        expected = 1 if single else len(side["roots"]) + len(side["warnings"])
        rows.append((c_path.name, len(result.errors), len(result.clusters), expected, single))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python tools/metrics_f2.py", description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=("dev", "heldout"), default="dev")
    ap.add_argument("--i-am-milestone-5", dest="milestone5", action="store_true",
                    help="required for --split heldout (evaluation only)")
    args = ap.parse_args(argv)
    if args.split == "heldout" and not args.milestone5:
        print("REFUSED: the heldout split is evaluation-only (tests/corpus/README.md section 5); "
              "pass --i-am-milestone-5 at milestone 5", file=sys.stderr)
        return 2
    rows = measure(args.split)
    print(f"F2 metric, split={args.split}, cascade set = {len(rows)} programs")
    print(f"{'program':<48} {'raw':>4} {'shown':>5} {'want':>4}  check")
    for name, raw, shown, want, single in rows:
        print(f"{name:<48} {raw:>4} {shown:>5} {want:>4}  {'ok' if shown == want else 'MISMATCH'}")
    raw_total = sum(r[1] for r in rows)
    shown_total = sum(r[2] for r in rows)
    single_rows = [r for r in rows if r[4]]
    single_ok = sum(1 for r in single_rows if r[2] == 1)
    reduction = 100.0 * (raw_total - shown_total) / raw_total if raw_total else 0.0
    print(f"TOTAL raw={raw_total} displayed={shown_total} reduction={reduction:.1f}%")
    single_raw = sum(r[1] for r in single_rows)
    single_shown = sum(r[2] for r in single_rows)
    single_red = 100.0 * (single_raw - single_shown) / single_raw if single_raw else 0.0
    print(f"SINGLE-FAULT raw={single_raw} displayed={single_shown} reduction={single_red:.1f}%")
    print(f"part (b): {single_ok}/{len(single_rows)} single-fault programs display exactly 1 root")
    mismatches = sum(1 for r in rows if r[2] != r[3])
    print(f"mismatches: {mismatches}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
