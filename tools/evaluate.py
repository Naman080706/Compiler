"""Milestone 5: run every PRD success metric on the held-out split (and dev, for comparison).

Metrics (PRD "Success metrics"; definitions in docs/evaluation/report.md):
- F2 error reduction: raw vs displayed errors over the cascade set. Reported for single-fault cascading
  files (the metric the >= 70% target applies to, plans/README.md) and for all cascading files.
- root-cause accuracy: displayed cluster roots vs sidecar roots+warnings, exact (code, line).
- F8 verified-fix rate within 3 attempts on ``fixable`` programs (unit = first fatal root).
- F7 grounding: share of explanations citing a real retrieved rule chunk, and non-existent citations.
- F3 latency: default (short, beginner) explanation, N requests, no explanation cache, median and p90.

LLM (``--llm``): ``env`` uses cea.llm.client_from_env() (CEA_LLM_* variables / .env; for the local
model: ``CEA_LLM_FALLBACK_MODEL=llama3.1`` with no primary). ``fake`` uses scripted FakeLLMs and
the results are labelled "pipeline-only, not a real-model result".

Usage (from the project root):
    python tools/evaluate.py --i-am-milestone-5 --llm env
    python tools/evaluate.py --llm fake --splits dev --out-dir <dir>      # no network, dev only

The held-out split is read only with ``--i-am-milestone-5``. Corpus files are never written.
Stdlib only. Exit status: 0 on success, 2 on refusal or a usage error.
"""
from __future__ import annotations

import argparse
import datetime
import json
import platform
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cea.agent import Agent  # noqa: E402
from cea.llm import FakeLLM, LLMError, client_from_env  # noqa: E402
from cea.pipeline import compile_source  # noqa: E402
from cea.retrieval import load_index, retrieve  # noqa: E402
from cea.verifier import MAX_ATTEMPTS, verify_fix  # noqa: E402

CORPUS = ROOT / "tests" / "corpus"
ORACLE = ROOT / "tools" / "f8_oracle_fixes.json"
OUT_DIR = ROOT / "docs" / "evaluation"
TARGETS = {"f2": 70.0, "root": 85.0, "f8": 80.0, "f7": 90.0, "latency_s": 5.0}
EVAL_FIX_TIMEOUT = 180.0        # seconds per F8 unit; the product default (10 s) is far below a local 8B model
_CHUNK = re.compile(r"^  \[([^\]]+)\]$", re.MULTILINE)


# ---------------------------------------------------------------- corpus
def programs(split: str):
    """(name, source, sidecar dict) for every program of one split, in name order."""
    out = []
    for c_path in sorted((CORPUS / split).glob("*.c")):
        side = json.loads(c_path.with_name(c_path.stem + ".expected.json").read_text(encoding="utf-8"))
        out.append((c_path.name, c_path.read_text(encoding="utf-8"), side))
    return out


def pct(num: float, den: float) -> float | None:
    return round(100.0 * num / den, 1) if den else None


# ---------------------------------------------------------------- LLM helpers
class Recorder:
    """Wraps an LLM client; remembers the last raw reply (None if the call failed) and call counts."""

    def __init__(self, inner):
        self.inner = inner
        self.last: str | None = None
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        self.last = None
        text = self.inner.complete(messages, **kwargs)
        self.last = text
        return text

    def __repr__(self) -> str:
        return f"Recorder({self.inner!r})"


def fake_explainer(messages, schema):
    """Scripted explanation: cites the first reference chunk it was shown (pipeline test only)."""
    shown = _CHUNK.findall(messages[-1]["content"])
    return json.dumps({"explanation": "Scripted explanation of the error. Second sentence.", "citations": shown[:1]})


def fake_for_f8(name: str, oracle: dict) -> FakeLLM:
    fix = oracle.get(name)
    return FakeLLM(default=json.dumps(fix)) if fix else FakeLLM()


def make_llm(kind: str):
    if kind == "env":
        return client_from_env()
    return FakeLLM(default=fake_explainer)


# ---------------------------------------------------------------- metrics
def metric_f2(progs):
    rows = []
    for name, source, side in progs:
        if not side["cascading"]:
            continue
        res = compile_source(source, name)
        single = len(side["injected_faults"]) == 1
        want = 1 if single else len(side["roots"]) + len(side["warnings"])
        rows.append({"program": name, "raw": len(res.errors), "displayed": len(res.clusters),
                     "expected_displayed": want, "single_fault": single})

    def agg(sel):
        raw, shown = sum(r["raw"] for r in sel), sum(r["displayed"] for r in sel)
        return {"programs": len(sel), "raw": raw, "displayed": shown,
                "reduction_pct": pct(raw - shown, raw),
                "programs_displayed_as_expected": sum(1 for r in sel if r["displayed"] == r["expected_displayed"])}

    return {"single_fault": agg([r for r in rows if r["single_fault"]]), "all_cascade": agg(rows), "rows": rows}


def metric_root(progs):
    rows = []
    for name, source, side in progs:
        res = compile_source(source, name)
        shown = {(c.root.code, c.root.line) for c in res.clusters}
        want = {(r["code"], r["line"]) for r in side["roots"] + side["warnings"]}
        rows.append({"program": name, "displayed": sorted(shown), "expected": sorted(want),
                     "matched": len(shown & want), "n_displayed": len(shown), "n_expected": len(want),
                     "exact": shown == want})
    matched = sum(r["matched"] for r in rows)
    return {"programs": len(rows),
            "program_exact_pct": pct(sum(r["exact"] for r in rows), len(rows)),
            "root_precision_pct": pct(matched, sum(r["n_displayed"] for r in rows)),
            "root_recall_pct": pct(matched, sum(r["n_expected"] for r in rows)),
            "mismatches": [r for r in rows if not r["exact"]], "rows": rows}


def metric_f8(progs, mode: str, llm_kind: str):
    """mode 'oracle': FakeLLM replaying tools/f8_oracle_fixes.json (dev only); 'llm': the configured client."""
    oracle = json.loads(ORACLE.read_text(encoding="utf-8")) if mode == "oracle" else {}
    units, verified, attempts, failures = 0, 0, [], []
    times = []
    for name, source, side in progs:
        if not side["fixable"]:
            continue
        fatal = [c.root for c in compile_source(source, name).clusters if c.root.severity == "fatal"]
        if not fatal:
            continue
        units += 1
        llm = fake_for_f8(name, oracle) if mode == "oracle" else make_llm(llm_kind)
        agent = Agent(llm)                                  # no cache: every attempt is a fresh model call
        print(f"  F8 {name}", file=sys.stderr, flush=True)
        t0 = time.perf_counter()
        try:
            fix = verify_fix(agent, fatal[0], source, max_attempts=MAX_ATTEMPTS, timeout=EVAL_FIX_TIMEOUT)
            elapsed = time.perf_counter() - t0
            ok, reason, used = fix.verified, fix.reason, fix.attempts
        except LLMError as exc:
            elapsed, ok, reason, used = time.perf_counter() - t0, False, f"LLM error: {exc}", 0
        times.append(elapsed)
        if ok:
            verified += 1
            attempts.append(used)
        else:
            failures.append({"program": name, "reason": reason})
    return {"mode": mode, "units": units, "verified": verified, "verified_pct": pct(verified, units),
            "attempts_histogram": {str(n): attempts.count(n) for n in sorted(set(attempts))},
            "median_seconds_per_unit": round(statistics.median(times), 2) if times else None,
            "verified_within_10s_budget": sum(1 for a, t in zip(attempts, times) if t <= 10) if mode == "llm" else None,
            "failures": failures}


def metric_f7(progs, llm_kind: str):
    """Grounding over every displayed root of the split. 'model_cited' = the model itself named a
    retrieved rule chunk; 'attributed' = after Agent.validate_citations (which attributes an explanation
    that cites nothing valid to its own rule chunk)."""
    index = load_index()
    total = model_cited = attributed = nonexistent = fallback = 0
    for name, source, side in progs:
        for cluster in compile_source(source, name).clusters:
            record = cluster.root
            print(f"  F7 {name} {record.code}", file=sys.stderr, flush=True)
            rec = Recorder(make_llm(llm_kind))
            exp = Agent(rec).explain(record, source, "short")
            total += 1
            retrieved = {c.id: c for c in retrieve(record, index)}
            nonexistent += sum(1 for cid in exp.citations if cid not in index.chunks)
            if any(cid in retrieved and retrieved[cid].kind != "fix" for cid in exp.citations):
                attributed += 1
            if rec.last is None:
                fallback += 1                                  # no usable reply: deterministic fallback text
                continue
            try:
                raw = json.loads(rec.last).get("citations", [])
            except (ValueError, AttributeError):
                raw = []
            if any(isinstance(cid, str) and cid in retrieved and retrieved[cid].kind != "fix" for cid in raw):
                model_cited += 1
    return {"explanations": total, "model_cited": model_cited, "model_cited_pct": pct(model_cited, total),
            "attributed": attributed, "attributed_pct": pct(attributed, total),
            "nonexistent_citations": nonexistent, "llm_failed_fallback_used": fallback}


def metric_latency(progs, llm_kind: str, n: int):
    """Time Agent.explain(record, source, 'short') for n requests, cycling over the split's roots.
    No explanation cache is used, so every request is a cold call to the model."""
    records = [(c.root, source) for name, source, _ in progs for c in compile_source(source, name).clusters]
    if not records:
        return {"requests": 0}
    llm = make_llm(llm_kind)
    agent = Agent(llm)
    times, failed = [], 0
    for i in range(n):
        record, source = records[i % len(records)]
        print(f"  latency request {i + 1}/{n}", file=sys.stderr, flush=True)
        t0 = time.perf_counter()
        exp = agent.explain(record, source, "short")
        times.append(time.perf_counter() - t0)
        if exp.text == Agent.fallback_text(record, "short"):
            failed += 1
    ordered = sorted(times)
    p90 = ordered[min(len(ordered) - 1, int(round(0.9 * len(ordered) + 0.5)) - 1)]
    return {"requests": n, "distinct_errors": len(records), "median_s": round(statistics.median(times), 2),
            "p90_s": round(p90, 2), "max_s": round(max(times), 2), "min_s": round(min(times), 2),
            "first_request_s": round(times[0], 2), "median_excl_first_s": round(statistics.median(times[1:]), 2) if n > 1 else None,
            "under_5s_pct": pct(sum(1 for t in times if t < TARGETS["latency_s"]), n),
            "fallback_text_used": failed}


# ---------------------------------------------------------------- driver
def evaluate_split(split: str, llm_kind: str, latency_n: int, log) -> dict:
    progs = programs(split)
    log(f"[{split}] {len(progs)} programs: structural metrics")
    out = {"llm_kind": llm_kind, "programs": len(progs), "f2": metric_f2(progs), "root_accuracy": metric_root(progs)}
    log(f"[{split}] F7 grounding")
    out["f7"] = metric_f7(progs, llm_kind)
    log(f"[{split}] latency x{latency_n}")
    out["latency"] = metric_latency(progs, llm_kind, latency_n)
    log(f"[{split}] F8 verified fixes")
    if llm_kind == "env":
        out["f8"] = metric_f8(progs, "llm", llm_kind)
    elif split == "dev":
        out["f8"] = metric_f8(progs, "oracle", llm_kind)
    else:
        out["f8"] = {"mode": "n/a", "note": "no oracle fixes exist for the held-out split (by design)"}
    if split == "dev" and llm_kind == "env":
        log("[dev] F8 oracle (pipeline-only, for reference)")
        out["f8_oracle"] = metric_f8(progs, "oracle", "fake")
    return out


def _fmt(v, suffix="%") -> str:
    return "n/a" if v is None else f"{v}{suffix}"


def _met(value, target, higher=True) -> str:
    if value is None:
        return "n/a"
    return "met" if (value >= target if higher else value < target) else "NOT MET"


def markdown(res: dict) -> str:
    meta = res["meta"]
    lines = ["# Evaluation results", "",
             f"Generated {meta['date']} by `python tools/evaluate.py` (LLM: {meta['llm_description']}).", ""]
    if any(s["llm_kind"] != "env" for s in res["splits"].values()):
        lines += ["> **PIPELINE-ONLY, NOT A REAL-MODEL RESULT** wherever a split is marked so below: those LLM "
                  "metrics were produced with a scripted FakeLLM. Real run: `CEA_LLM_FALLBACK_MODEL=llama3.1 "
                  "python tools/evaluate.py --i-am-milestone-5 --llm env [--dev-llm env]`.", ""]
    for split in ("heldout", "dev"):
        if split not in res["splits"]:
            continue
        s = res["splits"][split]
        real = s["llm_kind"] == "env"
        f2s, f2a, ra, f7, lat, f8 = (s["f2"]["single_fault"], s["f2"]["all_cascade"], s["root_accuracy"],
                                     s["f7"], s["latency"], s["f8"])
        lines += [f"## {split} ({s['programs']} programs; LLM metrics: "
                  f"{'real model' if real else 'PIPELINE-ONLY, not a real-model result'})", "",
                  "| Metric | Target | Result | Status |", "|---|---|---|---|",
                  f"| Error reduction, single-fault cascading files | >= 70% | {_fmt(f2s['reduction_pct'])} "
                  f"({f2s['raw']} raw -> {f2s['displayed']} shown, {f2s['programs']} files) | "
                  f"{_met(f2s['reduction_pct'], 70)} |",
                  f"| Error reduction, all cascading files (reported, not the target) | - | {_fmt(f2a['reduction_pct'])} "
                  f"({f2a['raw']} raw -> {f2a['displayed']} shown, {f2a['programs']} files) | - |",
                  f"| Root-cause accuracy, program exact match | >= 85% | {_fmt(ra['program_exact_pct'])} | "
                  f"{_met(ra['program_exact_pct'], 85)} |",
                  f"| Root-cause accuracy, root precision / recall | - | {_fmt(ra['root_precision_pct'])} / "
                  f"{_fmt(ra['root_recall_pct'])} | - |"]
        if f8.get("mode") == "n/a":
            lines.append("| Verified-fix rate (3 attempts) | >= 80% | n/a (no oracle for held-out) | n/a |")
        else:
            tag = "" if f8["mode"] == "llm" else " (oracle FakeLLM, pipeline-only)"
            lines.append(f"| Verified-fix rate (3 attempts){tag} | >= 80% | {_fmt(f8['verified_pct'])} "
                         f"({f8['verified']}/{f8['units']}) | {_met(f8['verified_pct'], 80) if f8['mode'] == 'llm' else 'pipeline-only'} |")
        lines += [f"| Grounding, model itself cites a retrieved rule | >= 90% | {_fmt(f7['model_cited_pct'])} "
                  f"({f7['model_cited']}/{f7['explanations']}) | {_met(f7['model_cited_pct'], 90) if real else 'pipeline-only'} |",
                  f"| Grounding, after citation validation | >= 90% | {_fmt(f7['attributed_pct'])} | "
                  f"{_met(f7['attributed_pct'], 90) if real else 'pipeline-only'} |",
                  f"| Non-existent citations | 0 | {f7['nonexistent_citations']} | "
                  f"{'met' if f7['nonexistent_citations'] == 0 else 'NOT MET'} |",
                  f"| Latency, default explanation, median / p90 ({lat.get('requests')} requests) | < 5 s | "
                  f"{lat.get('median_s')} s / {lat.get('p90_s')} s | "
                  f"{_met(lat.get('median_s'), 5, higher=False) if real else 'pipeline-only'} |", ""]
        if "f8_oracle" in s:
            o = s["f8_oracle"]
            lines += [f"Dev F8 with the oracle FakeLLM (pipeline-only): {o['verified']}/{o['units']} = "
                      f"{_fmt(o['verified_pct'])}.", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python tools/evaluate.py", description=__doc__.splitlines()[0])
    ap.add_argument("--llm", choices=("env", "fake"), default="env")
    ap.add_argument("--dev-llm", choices=("env", "fake"), default="fake",
                    help="LLM for the dev split's LLM metrics when --llm env (default fake: a real dev run is slow)")
    ap.add_argument("--splits", default="heldout,dev", help="comma list of: heldout, dev")
    ap.add_argument("--latency-n", type=int, default=50)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--i-am-milestone-5", dest="milestone5", action="store_true",
                    help="required for the heldout split (evaluation only)")
    args = ap.parse_args(argv)
    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    if any(s not in ("dev", "heldout") for s in splits) or not splits:
        print("error: --splits takes dev and/or heldout", file=sys.stderr)
        return 2
    if "heldout" in splits and not args.milestone5:
        print("REFUSED: the heldout split is evaluation-only (tests/corpus/README.md section 5); "
              "pass --i-am-milestone-5 at milestone 5", file=sys.stderr)
        return 2
    desc = "scripted FakeLLM"
    if args.llm == "env":
        try:
            client = client_from_env()
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        desc = repr(client)
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731
    started = time.perf_counter()
    res = {"meta": {"date": datetime.date.today().isoformat(), "llm_kind": args.llm, "llm_description": desc,
                    "latency_requests": args.latency_n, "f8_unit_timeout_s": EVAL_FIX_TIMEOUT,
                    "python": platform.python_version(), "machine": platform.processor() or platform.machine(),
                    "pipeline_only": args.llm != "env"},
           "splits": {}}
    for split in splits:
        res["splits"][split] = evaluate_split(split, args.dev_llm if (split == "dev" and args.llm == "env") else args.llm,
                                          args.latency_n, log)
    res["meta"]["wall_clock_s"] = round(time.perf_counter() - started, 1)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    table = markdown(res)
    (out / "results.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
