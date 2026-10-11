"""Command-line interface: ``python -m cea FILE.c [--json] [--all]`` (plans 007, 009).

This is the only module allowed to print (plans/m1-architecture.md §1, PRD F1).
By default it shows one line per F2 root cause, with a "+N related" count of
the symptoms grouped under it (plan 009). ``--all`` lists every record.
``--json`` prints every record plus a ``clusters`` array.
Exit status: 0 when the file compiles (no fatal record, PRD F4), 1 when at
least one record is fatal, 2 for a usage error or an unreadable file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cea.cluster import Cluster
from cea.pipeline import compile_source
from cea.records import ErrorRecord


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


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # never crash on a console that cannot show a character
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(prog="python -m cea", description="Compile a C-subset file and report its errors.")
    ap.add_argument("file", help="path to a .c file")
    ap.add_argument("--json", action="store_true", help="print the error records and clusters as JSON")
    ap.add_argument("--all", action="store_true", help="list every record, not just one root per cluster")
    args = ap.parse_args(argv)
    path = Path(args.file)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    result = compile_source(source, path.name)
    if args.json:
        payload = {"file": path.name, "ok": result.ok, "summary": result.summary(),
                   "errors": [r.to_dict() for r in result.errors],
                   "clusters": [{"root_id": c.root.id, "symptom_ids": [s.id for s in c.symptoms]}
                                for c in result.clusters]}
        print(json.dumps(payload, indent=2))
    else:
        if args.all:
            for rec in result.errors:
                print(format_record(path.name, rec))
        else:
            for cluster in result.clusters:
                print(format_cluster(path.name, cluster))
        print(result.summary())
    return 0 if result.ok else 1
