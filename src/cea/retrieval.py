"""PRD F7: deterministic RAG retrieval over the corpus in docs/rag/ (standard library only).

The corpus has two kinds of chunk:
- ``rule:<name>``: one chunk per lexical, grammar or ``sem.*`` rule, generated from
  docs/language-spec.md by ``tools/build_rag.py`` (docs/rag/rules.md);
- ``fix:<CODE>``: one curated common mistake and its fix per catalog code
  (docs/rag/fix-patterns.md), tagged with code, phase and rule_ref.

Retrieval is a keyed index, not a similarity search: the record's ``rule_ref`` picks
its rule chunk, its ``code`` picks the fix pattern, its ``phase`` limits which kind
of rule an expected token may pull in, and each expected token adds at most
``MAX_TOKEN_RULES`` more grammar rules that mention it. The result is a short
list in a fixed order (rule, fix pattern, token rules). Chroma or embeddings are
optional extras and are not used here.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

from cea.catalog import REPO_ROOT
from cea.records import ErrorRecord

RAG_DIR = REPO_ROOT / "docs" / "rag"
MAX_TOKEN_RULES = 2
_PHASE_KINDS = {"lexical": ("lexical",), "syntax": ("grammar", "lexical"), "semantic": ("semantic",)}
_NAMED_EXPECTED = {"expression": "expression", "type": "type_spec", "identifier": "IDENT"}


@dataclass(frozen=True)
class Chunk:
    id: str            # "rule:<name>" or "fix:<CODE>"
    kind: str          # "lexical" | "grammar" | "semantic" | "fix"
    rule_ref: str
    text: str
    code: str | None = None
    phase: str | None = None


def _sections(text: str, prefix: str) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith(prefix):
            out.append((line[len(prefix):].strip(), []))
        elif out:
            out[-1][1].append(line)
    return out


def _parse_rules(text: str) -> list[Chunk]:
    chunks = []
    for name, body in _sections(text, "## rule: "):
        kind = next(l.split(":", 1)[1].strip() for l in body if l.startswith("kind:"))
        start = body.index("~~~text") + 1
        end = body.index("~~~", start)
        chunks.append(Chunk(f"rule:{name}", kind, name, "\n".join(body[start:end])))
    return chunks


def _parse_fixes(text: str) -> list[Chunk]:
    chunks = []
    for code, body in _sections(text, "## fix: "):
        tags = {}
        for line in body:
            m = re.match(r"^(code|phase|rule_ref|mistake|fix):\s*(.*)$", line)
            if m:
                tags[m.group(1)] = m.group(2).strip().strip("`")
        body_text = f"Common mistake: {tags['mistake']}\nFix: {tags['fix']}"
        chunks.append(Chunk(f"fix:{code}", "fix", tags["rule_ref"], body_text, tags["code"], tags["phase"]))
    return chunks


@dataclass(frozen=True)
class Index:
    chunks: dict[str, Chunk]          # by id, in corpus order

    def get(self, chunk_id: str) -> Chunk | None:
        return self.chunks.get(chunk_id)

    def ids(self) -> frozenset[str]:
        return frozenset(self.chunks)


@functools.lru_cache(maxsize=None)
def _load(directory: Path) -> Index:
    chunks = _parse_rules((directory / "rules.md").read_text(encoding="utf-8"))
    chunks += _parse_fixes((directory / "fix-patterns.md").read_text(encoding="utf-8"))
    return Index({c.id: c for c in chunks})


def load_index(directory: Path | None = None) -> Index:
    """The corpus index of ``directory`` (default docs/rag), parsed once per directory."""
    return _load(Path(directory).resolve() if directory is not None else RAG_DIR)


def retrieve(record: ErrorRecord, index: Index | None = None) -> list[Chunk]:
    """Chunks for one error record, keyed on rule_ref, code, phase and expected tokens (fixed order)."""
    idx = index or load_index()
    found: list[Chunk] = []

    def add(chunk: Chunk | None) -> None:
        if chunk is not None and chunk not in found:
            found.append(chunk)

    add(idx.get(f"rule:{record.rule_ref}"))
    add(idx.get(f"fix:{record.code}"))
    kinds = _PHASE_KINDS.get(record.phase, ())
    extra = 0
    for token in record.expected:
        name = _NAMED_EXPECTED.get(token)
        if name is not None:
            add(idx.get(f"rule:{name}"))
            continue
        literal = token.strip("'\"")
        if not literal or extra >= MAX_TOKEN_RULES:
            continue
        quoted = f'"{literal}"'
        hits = sorted((c for c in idx.chunks.values()
                       if c.kind in kinds and c.kind != "lexical" and quoted in c.text and c not in found),
                      key=lambda c: (len(c.text), c.rule_ref))
        for chunk in hits[:MAX_TOKEN_RULES - extra]:
            add(chunk)
            extra += 1
    return found
