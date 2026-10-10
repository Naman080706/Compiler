"""Command-line interface: ``python -m cea FILE.c [--json]`` (plan 007).

This is the only module allowed to print (plans/m1-architecture.md §1, PRD F1).
Exit status: 0 when the file compiles (no fatal record, PRD F4), 1 when at
least one record is fatal, 2 for a usage error or an unreadable file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cea.pipeline import compile_source
from cea.records import ErrorRecord


def format_record(filename: str, rec: ErrorRecord) -> str:
    """One human-readable line, e.g. ``E-0002 t.c:5:22: fatal [SYN-MISSING-SEMICOLON] Expected ';' ...``."""
    text = f"{rec.id} {filename}:{rec.line}:{rec.column}: {rec.severity} [{rec.code}] {rec.message}"
    if rec.caused_by:
        text += f" (caused by {rec.caused_by})"
    return text


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # never crash on a console that cannot show a character
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(prog="python -m cea", description="Compile a C-subset file and report its errors.")
    ap.add_argument("file", help="path to a .c file")
    ap.add_argument("--json", action="store_true", help="print the error records as JSON")
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
                   "errors": [r.to_dict() for r in result.errors]}
        print(json.dumps(payload, indent=2))
    else:
        for rec in result.errors:
            print(format_record(path.name, rec))
        print(result.summary())
    return 0 if result.ok else 1
