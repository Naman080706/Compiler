"""The gcc fallback: diagnostics for programs outside the course subset (language-spec.md section 7).

``run_gcc(source)`` runs ``gcc -std=c99 -Wall -fsyntax-only -fdiagnostics-format=json`` on the source and
turns every diagnostic into an ``ErrorRecord`` through an ``ErrorSink``: code ``GCC-ERROR``, ``GCC-WARNING``
or ``GCC-NOTE``, gcc's line, column and message, and a ``phase`` guessed from the message
(``guess_phase``). A note is linked to the diagnostic it belongs to with ``caused_by``, so clustering shows it
as a symptom. If the JSON cannot be read the text output (``file:line:col: severity: message``) is parsed
instead. Nothing here prints.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cea.diagnostics import ErrorSink
from cea.records import Position

GCC_ARGS = ["-std=c99", "-Wall", "-fsyntax-only", "-fdiagnostics-format=json"]
TIMEOUT_SECONDS = 30
SOURCE_NAME = "input.c"
GCC_MISSING_NOTE = ("gcc is not installed (or not on PATH) on this machine, so the gcc fallback could not run; "
                    "showing the course compiler's own result instead.")

_QUOTED = re.compile(r"[‘'\"]([^’'\"]{1,60})[’'\"]")
_TEXT_DIAG = re.compile(r"^(?P<file>.*?):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?P<kind>fatal error|error|warning|note):\s*(?P<msg>.*)$")
_LEXICAL = re.compile(
    r"stray|unterminated|missing terminating|empty character constant|invalid suffix|invalid digit|"
    r"unknown escape sequence|invalid character|exponent has no digits|hex escape|"
    r"character constant too long|multi-character character constant|invalid preprocessing number|"
    r"missing binary operator before token|extra tokens at end", re.I)
_SYNTAX = re.compile(
    r"^expected\b|parse error|before ['‘\"].*['’\"] token|at end of input|unbalanced|"
    r"unknown type name|invalid preprocessing directive|#include expects|#include_next|"
    r"unterminated #|#[a-z]+ without|no include path|macro .* requires|macro .* passed|"
    r"invalid directive|empty filename in #include|syntax error|expected declaration|"
    r"unexpected|stray '", re.I)


def gcc_path() -> str | None:
    """The gcc executable on PATH, or None."""
    return shutil.which("gcc")


def gcc_available() -> bool:
    return gcc_path() is not None


def guess_phase(message: str) -> str:
    """Guess lexical / syntax / semantic from gcc's message text (heuristic of language-spec.md section 7)."""
    if _LEXICAL.search(message):
        return "lexical"
    if _SYNTAX.search(message):
        return "syntax"
    return "semantic"


@dataclass
class Diagnostic:
    kind: str                      # "error" | "warning" | "note"
    message: str
    line: int
    column: int
    end_line: int
    end_column: int
    children: list["Diagnostic"]


def _kind(raw: str) -> str:
    raw = (raw or "").lower()
    if raw in ("warning", "note"):
        return raw
    return "error"                 # error, fatal error, sorry, internal compiler error, ...


def _location(entry: dict) -> tuple[int, int, int, int]:
    locs = entry.get("locations") or []
    if not locs:
        return 1, 1, 1, 1
    first = locs[0]
    caret = first.get("caret") or {}
    line = int(caret.get("line", 1) or 1)
    col = int(caret.get("byte-column", caret.get("column", 1)) or 1)
    finish = first.get("finish") or {}
    end_line = int(finish.get("line", line) or line)
    end_col = int(finish.get("byte-column", finish.get("column", col)) or col)
    if (end_line, end_col) < (line, col):
        end_line, end_col = line, col
    return max(line, 1), max(col, 1), max(end_line, 1), max(end_col, 1)


def _from_json(entry: dict) -> Diagnostic:
    line, col, end_line, end_col = _location(entry)
    return Diagnostic(_kind(entry.get("kind", "error")), str(entry.get("message", "")), line, col, end_line, end_col,
                      [_from_json(c) for c in entry.get("children") or []])


def parse_json(text: str) -> list[Diagnostic] | None:
    """Diagnostics from gcc's JSON output, or None when the text is not (only) that JSON."""
    start = text.find("[")
    if start < 0:
        return [] if not text.strip() else None
    try:
        data = json.loads(text[start:])
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    return [_from_json(e) for e in data if isinstance(e, dict)]


def parse_text(text: str) -> list[Diagnostic]:
    """Diagnostics from gcc's plain-text output (used only if the JSON could not be read)."""
    out: list[Diagnostic] = []
    for raw in text.splitlines():
        m = _TEXT_DIAG.match(raw.strip())
        if not m:
            continue
        line, col = int(m["line"]), int(m["col"] or 1)
        out.append(Diagnostic(_kind(m["kind"]), m["msg"], line, col, line, col, []))
    return out


def run_gcc_raw(source: str) -> list[Diagnostic] | None:
    """Run gcc on ``source``; None if gcc is missing, otherwise its diagnostics in order."""
    gcc = gcc_path()
    if gcc is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / SOURCE_NAME
        path.write_text(source, encoding="utf-8", newline="")
        try:
            proc = subprocess.run([gcc, *GCC_ARGS, path.name], cwd=tmp, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            return None
    text = proc.stderr or ""
    parsed = parse_json(text)
    return parsed if parsed is not None else parse_text(text)


def _found(message: str) -> str:
    m = _QUOTED.search(message)
    return m.group(1) if m else ""


def _code(kind: str) -> str:
    return {"error": "GCC-ERROR", "warning": "GCC-WARNING", "note": "GCC-NOTE"}[kind]


def report_all(diags: list[Diagnostic], sink: ErrorSink) -> None:
    """Turn diagnostics into records. Notes get ``caused_by`` = the diagnostic they follow."""
    parent_id: str | None = None

    def emit(d: Diagnostic, cause: str | None) -> str:
        phase = guess_phase(d.message)
        rec = sink.report(_code(d.kind), d.line, d.column, found=_found(d.message),
                          span_end=Position(d.end_line, d.end_column), caused_by=cause, phase=phase,
                          gcc_message=d.message)
        return rec.id

    for d in diags:
        if d.kind == "note":
            emit(d, parent_id)
        else:
            parent_id = emit(d, None)
        for child in d.children:
            emit(child, parent_id)


def run_gcc(source: str, sink: ErrorSink) -> bool:
    """Fill ``sink`` with gcc's diagnostics for ``source``. False (and nothing reported) if gcc cannot run."""
    diags = run_gcc_raw(source)
    if diags is None:
        return False
    report_all(diags, sink)
    return True
