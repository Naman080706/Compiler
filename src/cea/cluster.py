"""F2 error clustering: assign each record's root_id and group symptoms under roots (plan 009).

The rule is the provisional root rule of docs/error-recovery.md section 7, made
final by plans/m2-architecture.md section 2. In id order:

1. ``caused_by`` is set -> ``root_id`` = the ``root_id`` of ``caused_by``.
2. SEM-UNDECLARED-VAR / SEM-UNDECLARED-FUNC whose name (``found``) matches an
   earlier record with the same code in the same function body (or both at
   file scope) -> that record's ``root_id`` (PRD: "an undeclared variable
   groups all its later uses").
3. Otherwise -> ``root_id`` = ``id``.

The PRD's "same statement or block" rule is applied ONLY through caused_by
(R1/R2/R9); there is deliberately no block-wide merging. Nothing here prints.
"""
from __future__ import annotations

from dataclasses import dataclass

from cea import ast as A
from cea.records import ErrorRecord

UNDECLARED_CODES = ("SEM-UNDECLARED-VAR", "SEM-UNDECLARED-FUNC")


@dataclass
class Cluster:
    root: ErrorRecord
    symptoms: list[ErrorRecord]          # same root_id, excluding the root, id order


def _id_order(rec: ErrorRecord) -> int:
    """Numeric part of "E-0012" (ids are numbered in creation order)."""
    return int(rec.id.split("-")[1])


def _function_spans(program: A.Program | None) -> list[tuple[str, A.Span]]:
    """(name, span) of every function definition that has a body, in source order."""
    if program is None:
        return []
    return [(d.name, d.span) for d in program.decls
            if isinstance(d, A.FunctionDecl) and d.body is not None]


def _scope_of(rec: ErrorRecord, spans: list[tuple[str, A.Span]]) -> int | None:
    """Index of the function body containing the record's position, or None for file scope."""
    pos = (rec.line, rec.column)
    for i, (_, s) in enumerate(spans):
        if (s.start_line, s.start_col) <= pos <= (s.end_line, s.end_col):
            return i
    return None


def assign_roots(records: list[ErrorRecord], program: A.Program | None = None) -> None:
    """Set ``root_id`` on every record in place, in id order (rules 1-3 above).

    ``program`` locates function bodies for rule 2. Without it every record
    counts as file scope, so rule 2 groups same-code same-name records file-wide.
    """
    spans = _function_spans(program)
    by_id: dict[str, ErrorRecord] = {}
    first_use: dict[tuple[str, str, int | None], str] = {}
    for rec in sorted(records, key=_id_order):
        key = None
        if rec.code in UNDECLARED_CODES:
            key = (rec.code, rec.found, _scope_of(rec, spans))
        if rec.caused_by is not None and rec.caused_by in by_id:
            rec.root_id = by_id[rec.caused_by].root_id                               # rule 1
        elif key is not None and key in first_use:
            rec.root_id = by_id[first_use[key]].root_id                              # rule 2
        else:
            rec.root_id = rec.id                                                     # rule 3
        if key is not None and key not in first_use:
            first_use[key] = rec.id
        by_id[rec.id] = rec


def roots(records: list[ErrorRecord]) -> list[ErrorRecord]:
    """Records with ``root_id == id``, in (line, column) order (ties by id)."""
    return sorted((r for r in records if r.root_id == r.id), key=lambda r: (r.line, r.column, _id_order(r)))


def cluster_view(records: list[ErrorRecord]) -> list[Cluster]:
    """One Cluster per root, in ``roots()`` order; symptoms in id order."""
    clusters = {r.id: Cluster(root=r, symptoms=[]) for r in roots(records)}
    for rec in sorted(records, key=_id_order):
        if rec.root_id != rec.id and rec.root_id in clusters:
            clusters[rec.root_id].symptoms.append(rec)
    return list(clusters.values())
