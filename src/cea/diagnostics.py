"""ErrorSink: the error interceptor (PRD F1).

It is the only way to create an ErrorRecord. Phase, severity (PRD F4) and the
default rule_ref come from the catalog, never from the caller. Nothing in this
module writes to the console.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from cea.catalog import PRODUCTION, CatalogEntry, load_catalog, load_grammar_rules
from cea.records import ErrorRecord, Position

_NEWLINE = re.compile(r"\r\n|\r|\n")
ZERO_WIDTH_CODE = "SYN-MISSING-SEMICOLON"   # reported just after the last token, so zero-width


def split_lines(source: str) -> list[str]:
    """Split on CRLF, CR or LF (the lexer's newline rule). A final newline adds no line."""
    lines = _NEWLINE.split(source)
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return lines


def render_expected(template: str, expected: Sequence[str], phase: str) -> str:
    """Join items with " or ".

    Only syntax codes quote each item, and only when the template does not
    already write '{expected}'. Lexical and semantic items (type names, counts)
    are inserted raw: "expects 2 argument(s)", not "expects '2' argument(s)".
    """
    if phase != "syntax" or "'{expected}'" in template:
        return " or ".join(expected)
    return " or ".join(f"'{item}'" for item in expected)


class ErrorSink:
    """Collects ErrorRecords in creation order. Ids are E-0001, E-0002, ..."""

    def __init__(self, source: str, catalog: dict[str, CatalogEntry] | None = None):
        self._lines = split_lines(source)
        self._catalog = catalog if catalog is not None else load_catalog()
        self._records: list[ErrorRecord] = []

    def report(self, code: str, line: int, column: int, *,
               found: str,
               expected: Sequence[str] = (),
               span_end: Position | None = None,
               caused_by: str | None = None,
               rule_ref: str | None = None,
               phase: str | None = None,
               **message_args: object) -> ErrorRecord:
        entry = self._catalog[code]                      # unknown code -> KeyError
        if isinstance(expected, str):
            raise TypeError("expected must be a sequence of strings, not one str")
        if line < 1 or column < 1:
            raise ValueError(f"positions are 1-based, got {line}:{column}")
        if rule_ref is None:
            if entry.rule_ref == PRODUCTION:
                raise ValueError(f"{code} needs a rule_ref argument (catalog rule_ref is {PRODUCTION})")
            rule_ref = entry.rule_ref
        elif rule_ref not in load_grammar_rules():
            raise ValueError(f"rule_ref {rule_ref!r} is not a rule of docs/language-spec.md section 2")
        expected_list = list(expected)
        # Strict formatting: a placeholder with no value raises KeyError (a programming error).
        message = entry.message_template.format(
            found=found,
            expected=render_expected(entry.message_template, expected_list, entry.phase),
            **message_args,
        )
        if span_end is None:
            if found == "EOF" or code == ZERO_WIDTH_CODE:
                span_end = Position(line, column)          # zero-width (error-recovery section 8)
            else:
                span_end = Position(line, column + max(len(found), 1) - 1)
        rec_id = f"E-{len(self._records) + 1:04d}"
        record = ErrorRecord(
            id=rec_id, phase=phase or entry.phase, code=code, severity=entry.severity,
            line=line, column=column, found=found, expected=expected_list,
            snippet=self._snippet(line), root_id=rec_id, rule_ref=rule_ref,
            language="c", caused_by=caused_by, span_end=span_end, message=message,
        )
        self._records.append(record)
        return record

    def _snippet(self, line: int) -> str:
        lo = max(1, line - 1)
        hi = min(len(self._lines), line + 1)
        return "\n".join(self._lines[lo - 1:hi])

    @property
    def records(self) -> list[ErrorRecord]:
        """A copy of the records, in creation order."""
        return list(self._records)

    def summary(self) -> str:
        """PRD F4 count line, e.g. "2 fatal, 3 warnings" / "1 fatal, 1 warning"."""
        fatal = sum(1 for r in self._records if r.severity == "fatal")
        warnings = sum(1 for r in self._records if r.severity == "warning" and r.code != "GCC-NOTE")   # notes explain, they do not count
        return f"{fatal} fatal, {warnings} warning{'' if warnings == 1 else 's'}"
