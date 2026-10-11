"""Deterministic language-rule lookup for the F3 agent (plan 011, plans/m2-architecture.md section 2).

``rule_text(rule_ref)`` returns the text of one rule of docs/language-spec.md:
- a lexical rule (section 1 ebnf block) or a grammar rule (section 2 ebnf
  block): the rule's definition line plus its continuation lines;
- a semantic rule ``sem.*`` (section 4): the paragraph under its ``###``
  heading, including the C example.
No embeddings and no retrieval ranking: full RAG (F7) is milestone 3. The spec
is parsed once per path (lru_cache).
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

from cea.catalog import DEFAULT_SPEC_PATH

_RULE_DEF = re.compile(r"^([A-Za-z_]+)\s*=")
_SEM_HEADING = re.compile(r"^### (sem\.[a-z_]+)\s*$")


@dataclass(frozen=True)
class RuleText:
    rule_ref: str
    kind: str          # "grammar" | "lexical" | "semantic"
    text: str          # ebnf rule line(s), or the sem.* paragraph and its C example


def _ebnf_block(text: str, heading: str) -> list[str]:
    start = text.index("```ebnf", text.index(heading))
    end = text.index("```", start + len("```ebnf"))
    return text[start:end].splitlines()[1:]


def _ebnf_rules(lines: list[str], kind: str) -> dict[str, RuleText]:
    """A rule is its ``name =`` line plus the indented continuation lines after it."""
    rules: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        m = _RULE_DEF.match(line)
        if m:
            current = m.group(1)
            rules[current] = [line.rstrip()]
        elif current is not None and line.startswith((" ", "\t")) and line.strip():
            rules[current].append(line.rstrip())
        else:
            current = None
    return {name: RuleText(name, kind, "\n".join(body)) for name, body in rules.items()}


def _sem_rules(text: str) -> dict[str, RuleText]:
    lines = text[text.index("## 4. Semantic rules"):].splitlines()
    rules: dict[str, RuleText] = {}
    i = 0
    while i < len(lines):
        m = _SEM_HEADING.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        # only "## " / "### " end a rule: a "#include" line inside a ```c example does not
        while j < len(lines) and not lines[j].startswith(("## ", "### ")):
            j += 1
        rules[m.group(1)] = RuleText(m.group(1), "semantic", "\n".join(lines[i + 1:j]).strip())
        i = j
    return rules


@functools.lru_cache(maxsize=None)
def _load(path: Path) -> dict[str, RuleText]:
    text = path.read_text(encoding="utf-8")
    rules = _ebnf_rules(_ebnf_block(text, "## 1. Lexical grammar"), "lexical")
    rules.update(_ebnf_rules(_ebnf_block(text, "## 2. Syntax grammar"), "grammar"))
    rules.update(_sem_rules(text))
    return rules


def load_rules(path: Path | None = None) -> dict[str, RuleText]:
    """Every rule of docs/language-spec.md by name (lexical, then grammar, then semantic)."""
    return dict(_load(Path(path).resolve() if path is not None else DEFAULT_SPEC_PATH))


def rule_text(rule_ref: str) -> RuleText | None:
    """The spec text of ``rule_ref`` (a catalog/record rule_ref), or None if the spec has no such rule."""
    return _load(DEFAULT_SPEC_PATH).get(rule_ref)
