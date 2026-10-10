"""Load the error catalog (docs/error-catalog.md) and the grammar rule names.

The catalog table is the single source of truth for every code's phase,
severity (PRD F4), category, rule_ref and message template. No code is
hard-coded here: the table is parsed at run time and cached.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = REPO_ROOT / "docs" / "error-catalog.md"
DEFAULT_SPEC_PATH = REPO_ROOT / "docs" / "language-spec.md"
PRODUCTION = "<production>"

_ROW = re.compile(r"^\|\s*(LEX|SYN|SEM|WRN)-")
_RULE_DEF = re.compile(r"^([a-z_]+)\s*=")


@dataclass(frozen=True)
class CatalogEntry:
    code: str
    phase: str
    severity: str
    category: str
    rule_ref: str          # without backticks; "<production>" for dynamic syntax refs
    message_template: str


@functools.lru_cache(maxsize=None)
def _parse_catalog(path: Path) -> dict[str, CatalogEntry]:
    entries: dict[str, CatalogEntry] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not _ROW.match(line):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            raise ValueError(f"{path}:{n}: expected 7 cells, got {len(cells)}")
        code, phase, severity, category, rule_ref, template, _example = cells
        if code in entries:
            raise ValueError(f"{path}:{n}: duplicate code {code}")
        entries[code] = CatalogEntry(code, phase, severity, category, rule_ref, template)
    return entries


def load_catalog(path: Path | None = None) -> dict[str, CatalogEntry]:
    """Return {code: CatalogEntry} in table order. Each path is parsed once (lru_cache)."""
    resolved = Path(path).resolve() if path is not None else DEFAULT_CATALOG_PATH
    return dict(_parse_catalog(resolved))


@functools.lru_cache(maxsize=None)
def _parse_grammar_rules(path: Path) -> frozenset[str]:
    text = path.read_text(encoding="utf-8")
    section = text.index("## 2. Syntax grammar")
    block_start = text.index("```ebnf", section)
    block_end = text.index("```", block_start + len("```ebnf"))
    names = set()
    for line in text[block_start:block_end].splitlines()[1:]:
        m = _RULE_DEF.match(line)
        if m:
            names.add(m.group(1))
    return frozenset(names)


def load_grammar_rules(path: Path | None = None) -> frozenset[str]:
    """Rule names defined in docs/language-spec.md section 2: the valid runtime rule_refs."""
    resolved = Path(path).resolve() if path is not None else DEFAULT_SPEC_PATH
    return _parse_grammar_rules(resolved)
