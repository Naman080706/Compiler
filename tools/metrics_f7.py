"""F7 grounding metric: do explanations cite a real retrieved rule? (PRD F7 acceptance)

Over every root error of every dev corpus program, the agent explains the error with a
scripted FakeLLM (no network). The fake cites, from the prompt's "Reference chunks"
section, the chunk ids it was shown, plus one invented id per reply to exercise the
validation step. Reported:
- % of explanations whose citations include a retrieved rule chunk (target >= 90%);
- the number of returned citations that do not exist in the corpus (must be 0);
- how many invented citations validation dropped.
Only the dev split is read (the held-out split is evaluation-only). Stdlib only.

Usage (from the project root):  python tools/metrics_f7.py
Exit status: 0 when the target is met and no returned citation is non-existent, else 1.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cea.agent import Agent  # noqa: E402
from cea.llm import FakeLLM  # noqa: E402
from cea.pipeline import compile_source  # noqa: E402
from cea.retrieval import load_index, retrieve  # noqa: E402

DEV = ROOT / "tests" / "corpus" / "dev"
BOGUS = "rule:no_such_rule"
TARGET = 90.0
_CHUNK = re.compile(r"^  \[([^\]]+)\]$", re.MULTILINE)


def scripted(messages, schema):
    shown = _CHUNK.findall(messages[1]["content"])
    return json.dumps({"explanation": "Scripted explanation. Second sentence.", "citations": shown[:1] + [BOGUS]})


def measure():
    index = load_index()
    total = grounded = nonexistent = dropped = 0
    for c_path in sorted(DEV.glob("*.c")):
        result = compile_source(c_path.read_text(encoding="utf-8"), c_path.name, engine="cea")
        for cluster in result.clusters:
            record = cluster.root
            exp = Agent(FakeLLM(default=scripted)).explain(record, c_path.read_text(encoding="utf-8"), "short")
            retrieved = {c.id: c for c in retrieve(record, index)}
            total += 1
            dropped += 1 if BOGUS not in exp.citations else 0
            nonexistent += sum(1 for cid in exp.citations if cid not in index.chunks)
            if any(cid in retrieved and retrieved[cid].kind != "fix" for cid in exp.citations):
                grounded += 1
    return total, grounded, nonexistent, dropped


def main():
    total, grounded, nonexistent, dropped = measure()
    pct = 100.0 * grounded / total if total else 0.0
    print(f"F7 metric, split=dev, explanations = {total}")
    print(f"cite a real retrieved rule: {grounded}/{total} = {pct:.1f}% (target >= {TARGET:.0f}%)")
    print(f"non-existent citations: {nonexistent} (must be 0)")
    print(f"invented citations dropped by validation: {dropped}/{total}")
    return 0 if pct >= TARGET and nonexistent == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
