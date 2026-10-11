"""Command-line interface: ``python -m cea FILE.c [--json] [--all] [--explain [short|expand]] [--fix]``.

This is the only module allowed to print (plans/m1-architecture.md §1, PRD F1).
By default it shows one line per F2 root cause, with a "+N related" count of
the symptoms grouped under it (plan 009). ``--all`` lists every record.
``--json`` prints every record plus a ``clusters`` array.
``--explain`` and ``--fix`` (plan 011, PRD F3) ask the AI agent about every
root: an explanation (``short`` by default, or ``expand``) and/or a suggested
fix. A fix (PRD F8) is shown only when ``cea.verifier`` re-compiled the patch and
accepted it: a unified diff under a Verified header; otherwise the line
"No verified fix found; see explanation". The LLM comes from
``cea.llm.client_from_env()``; ``--no-cache`` skips the explanation cache.
``--engine`` picks the compiler: ``auto`` (default) uses ours and falls back to gcc for programs that use a
feature outside the course subset (``cea.gcc_fallback``), ``cea`` never uses gcc, ``gcc`` always does.
Exit status: 0 when the file compiles (no fatal record, PRD F4), 1 when at
least one record is fatal, 2 for a usage error, an unreadable file, or
``--explain``/``--fix`` with no LLM configured.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from cea.agent import Agent
from cea.cluster import Cluster
from cea.llm import ExplanationCache, LLMError, client_from_env
from cea.pipeline import compile_source
from cea.records import ErrorRecord
from cea.verifier import verify_fix

VERIFIED_HEADER = "--- Verified fix (re-compiled: the error is gone, no new fatal error) ---"
NO_FIX_TEXT = "No verified fix found; see explanation"


def fix_payload(fix) -> dict:
    """JSON-ready verified-fix result; an unverified fix never carries a diff or patched source."""
    return {"diff": fix.diff if fix.verified else "", "patched_source": fix.patched_source if fix.verified else "",
            "verified": bool(fix.verified), "attempts": fix.attempts, "reason": fix.reason}


def format_record(filename: str, rec: ErrorRecord) -> str:
    """One human-readable line, e.g. ``E-0002 t.c:5:22: fatal [SYN-MISSING-SEMICOLON] Expected ';' ...``."""
    text = f"{rec.id} {filename}:{rec.line}:{rec.column}: {rec.severity} [{rec.code}] {rec.message}"
    if rec.caused_by:
        text += f" (caused by {rec.caused_by})"
    return text


def format_cluster(filename: str, cluster: Cluster) -> str:
    """The root's line, plus `` (+N related)`` when the cluster has symptoms."""
    text = format_record(filename, cluster.root)
    if cluster.symptoms:
        text += f" (+{len(cluster.symptoms)} related)"
    return text


def _indent(text: str, prefix: str = "    ") -> list[str]:
    return [prefix + line for line in text.splitlines()]


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # never crash on a console that cannot show a character
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(prog="python -m cea", description="Compile a C-subset file and report its errors.")
    ap.add_argument("file", help="path to a .c file")
    ap.add_argument("--engine", choices=("auto", "cea", "gcc"), default="auto",
                    help="auto: our compiler, falling back to gcc for features outside the course subset; "
                         "cea: never use gcc; gcc: always use gcc")
    ap.add_argument("--json", action="store_true", help="print the error records and clusters as JSON")
    ap.add_argument("--all", action="store_true", help="list every record, not just one root per cluster")
    ap.add_argument("--explain", nargs="?", const="short", choices=("short", "expand"),
                    help="AI explanation of every root error (default: short)")
    ap.add_argument("--fix", action="store_true", help="verified AI fix (diff) for every root error, or a note that none was found")
    ap.add_argument("--no-cache", action="store_true", help="do not read or write the explanation cache")
    args = ap.parse_args(argv)
    if args.all and (args.explain or args.fix):
        ap.error("--all cannot be combined with --explain or --fix (the agent explains roots only)")
    path = Path(args.file)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    result = compile_source(source, path.name, engine=args.engine)
    agent = None
    if args.explain or args.fix:
        try:
            llm = client_from_env()
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        agent = Agent(llm, cache=None if args.no_cache else ExplanationCache())
    if args.json:
        payload = {"file": path.name, "ok": result.ok, "summary": result.summary(),
                   "engine": result.engine, "engine_note": result.engine_note,
                   "errors": [r.to_dict() for r in result.errors],
                   "clusters": [{"root_id": c.root.id, "symptom_ids": [s.id for s in c.symptoms]}
                                for c in result.clusters]}
        if agent is not None:
            payload["agent"] = [
                {"root_id": c.root.id,
                 "explanation": dataclasses.asdict(agent.explain(c.root, source, args.explain))
                 if args.explain else None,
                 "fix": fix_payload(verify_fix(agent, c.root, source)) if args.fix else None}
                for c in result.clusters]
        print(json.dumps(payload, indent=2))
    else:
        if result.engine_note:
            print(f"note: {result.engine_note}")
        if args.all:
            for rec in result.errors:
                print(format_record(path.name, rec))
        else:
            for cluster in result.clusters:
                print(format_cluster(path.name, cluster))
                if agent is None:
                    continue
                if args.explain:
                    exp = agent.explain(cluster.root, source, args.explain)
                    print(f"    Explanation ({exp.mode}, rule {exp.cited_rule or exp.rule_ref}):")
                    print("\n".join(_indent(exp.text, "      ")))
                if args.fix:
                    fix = verify_fix(agent, cluster.root, source)
                    if fix.verified:
                        print("    " + VERIFIED_HEADER)
                        print("\n".join(_indent(fix.diff)))
                    else:
                        print("    " + NO_FIX_TEXT)
        print(result.summary())
    return 0 if result.ok else 1
