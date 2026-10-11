"""The structured error record: PRD F1 schema plus docs/error-recovery.md section 2."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    line: int
    column: int


@dataclass
class ErrorRecord:
    # PRD schema fields, in PRD order
    id: str                 # "E-0001", "E-0002", ... in creation order
    phase: str              # "lexical" | "syntax" | "semantic"
    code: str               # a catalog code
    severity: str           # "fatal" | "warning", always from the catalog (PRD F4)
    line: int               # 1-based
    column: int             # 1-based
    found: str              # offending text; "EOF" for the EOF token
    expected: list[str]     # what the failing expect() required; [] if not applicable
    snippet: str            # up to 3 source lines around `line`
    root_id: str            # id of the cluster root; set by cea.cluster.assign_roots (F2, plan 009)
    rule_ref: str           # catalog rule_ref, or the grammar rule for "<production>" rows
    # additions (docs/error-recovery.md section 2)
    language: str           # always "c"
    caused_by: str | None   # set only by rules R1..R8
    span_end: Position      # inclusive end
    message: str            # catalog template with placeholders filled

    def to_dict(self) -> dict:
        """JSON-ready dict in field order; span_end becomes {"line": ..., "column": ...}."""
        return dataclasses.asdict(self)
