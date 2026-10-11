# Plan 011: Build the F3 compiler-scoped AI agent (`rules.py`, `agent.py`) and `python -m cea --explain / --fix`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md` (the "Milestone 2" table, row 011), unless a reviewer
> dispatched you and told you they maintain the index. End your final report
> with a **Viva notes** list: the decisions, trade-offs or deviations an
> examiner might ask about (see `plans/README.md`, "Viva notes convention").
> Do not edit `VIVA.md`; the advisor folds your notes into it.
>
> Every code block marked "exact content" is the whole file to write; copy it
> verbatim. Do not reformat or "improve" it. The advisor ran exactly this code
> on a copy of the repo (`40d4ef9` plus plans 008, 009 and 010) and got every
> number quoted below. If a verification fails and your file is identical to
> the plan, STOP and report.
>
> **No network, no secrets.** Every test uses `FakeLLM`. You do NOT need an API
> key, Ollama or any LLM to execute this plan. Never put a key in any file,
> command or report. Do not run `ollama pull`.
>
> **Never open, read, list or run anything under `tests/corpus/heldout/`.**
> (`pytest` deselects held-out tests by default; keep it that way.)
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat 40d4ef9..HEAD -- docs/language-spec.md docs/error-catalog.md src/cea/records.py src/cea/catalog.py tests/corpus/dev tests/corpus/valid` must print exactly two file lines, `docs/error-catalog.md | 2 +-` (plan 008) and `src/cea/records.py | 2 +-` (plan 009's comment), plus the summary line.
> 2. Plans 009 and 010 have landed: `ls src/cea/cluster.py src/cea/llm/__init__.py src/cea/llm/fake.py src/cea/llm/cache.py tools/metrics_f2.py` lists all five without an error, and `grep -c "def format_cluster\|\"--all\"" src/cea/cli.py` prints `2`.
> 3. This plan's files do not exist yet: `ls src/cea/rules.py src/cea/agent.py tests/unit/test_rules.py tests/unit/test_agent.py tests/unit/test_cli_agent.py tests/test_f3_acceptance.py 2>&1 | grep -c "No such file"` prints `6`.
> 4. `.venv/Scripts/python -m pytest -q` ends with `926 passed, 20 deselected` (883 after plans 008+009, plus 43 from plan 010).
>
> If any check fails, STOP and report which one.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED (first code that sends compiler context to an LLM: privacy and scope rules must hold; CLI output gains new flags)
- **Depends on**: `plans/009-f2-clustering.md` (roots via `CompileResult.clusters`), `plans/010-llm-layer.md` (`cea.llm`)
- **Category**: direction (milestone 2, PRD F3)
- **Planned at**: commit `40d4ef9`, 2026-10-11

## Why this matters

The project is a course compiler for a strict C99 subset (Python, `src/cea/`). Milestone 1 produces structured error records; plan 009 groups them under root causes. PRD F3 asks for "a persistent assistant that only sees compiler context (the error record, source snippet, grammar rule)", whose default reply is "two sentences at most, covering what is wrong and where", with "Expand" for the full explanation and "Suggest fix" returning a diff. Acceptance: "every root error has an explanation and a diff, and the agent refuses questions unrelated to the compiler." This plan builds that agent on plan 010's LLM layer: a deterministic spec-rule lookup (`rules.py`), the agent (`agent.py`: prompts, JSON schemas, one retry, deterministic fallbacks, fix application with `difflib`, a local scope guard, caching) and `python -m cea FILE --explain [short|expand] --fix`. Fix diffs are labelled **UNVERIFIED** (owner decision; F8 verifies fixes in milestone 4). The filename never reaches the LLM (PRD privacy note), and tests prove it on the messages `FakeLLM` received. Plan 012 (FastAPI) calls this agent directly.

## Current state

- `plans/m2-architecture.md` §2 (binding contract), quoted:
  ```python
  # rules.py (plan 011): deterministic lookup, no embeddings (full RAG/F7 is milestone 3)
  @dataclass(frozen=True)
  class RuleText:
      rule_ref: str; kind: str          # "grammar" | "lexical" | "semantic"
      text: str                         # ebnf rule line(s), or the sem.* paragraph and its C example
  def rule_text(rule_ref: str) -> RuleText | None: ...   # parsed from docs/language-spec.md, cached

  # agent.py (plan 011)
  @dataclass
  class Explanation:   text: str; rule_ref: str; cited_rule: str | None; mode: str   # "short" | "expand"
  @dataclass
  class FixSuggestion: diff: str; patched_source: str; verified: bool = False         # always False in M2
  @dataclass
  class Answer:        text: str; refused: bool
  class Agent:
      def __init__(self, llm: LLMClient, cache: ExplanationCache | None = None): ...
      def explain(self, record, source: str, mode: str = "short") -> Explanation: ...
      def suggest_fix(self, record, source: str) -> FixSuggestion: ...       # unified diff via difflib
      def ask(self, record, source: str, question: str) -> Answer: ...       # refuses off-topic (F3)
  ```
  Agent rules: "The prompt context is ONLY: the error record, the snippet (or the source for fixes), the `rule_text` of `rule_ref`, and the mode. The filename, paths and any student identity are never sent." "`short` is at most two sentences, saying what is wrong and where. `expand` is the full explanation." "The model returns JSON validated against a schema. Invalid output gets one retry, then a deterministic fallback built from the catalog message." "Scope guard: a cheap local keyword/heuristic pre-check refuses clearly off-topic questions without calling the LLM. The system prompt also instructs refusal." "Explanations are cached by error signature." §5: "No network in tests." "`print` only in `cli.py`."
- `docs/language-spec.md` structure the rule parser relies on: `## 1. Lexical grammar` followed by an ` ```ebnf ` block (18 rules, e.g. `STRING_LIT`, `escape`, `token`); `## 2. Syntax grammar` followed by an ` ```ebnf ` block (36 rules; continuation lines start with spaces, e.g. `statement`); `## 4. Semantic rules` with 16 `### sem.<name>` headings, each followed by a paragraph and a ` ```c ` example (the `sem.builtins` example contains a `#include <stdio.h>` line, which is NOT a heading). `## 5. Example program` ends section 4. `tools/check_spec.py` reports `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`.
- Record `rule_ref` values: a lexical or grammar rule name, or `sem.*` (`src/cea/records.py`; catalog `<production>` rows resolve to the grammar rule being parsed). Every catalog `rule_ref` exists in the spec (checked by `tools/check_spec.py`).
- `src/cea/records.py`: `ErrorRecord` fields `id, phase, code, severity, line, column, found, expected, snippet, root_id, rule_ref, language, caused_by, span_end, message`. `snippet` is source lines `max(1, line-1) .. min(last, line+1)` joined with `"\n"`. The record has **no filename field**.
- `src/cea/pipeline.py` (after plan 009): `compile_source(source, filename) -> CompileResult` with `errors`, `clusters: list[Cluster]` (one per root, roots in (line, column) order; `Cluster.root`, `Cluster.symptoms`).
- `src/cea/cli.py` (after plan 009, 70 lines): `format_record`, `format_cluster`, `main(argv)` with `file`, `--json`, `--all`. Text mode prints one line per cluster (`... (+N related)`), then the F4 summary; `--json` prints `{"file","ok","summary","errors","clusters"}`. Exit 0/1/2. This plan replaces the whole file; everything existing stays byte-for-byte the same in behaviour when the new flags are not given (the 101 tests of `tests/unit/test_pipeline_cli.py` keep passing unchanged).
- `cea.llm` (plan 010): `LLMClient`, `LLMError`, `FakeLLM(script=(), *, default=None)` (records every call in `.calls` as `{"messages","json_schema","max_tokens","temperature"}`; a callable reply gets `(messages, json_schema)`), `ExplanationCache(path=None)` with `get(signature, mode)`, `put(signature, mode, value)`, `len()`, default path `<repo>/.cea_cache/explanations.json`; `client_from_env()` raises `LLMError("no LLM configured: …")` when nothing is set.
- Example records used by the tests (advisor probe, exact):
  `int main(void) {\n    int total = 0;\n    total = total + 1\n    return total;\n}\n` → one record `E-0001 SYN-MISSING-SEMICOLON` at 3:22, found `return`, expected `[';']`, rule_ref `expr_stmt`, message `Expected ';' after the expression statement but found 'return'`, snippet = lines 2–4.
- Repo conventions: module docstring on every file, type hints, `@dataclass`, stdlib only in `src/cea/`, unit tests in `tests/unit/test_<module>.py` with plain `assert` and `pytest.mark.parametrize` (model: `tests/unit/test_pipeline_cli.py`); corpus-wide tests live in `tests/` (model: `tests/test_corpus_compile.py`, which uses `tests/corpus_lib.py`).

## Design decisions (fixed; do not change)

1. **Fix format.** The model does not write a diff (models get hunk headers wrong). It returns `{"start_line", "end_line", "replacement": [lines]}`; the agent replaces those lines in a copy of the source and builds the unified diff with `difflib` (labels `original`/`suggested`, never the filename). Out-of-range ranges and no-op edits count as invalid output (one retry, then no fix: `diff == ""`, `patched_source == source`). The student's file is never written.
2. **`cited_rule`** is the rule the agent supplied in the prompt (`rule_text(record.rule_ref)`), or `None` if the spec has no such rule. It is never taken from the model, so the agent can never cite a rule that does not exist (groundwork for F7's "none cite a rule that does not exist").
3. **Short mode** keeps the first two sentences of the model's text (split at `.`, `!`, `?` followed by whitespace, not after `e.g.`/`i.e.`; whitespace collapsed).
4. **Retries and fallbacks.** Invalid JSON or a schema mismatch → exactly one retry (the bad reply and a correction message are appended). A second failure, or any `LLMError`, → a deterministic fallback: `Line L, column C: <catalog message>.` (expand adds the rule name and text). Fallbacks are never cached, so the next run with a working LLM gets a real answer.
5. **Schemas** use only `type`, `properties`, `required`, `items` (no `additionalProperties`, no `strict`), the subset both Gemini's and Ollama's OpenAI endpoints accept. The agent validates replies itself (`matches_schema`).
6. **Scope guard.** `is_off_topic` refuses locally: an empty question, a clearly unrelated topic (weather, poem, football, capital of, essay, …), or a question with no compiler/C vocabulary, no C punctuation and no identifier from the error's snippet. Everything else goes to the model, whose system prompt also instructs refusal.
7. **Cache signature** = prompt version + code, rule_ref, message, found, expected, line, column, snippet (no filename, no record id). Fixes add the sha256 of the whole source and use mode `fix`. `ask` is not cached.
8. **CLI.** `--explain [short|expand]` and `--fix` run once per ROOT (cluster), not per record. `--all` with either flag is a usage error (exit 2). `--no-cache` skips the cache. With no LLM configured, exit 2 with the `LLMError` message on stderr. With `--json`, an `agent` array is added: `[{root_id, explanation|null, fix|null}]`.

## Advisor's verification (what you should reproduce)

On a scratch copy at `40d4ef9` + plans 008, 009, 010 (Python 3.13.1, gcc on PATH):
- Full suite after each step: 926 → 939 → 989 → 1045 → 1055 passed, 20 deselected.
- `tests/unit/test_rules.py` 13 passed; `tests/unit/test_agent.py` 50 passed; `tests/test_f3_acceptance.py` 56 passed (54 dev programs + 2); `tests/unit/test_cli_agent.py` 10 passed.
- Optional live check (NOT required; not a test): with Ollama running and `llama3.1` already pulled, `CEA_LLM_FALLBACK_MODEL=llama3.1 python -m cea <file> --explain --fix --no-cache` on the 5-line example above took about 10 s and printed a two-sentence explanation ("You forgot to add a semicolon at the end of the line on line 3, column 22. This is a required character in C to end a statement.") and a diff that added the `;` but also lost the indentation and duplicated `return total;`. That is exactly why fixes are labelled UNVERIFIED until F8. `--explain expand` on `dev/043` gave a correct multi-sentence explanation citing `sem.declare_before_use`. Gemini was not tried (no key).

Without `gcc` on PATH, one gcc test is skipped: read every "N passed" as "N-1 passed, 1 skipped".

## Commands you will need

| Purpose | Command (project root, Git Bash) | Expected on success |
|---|---|---|
| Tests | `.venv/Scripts/python -m pytest -q` | see each step |
| One file | `.venv/Scripts/python -m pytest -q tests/unit/test_agent.py` | see each step |
| Spec check | `.venv/Scripts/python tools/check_spec.py` | `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules` |
| CLI, no LLM | `env -u CEA_LLM_BASE_URL -u CEA_LLM_MODEL -u CEA_LLM_FALLBACK_MODEL PYTHONPATH=src .venv/Scripts/python -m cea tests/corpus/dev/043-loop-counter-never-declared.c` | 2 lines, exit 1 (unchanged from plan 009) |

## Scope

**In scope** (the only files you may create or modify):
- `src/cea/rules.py`, `src/cea/agent.py` (create); `src/cea/cli.py` (replace)
- `tests/unit/test_rules.py`, `tests/unit/test_agent.py`, `tests/unit/test_cli_agent.py`, `tests/test_f3_acceptance.py` (create)
- `plans/README.md` (status row 011 only)

**Out of scope** (do NOT touch):
- `src/cea/llm/**` (plan 010's layer is used as is; if it seems to need a change, STOP), `src/cea/pipeline.py`, `cluster.py`, the compiler phases, `records.py`, `catalog.py`.
- `docs/**` (the rule parser reads `docs/language-spec.md`; it must not be edited to suit the parser), `tests/corpus/**` (sidecars, `.c` files), `tests/corpus/heldout/**` (never read).
- `tests/unit/test_pipeline_cli.py` and every other existing test: they must pass unchanged.
- `.env`, `.cea_cache/` (never create or commit them), `VIVA.md`, `plans/m2-architecture.md`.
- F5 (verbosity templates), F6 (per-error chat history), F7 (RAG), F8 (verified fixes): later milestones. Do not add them.

## Git workflow

- Branch: `advisor/011-f3-agent` from `main` (after 009 and 010 are merged).
- One commit per step. Stage by explicit path (never `git add -A` / `git add .`). Message style as in `git log` (`cea: …`, `tests: …`, `plans: …` with `(plan 011 step N)`). Every commit message ends with a blank line and then:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
- Do NOT push (there is no remote). Do NOT merge; the owner reviews first.

## Steps

### Step 1: `rules.py`, the deterministic spec-rule lookup

1a. Create `src/cea/rules.py`, exact content:

````python
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
````

1b. Create `tests/unit/test_rules.py`, exact content:

````python
"""cea.rules (plan 011): deterministic rule lookup from docs/language-spec.md."""
import pytest

from cea.catalog import PRODUCTION, load_catalog, load_grammar_rules
from cea.rules import RuleText, load_rules, rule_text


def test_rule_counts_by_kind():
    kinds = [r.kind for r in load_rules().values()]
    assert (kinds.count("lexical"), kinds.count("grammar"), kinds.count("semantic")) == (18, 36, 16)


def test_every_grammar_rule_name_resolves_as_grammar():
    for name in load_grammar_rules():
        assert rule_text(name).kind == "grammar", name


def test_every_catalog_rule_ref_resolves():
    refs = {e.rule_ref for e in load_catalog().values() if e.rule_ref != PRODUCTION}
    missing = sorted(r for r in refs if rule_text(r) is None)
    assert not missing


@pytest.mark.parametrize("ref,kind,text", [
    ("var_decl", "grammar", 'var_decl       = var_core , ";" ;'),
    ("statement", "grammar", "statement      = var_decl | if_stmt | while_stmt | for_stmt | return_stmt\n"
                             "               | break_stmt | continue_stmt | block | expr_stmt | empty_stmt ;"),
    ("STRING_LIT", "lexical", "STRING_LIT          = '\"' , { string_char | escape } , '\"' ;  (* may not span lines *)"),
])
def test_ebnf_rule_text(ref, kind, text):
    assert rule_text(ref) == RuleText(ref, kind, text)


def test_semantic_rule_has_paragraph_and_example():
    r = rule_text("sem.declare_before_use")
    assert r.kind == "semantic"
    assert r.text.startswith("Variables must be declared before use;")
    assert "```c" in r.text and r.text.endswith("```")
    assert "### " not in r.text


def test_include_line_inside_example_does_not_cut_the_rule():
    r = rule_text("sem.builtins")
    assert "#include <stdio.h>" in r.text and "printf(x);" in r.text and r.text.endswith("```")


@pytest.mark.parametrize("ref", ["", "nonexistent", "sem.nothing", "<production>", "##"])
def test_unknown_rule_is_none(ref):
    assert rule_text(ref) is None
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_rules.py` → `13 passed`
- `PYTHONPATH=src .venv/Scripts/python -c "from cea.rules import load_rules; print(len(load_rules()))"` → `70`
- `.venv/Scripts/python -m pytest -q` → `939 passed, 20 deselected`

Commit: `cea: deterministic spec rule lookup for the F3 agent (plan 011 step 1)`, staging `src/cea/rules.py tests/unit/test_rules.py`.

### Step 2: `agent.py`, the F3 agent, and its unit tests

2a. Create `src/cea/agent.py`, exact content:

````python
"""PRD F3: the compiler-scoped AI agent (plan 011, plans/m2-architecture.md section 2).

The agent sees ONLY compiler context: the error record, the source snippet (the
whole source for a fix), the spec text of the record's ``rule_ref``
(``cea.rules``) and the mode. The filename, paths and any student identity are
never sent (PRD privacy note); the agent is never even given them.

- ``explain``: ``short`` is at most two sentences (what is wrong and where),
  truncated deterministically if the model says more; ``expand`` is the full
  explanation.
- ``suggest_fix``: the model names a line range and replacement lines; the
  agent applies them to a copy of the source and builds a unified diff with
  difflib. ``verified`` is always False in milestone 2 (F8 is milestone 4).
- ``ask``: a local keyword check refuses clearly off-topic questions without
  calling the LLM; the system prompt makes the model refuse the rest.

Every reply must be JSON matching a schema. Invalid output gets ONE retry,
then a deterministic fallback built from the catalog message. A transport
failure (``LLMError``) goes straight to the fallback. Successful explanations
and fixes are cached by error signature (``ExplanationCache``); fallbacks are
never cached. Nothing here prints.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass

from cea.llm import ExplanationCache, LLMClient, LLMError
from cea.records import ErrorRecord
from cea.rules import RuleText, rule_text

PROMPT_VERSION = 1          # part of every cache signature: bump it when a prompt or schema changes
MODES = ("short", "expand")

SYSTEM_PROMPT = (
    "You are the error assistant of a teaching compiler for a small subset of C99. "
    "You only help with the one compiler error you are given: what is wrong, where it is, "
    "which language rule it breaks, and how to fix it in this program. "
    "Use only the error record, the source lines and the language rule in the user message; "
    "do not invent rules or features outside the subset. "
    "If a question is not about this error, this program or the course C subset, refuse: "
    "say that you can only help with this compiler error, and set \"refused\" to true where the schema has it. "
    "Reply with one JSON object that matches the requested schema and nothing else."
)

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {"explanation": {"type": "string"}},
    "required": ["explanation"],
}
FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
        "replacement": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["start_line", "end_line", "replacement"],
}
ASK_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "refused": {"type": "boolean"}},
    "required": ["answer", "refused"],
}

RETRY_PROMPT = ("Your previous reply was not a single valid JSON object matching the schema. "
                "Reply again with only that JSON object.")
REFUSAL_TEXT = ("I can only help with this compiler error: what it means, where it is, "
                "which rule it breaks and how to fix it.")
NO_ANSWER_TEXT = "The assistant could not answer right now. The compiler says: {message}"

TASKS = {
    "short": ("Explain this error to a beginner in at most two sentences: say what is wrong and where "
              "(line and column). Reply as JSON: {\"explanation\": \"...\"}"),
    "expand": ("Explain this error fully to a beginner: what is wrong, where, why the language rule above "
               "forbids it, and how to fix it. Do not include a diff. Reply as JSON: {\"explanation\": \"...\"}"),
    "fix": ("Suggest the smallest edit that fixes only this error. Lines are numbered from 1. Lines "
            "start_line to end_line (inclusive) are replaced by the replacement lines (no line numbers). "
            "Reply as JSON: {\"start_line\": N, \"end_line\": M, \"replacement\": [\"...\"]}"),
    "ask": ("Answer the student's question below about this error in at most four sentences. If it is not "
            "about this error, this program or the course C subset, refuse. "
            "Reply as JSON: {\"answer\": \"...\", \"refused\": false}"),
}
MAX_TOKENS = {"short": 300, "expand": 900, "fix": 900, "ask": 500}


@dataclass
class Explanation:
    text: str
    rule_ref: str
    cited_rule: str | None
    mode: str           # "short" | "expand"


@dataclass
class FixSuggestion:
    diff: str
    patched_source: str
    verified: bool = False      # always False in milestone 2 (F8 verifies fixes in milestone 4)


@dataclass
class Answer:
    text: str
    refused: bool


# ---------------------------------------------------------------- sentences (short mode)
_SENTENCE_END = re.compile(r"(?<=[.!?])(?<!e\.g\.)(?<!i\.e\.)\s+")


def sentences(text: str) -> list[str]:
    """Split on ., ! or ? followed by whitespace (not after "e.g." / "i.e."); whitespace is collapsed."""
    flat = " ".join(text.split())
    return [s for s in _SENTENCE_END.split(flat) if s] if flat else []


def first_sentences(text: str, n: int = 2) -> str:
    """The first ``n`` sentences of ``text`` (deterministic truncation for short mode)."""
    return " ".join(sentences(text)[:n])


# ---------------------------------------------------------------- scope guard
OFF_TOPIC = re.compile(
    r"\b(weather|recipe|cook|poem|poetry|song|lyrics|joke|story|movie|film|football|soccer|cricket|"
    r"president|election|politic\w*|stock|bitcoin|crypto|capital of|history of|translate|horoscope|"
    r"dating|girlfriend|boyfriend|essay|holiday|vacation|celebrity)\b", re.IGNORECASE)
ON_TOPIC_WORDS = frozenset("""
    error errors warning warnings compile compiler compiles compiling code program line lines column
    semicolon semicolons bracket brackets brace braces parenthesis parentheses paren token tokens
    syntax grammar rule rules spec scope declare declared declaration undeclared define defined definition
    variable variables function functions call calls argument arguments parameter parameters param
    type types int float double char void array arrays index loop loops return returns break continue
    printf include stdio main string literal value values expression expressions statement statements
    assign assignment operator fix fixed fixing wrong mean means meaning explain expect expected expects
    missing unused unreachable narrowing cast c99 c this here
""".split())
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_C_PUNCT = re.compile(r"[;{}()\[\]=]")


def is_off_topic(question: str, record: ErrorRecord | None = None) -> bool:
    """Cheap local pre-check (F3 scope guard). True = refuse without calling the LLM.

    Refuses an empty question, one that names a clearly unrelated topic, and one
    that has no compiler or C vocabulary, no C punctuation and no identifier
    from the error's snippet. Borderline questions pass and the model decides.
    """
    q = question.strip()
    if not q or OFF_TOPIC.search(q):
        return True
    words = {w.lower() for w in _WORD.findall(q)}
    if words & ON_TOPIC_WORDS or _C_PUNCT.search(q):
        return False
    if record is not None:
        names = {w.lower() for w in _WORD.findall(record.snippet + " " + record.found)}
        if words & names:
            return False
    return True


# ---------------------------------------------------------------- JSON replies
def _parse_json(raw: str) -> dict | None:
    text = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


_JSON_TYPES = {"string": str, "boolean": bool, "object": dict, "array": list}


def matches_schema(obj: object, schema: dict) -> bool:
    """The small JSON-schema subset used here: type, properties, required, items."""
    kind = schema.get("type")
    if kind == "integer":
        if not isinstance(obj, int) or isinstance(obj, bool):
            return False
    elif kind in _JSON_TYPES and not isinstance(obj, _JSON_TYPES[kind]):
        return False
    if kind == "object":
        if any(k not in obj for k in schema.get("required", [])):
            return False
        return all(matches_schema(obj[k], sub) for k, sub in schema.get("properties", {}).items() if k in obj)
    if kind == "array" and "items" in schema:
        return all(matches_schema(item, schema["items"]) for item in obj)
    return True


# ---------------------------------------------------------------- the agent
class Agent:
    def __init__(self, llm: LLMClient, cache: ExplanationCache | None = None):
        self.llm = llm
        self.cache = cache

    # -- prompt context: the record, source lines, rule text and mode; never a filename
    @staticmethod
    def _numbered(text: str, first_line: int) -> str:
        lines = text.splitlines() or [""]
        return "\n".join(f"{n:>4} | {line}" for n, line in enumerate(lines, first_line))

    def _context(self, record: ErrorRecord, rule: RuleText | None, mode: str, source_block: str) -> str:
        expected = ", ".join(record.expected) if record.expected else "(none)"
        parts = [
            f"Mode: {mode}",
            "Error record:",
            f"  code: {record.code}",
            f"  phase: {record.phase}",
            f"  severity: {record.severity}",
            f"  position: line {record.line}, column {record.column}",
            f"  found: {record.found}",
            f"  expected: {expected}",
            f"  message: {record.message}",
            f"  rule_ref: {record.rule_ref}",
        ]
        if rule is not None:
            parts.append(f"Language rule {rule.rule_ref} ({rule.kind}):")
            parts.extend("  " + line for line in rule.text.splitlines())
        else:
            parts.append(f"Language rule {record.rule_ref}: (not found in the specification)")
        parts.append(source_block)
        return "\n".join(parts)

    def _snippet_block(self, record: ErrorRecord) -> str:
        return "Source lines:\n" + self._numbered(record.snippet, max(1, record.line - 1))

    def _messages(self, record: ErrorRecord, mode: str, source_block: str, extra: str = "") -> list[dict]:
        rule = rule_text(record.rule_ref)
        user = self._context(record, rule, mode, source_block) + "\nTask: " + TASKS[mode] + extra
        return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]

    def _call_json(self, messages: list[dict], schema: dict, mode: str, check=None) -> dict | None:
        """At most two LLM calls: the request and one retry after invalid output. None = use the fallback."""
        for attempt in range(2):
            try:
                raw = self.llm.complete(messages, json_schema=schema, max_tokens=MAX_TOKENS[mode], temperature=0.2)
            except LLMError:
                return None
            obj = _parse_json(raw)
            if obj is not None and matches_schema(obj, schema) and (check is None or check(obj)):
                return obj
            messages = messages + [{"role": "assistant", "content": raw}, {"role": "user", "content": RETRY_PROMPT}]
        return None

    @staticmethod
    def _signature(record: ErrorRecord) -> dict:
        """The error signature the cache is keyed on (with the mode); no filename, no record id."""
        return {"v": PROMPT_VERSION, "code": record.code, "rule_ref": record.rule_ref, "message": record.message,
                "found": record.found, "expected": list(record.expected), "line": record.line,
                "column": record.column, "snippet": record.snippet}

    # -- explain
    @staticmethod
    def fallback_text(record: ErrorRecord, mode: str) -> str:
        """Deterministic explanation from the catalog message (used when the model fails)."""
        message = record.message.rstrip()
        if not message.endswith((".", "!", "?")):
            message += "."
        text = f"Line {record.line}, column {record.column}: {message}"
        if mode == "expand":
            text += f" This breaks the language rule '{record.rule_ref}'."
            rule = rule_text(record.rule_ref)
            if rule is not None:
                text += "\n\n" + rule.text
        return text

    def explain(self, record: ErrorRecord, source: str, mode: str = "short") -> Explanation:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        rule = rule_text(record.rule_ref)
        cited = rule.rule_ref if rule is not None else None
        sig = self._signature(record)
        hit = self.cache.get(sig, mode) if self.cache is not None else None
        if hit is not None and isinstance(hit.get("text"), str):
            return Explanation(hit["text"], record.rule_ref, cited, mode)
        obj = self._call_json(self._messages(record, mode, self._snippet_block(record)), EXPLAIN_SCHEMA, mode,
                              check=lambda o: bool(o["explanation"].strip()))
        if obj is None:
            text = self.fallback_text(record, mode)
        else:
            text = obj["explanation"].strip()
        if mode == "short":
            text = first_sentences(text, 2)
        if obj is not None and self.cache is not None:
            self.cache.put(sig, mode, {"text": text})
        return Explanation(text, record.rule_ref, cited, mode)

    # -- suggest_fix
    @staticmethod
    def apply_fix(source: str, start_line: int, end_line: int, replacement: list[str]) -> str:
        """Replace lines start_line..end_line (1-based, inclusive) of a copy of ``source``."""
        newline = "\r\n" if "\r\n" in source else "\n"
        lines = source.splitlines()
        new_lines = [part for item in replacement for part in item.splitlines() or [""]]
        patched = lines[:start_line - 1] + new_lines + lines[end_line:]
        text = newline.join(patched)
        return text + newline if source.endswith(("\n", "\r")) and patched else text

    @staticmethod
    def unified_diff(source: str, patched: str) -> str:
        """difflib unified diff with neutral file labels (never the student's filename)."""
        lines = difflib.unified_diff(source.splitlines(), patched.splitlines(), "original", "suggested",
                                     lineterm="")
        text = "\n".join(lines)
        return text + "\n" if text else ""

    def suggest_fix(self, record: ErrorRecord, source: str) -> FixSuggestion:
        line_count = len(source.splitlines())

        def valid(o: dict) -> bool:
            if not 1 <= o["start_line"] <= o["end_line"] <= line_count:
                return False
            return self.apply_fix(source, o["start_line"], o["end_line"], o["replacement"]) != source

        sig = dict(self._signature(record), source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest())
        hit = self.cache.get(sig, "fix") if self.cache is not None else None
        obj = hit if hit is not None and matches_schema(hit, FIX_SCHEMA) and valid(hit) else None
        if obj is None:
            block = "Source (whole file):\n" + self._numbered(source, 1)
            obj = self._call_json(self._messages(record, "fix", block), FIX_SCHEMA, "fix", check=valid)
            if obj is None:
                return FixSuggestion(diff="", patched_source=source, verified=False)
            if self.cache is not None:
                self.cache.put(sig, "fix", {k: obj[k] for k in ("start_line", "end_line", "replacement")})
        patched = self.apply_fix(source, obj["start_line"], obj["end_line"], obj["replacement"])
        return FixSuggestion(diff=self.unified_diff(source, patched), patched_source=patched, verified=False)

    # -- ask
    def ask(self, record: ErrorRecord, source: str, question: str) -> Answer:
        if is_off_topic(question, record):
            return Answer(REFUSAL_TEXT, refused=True)
        extra = '\nStudent question: """' + question.strip().replace('"""', "'''") + '"""'
        obj = self._call_json(self._messages(record, "ask", self._snippet_block(record), extra), ASK_SCHEMA, "ask",
                              check=lambda o: bool(o["answer"].strip()) or o["refused"])
        if obj is None:
            return Answer(NO_ANSWER_TEXT.format(message=record.message), refused=False)
        if obj["refused"]:
            return Answer(obj["answer"].strip() or REFUSAL_TEXT, refused=True)
        return Answer(obj["answer"].strip(), refused=False)
````

Notes (do not change the code because of them): `explain` takes `source` to match the contract but uses only `record.snippet` (the snippet is the explanation's context; the whole source is sent only for fixes). The system prompt is a single constant so a reviewer can read the whole scope restriction in one place. `MAX_TOKENS` is generous on purpose: short replies are truncated locally anyway, and a too-small budget makes some models return empty content.

2b. Create `tests/unit/test_agent.py`, exact content:

````python
"""cea.agent (plan 011, PRD F3): prompts, schemas, short mode, retries, fallbacks, fixes,
the scope guard, privacy and caching. Every test uses FakeLLM; nothing touches the network."""
import json

import pytest

from cea import agent as AG
from cea.agent import Agent, Answer, Explanation, FixSuggestion
from cea.llm import ExplanationCache, FakeLLM, LLMError
from cea.pipeline import compile_source

SRC = "int main(void) {\n    int total = 0;\n    total = total + 1\n    return total;\n}\n"
FIXED = "int main(void) {\n    int total = 0;\n    total = total + 1;\n    return total;\n}\n"
GOOD_FIX = json.dumps({"start_line": 3, "end_line": 3, "replacement": ["    total = total + 1;"]})
DIFF = ("--- original\n+++ suggested\n@@ -1,5 +1,5 @@\n int main(void) {\n     int total = 0;\n"
        "-    total = total + 1\n+    total = total + 1;\n     return total;\n }\n")


@pytest.fixture
def rec():
    (r,) = compile_source(SRC, "secret-student-4711.c").errors
    assert (r.code, r.line, r.column, r.rule_ref) == ("SYN-MISSING-SEMICOLON", 3, 22, "expr_stmt")
    return r


def reply(text):
    return json.dumps({"explanation": text})


def user_msg(call):
    return call["messages"][1]["content"]


# ---------------------------------------------------------------- prompt content
def test_explain_prompt_has_system_scope_record_rule_snippet_and_mode(rec):
    fake = FakeLLM([reply("Missing ';' on line 3.")])
    Agent(fake).explain(rec, SRC, "short")
    (call,) = fake.calls
    system, user = call["messages"]
    assert system == {"role": "system", "content": AG.SYSTEM_PROMPT}
    assert "only help with the one compiler error" in AG.SYSTEM_PROMPT and "refuse" in AG.SYSTEM_PROMPT
    assert user["role"] == "user"
    text = user["content"]
    assert text.startswith("Mode: short\nError record:\n  code: SYN-MISSING-SEMICOLON\n")
    assert "  position: line 3, column 22" in text and "  found: return" in text and "  expected: ;" in text
    assert f"  message: {rec.message}" in text
    assert 'Language rule expr_stmt (grammar):\n  expr_stmt      = expression , ";" ;' in text
    assert "Source lines:\n   2 |     int total = 0;\n   3 |     total = total + 1\n   4 |     return total;" in text
    assert call["json_schema"] == AG.EXPLAIN_SCHEMA and call["max_tokens"] == 300


def test_schemas_are_plain_json_schema():
    for schema in (AG.EXPLAIN_SCHEMA, AG.FIX_SCHEMA, AG.ASK_SCHEMA):
        assert schema["type"] == "object" and set(schema["required"]) == set(schema["properties"])
        json.dumps(schema)


# ---------------------------------------------------------------- explain
def test_short_explanation(rec):
    exp = Agent(FakeLLM([reply("  Line 3 is missing a ';'.  ")])).explain(rec, SRC)
    assert exp == Explanation("Line 3 is missing a ';'.", "expr_stmt", "expr_stmt", "short")


def test_short_mode_truncates_to_two_sentences(rec):
    exp = Agent(FakeLLM([reply("One. Two!\nThree? Four.")])).explain(rec, SRC, "short")
    assert exp.text == "One. Two!"


def test_expand_mode_keeps_everything(rec):
    fake = FakeLLM([reply("One. Two. Three.\n\nFour.")])
    exp = Agent(fake).explain(rec, SRC, "expand")
    assert exp.text == "One. Two. Three.\n\nFour." and exp.mode == "expand"
    assert user_msg(fake.calls[0]).startswith("Mode: expand\n") and fake.calls[0]["max_tokens"] == 900


def test_bad_mode_is_rejected(rec):
    with pytest.raises(ValueError):
        Agent(FakeLLM()).explain(rec, SRC, "verbose")


@pytest.mark.parametrize("text,expected", [
    ("A. B. C.", ["A.", "B.", "C."]),
    ("Use e.g. 'x' here. Then stop.", ["Use e.g. 'x' here.", "Then stop."]),
    ("x = 1.5; is fine. ok", ["x = 1.5; is fine.", "ok"]),
    ("no end punctuation", ["no end punctuation"]),
    ("  ", []),
])
def test_sentence_split(text, expected):
    assert AG.sentences(text) == expected


def test_fenced_json_is_accepted(rec):
    exp = Agent(FakeLLM(["```json\n" + reply("Fenced.") + "\n```"])).explain(rec, SRC)
    assert exp.text == "Fenced."


@pytest.mark.parametrize("bad", ["not json", "[1, 2]", '{"explanation": 3}', '{"text": "x"}', '{"explanation": "  "}'])
def test_invalid_output_gets_one_retry(rec, bad):
    fake = FakeLLM([bad, reply("Second try.")])
    exp = Agent(fake).explain(rec, SRC)
    assert exp.text == "Second try." and len(fake.calls) == 2
    retry = fake.calls[1]["messages"]
    assert retry[:2] == fake.calls[0]["messages"]
    assert retry[2] == {"role": "assistant", "content": bad}
    assert retry[3] == {"role": "user", "content": AG.RETRY_PROMPT}


def test_invalid_twice_falls_back_to_catalog_message(rec):
    fake = FakeLLM(["nope", "still nope", reply("never asked")])
    exp = Agent(fake).explain(rec, SRC, "short")
    assert len(fake.calls) == 2
    assert exp.text == "Line 3, column 22: Expected ';' after the expression statement but found 'return'."
    assert (exp.rule_ref, exp.cited_rule) == ("expr_stmt", "expr_stmt")


def test_expand_fallback_includes_the_rule(rec):
    exp = Agent(FakeLLM(default="nope")).explain(rec, SRC, "expand")
    assert exp.text.startswith("Line 3, column 22: Expected ';'")
    assert "This breaks the language rule 'expr_stmt'.\n\nexpr_stmt      = expression" in exp.text


def test_llm_error_falls_back_without_retry(rec):
    fake = FakeLLM([LLMError("network down")])
    exp = Agent(fake).explain(rec, SRC)
    assert len(fake.calls) == 1 and exp.text.startswith("Line 3, column 22: ")


def test_fallback_short_text_is_at_most_two_sentences():
    src = "int main(void) {\n    char c = 'ab';\n    return 0;\n}\n"
    r = next(e for e in compile_source(src, "t.c").errors if e.code == "LEX-BAD-CHAR-LITERAL")
    exp = Agent(FakeLLM(default="nope")).explain(r, src)
    assert exp.text == f"Line 2, column 14: {r.message}."
    assert len(AG.sentences(exp.text)) <= 2


# ---------------------------------------------------------------- suggest_fix
def test_fix_applies_replacement_and_builds_unified_diff(rec):
    fake = FakeLLM([GOOD_FIX])
    fix = Agent(fake).suggest_fix(rec, SRC)
    assert fix == FixSuggestion(diff=DIFF, patched_source=FIXED, verified=False)
    text = user_msg(fake.calls[0])
    assert text.startswith("Mode: fix\n") and fake.calls[0]["json_schema"] == AG.FIX_SCHEMA
    assert "Source (whole file):\n   1 | int main(void) {\n" in text and "   5 | }" in text


def test_fix_is_never_verified(rec):
    assert Agent(FakeLLM([GOOD_FIX])).suggest_fix(rec, SRC).verified is False


@pytest.mark.parametrize("bad", [
    '{"start_line": 0, "end_line": 3, "replacement": ["x"]}',             # out of range
    '{"start_line": 4, "end_line": 3, "replacement": ["x"]}',             # end before start
    '{"start_line": 3, "end_line": 9, "replacement": ["x"]}',             # past the end of the file
    '{"start_line": 3, "end_line": 3, "replacement": ["    total = total + 1"]}',   # changes nothing
    '{"start_line": "3", "end_line": 3, "replacement": ["x"]}',           # wrong type
    '{"start_line": 3, "end_line": 3}',                                    # missing key
])
def test_invalid_fix_is_retried_then_falls_back(rec, bad):
    fake = FakeLLM([bad, bad])
    fix = Agent(fake).suggest_fix(rec, SRC)
    assert len(fake.calls) == 2
    assert fix == FixSuggestion(diff="", patched_source=SRC, verified=False)


def test_fix_retry_succeeds(rec):
    fake = FakeLLM(["garbage", GOOD_FIX])
    assert Agent(fake).suggest_fix(rec, SRC).patched_source == FIXED


def test_apply_fix_splits_multiline_items_and_deletes():
    src = "a\nb\nc\n"
    assert Agent.apply_fix(src, 2, 2, ["x\ny", ""]) == "a\nx\ny\n\nc\n"
    assert Agent.apply_fix(src, 2, 3, []) == "a\n"
    assert Agent.apply_fix("a\r\nb\r\n", 1, 1, ["z"]) == "z\r\nb\r\n"      # CRLF kept
    assert Agent.apply_fix("a\nb", 2, 2, ["c"]) == "a\nc"                    # no final newline kept


# ---------------------------------------------------------------- ask and the scope guard
@pytest.mark.parametrize("question", [
    "What is the capital of France?",
    "Write me a poem about the sea",
    "Who won the football world cup?",
    "What's the weather like today?",
    "Can you help with my history essay?",
    "Tell me a joke",
    "",
])
def test_off_topic_questions_are_refused_without_calling_the_llm(rec, question):
    fake = FakeLLM(default=json.dumps({"answer": "should not be called", "refused": False}))
    ans = Agent(fake).ask(rec, SRC, question)
    assert ans == Answer(AG.REFUSAL_TEXT, refused=True)
    assert fake.calls == []


@pytest.mark.parametrize("question", [
    "why does it expect a semicolon here?",
    "What does this mean?",
    "How do I fix this?",
    "is total declared?",                      # an identifier from the snippet
    "what about x = 1;",                       # C punctuation
])
def test_on_topic_questions_reach_the_llm(rec, question):
    fake = FakeLLM([json.dumps({"answer": "Because expr_stmt ends with ';'.", "refused": False})])
    ans = Agent(fake).ask(rec, SRC, question)
    assert ans == Answer("Because expr_stmt ends with ';'.", refused=False)
    (call,) = fake.calls
    assert call["json_schema"] == AG.ASK_SCHEMA
    assert user_msg(call).startswith("Mode: ask\n") and f'Student question: """{question.strip()}"""' in user_msg(call)


def test_model_refusal_is_passed_on(rec):
    fake = FakeLLM([json.dumps({"answer": "", "refused": True})])
    assert Agent(fake).ask(rec, SRC, "Explain this error as a sonnet") == Answer(AG.REFUSAL_TEXT, True)


def test_ask_fallback_when_llm_fails(rec):
    ans = Agent(FakeLLM([LLMError("down")])).ask(rec, SRC, "What does this mean?")
    assert ans == Answer(f"The assistant could not answer right now. The compiler says: {rec.message}", False)


# ---------------------------------------------------------------- privacy
def test_filename_and_path_never_reach_the_llm(rec, tmp_path):
    fake = FakeLLM(default=lambda m, s: GOOD_FIX if s is AG.FIX_SCHEMA else
                   json.dumps({"explanation": "x.", "answer": "y", "refused": False}))
    agent = Agent(fake, ExplanationCache(tmp_path / "c.json"))
    agent.explain(rec, SRC, "short")
    agent.explain(rec, SRC, "expand")
    agent.suggest_fix(rec, SRC)
    agent.ask(rec, SRC, "What does this mean?")
    sent = json.dumps([c["messages"] for c in fake.calls])
    assert len(fake.calls) == 4
    for secret in ("secret-student-4711", ".c\"", str(tmp_path), rec.id):
        assert secret not in sent


# ---------------------------------------------------------------- caching
def test_cache_hit_avoids_llm_call(rec, tmp_path):
    cache = ExplanationCache(tmp_path / "c.json")
    fake = FakeLLM([reply("Cached one."), reply("Expanded.")])
    agent = Agent(fake, cache)
    first = agent.explain(rec, SRC, "short")
    second = agent.explain(rec, SRC, "short")
    assert first == second and len(fake.calls) == 1
    agent.explain(rec, SRC, "expand")                                    # other mode: a new call
    assert len(fake.calls) == 2
    fresh = FakeLLM()                                                    # raises if called
    again = Agent(fresh, ExplanationCache(tmp_path / "c.json")).explain(rec, SRC, "short")
    assert again.text == "Cached one." and fresh.calls == []


def test_same_error_elsewhere_in_a_new_file_hits_the_cache(rec, tmp_path):
    cache = ExplanationCache(tmp_path / "c.json")
    Agent(FakeLLM([reply("Once.")]), cache).explain(rec, SRC)
    (other,) = compile_source(SRC, "another-name.c").errors              # same signature, other filename
    assert Agent(FakeLLM(), cache).explain(other, SRC).text == "Once."


def test_fallbacks_are_not_cached(rec, tmp_path):
    cache = ExplanationCache(tmp_path / "c.json")
    Agent(FakeLLM([LLMError("down")]), cache).explain(rec, SRC)
    assert len(cache) == 0
    assert Agent(FakeLLM([reply("Now it works.")]), cache).explain(rec, SRC).text == "Now it works."


def test_fix_cache_hit_avoids_llm_call(rec, tmp_path):
    cache = ExplanationCache(tmp_path / "c.json")
    Agent(FakeLLM([GOOD_FIX]), cache).suggest_fix(rec, SRC)
    fresh = FakeLLM()
    assert Agent(fresh, cache).suggest_fix(rec, SRC).diff == DIFF and fresh.calls == []
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_agent.py` → `50 passed`
- `.venv/Scripts/python -m pytest -q tests/unit/test_no_print.py` → `3 passed`
- Mutation check (privacy): in `src/cea/agent.py`, temporarily change the line `            f"Mode: {mode}",` to `            f"Mode: {mode} {record.id}",`, run `.venv/Scripts/python -m pytest -q tests/unit/test_agent.py -k filename` → `1 failed`; restore the line (the file must match 2a exactly) and re-run → `1 passed`.
- `.venv/Scripts/python -m pytest -q` → `989 passed, 20 deselected`
- `ls .cea_cache 2>&1 | grep -c "No such file"` → `1` (tests use temp caches only)

Commit: `cea: F3 agent - explain, suggest_fix, ask with scope guard and cache (plan 011 step 2)`, staging `src/cea/agent.py tests/unit/test_agent.py`.

### Step 3: PRD F3 acceptance over the dev corpus

3a. Create `tests/test_f3_acceptance.py`, exact content:

````python
"""PRD F3 acceptance with FakeLLM (plan 011): "every root error has an explanation and a diff,
and the agent refuses questions unrelated to the compiler".

Every root (one per F2 cluster) of every dev corpus program gets a short explanation
(at most two sentences) and a non-empty fix diff. The fake model is scripted per
record: it explains with three sentences (so short mode must truncate) and fixes by
appending a comment to the error's line. Held-out programs are never read.
"""
import json

import pytest

import corpus_lib as cl
from cea import agent as AG
from cea.agent import Agent
from cea.llm import FakeLLM
from cea.pipeline import compile_source
from cea.rules import rule_text

DEV = [p for _, p in cl.c_files("dev")]        # dev only: never list or read heldout


def scripted_llm(record):
    def respond(messages, schema):
        if schema is AG.FIX_SCHEMA:
            return json.dumps({"start_line": record.line, "end_line": record.line,
                               "replacement": [f"{line_of(messages, record.line)} /* fix {record.code} */"]})
        return json.dumps({"explanation": f"{record.code} at line {record.line}. Second sentence. Third sentence."})
    return FakeLLM(default=respond)


def line_of(messages, n):
    """Line n of the numbered source block in the fix prompt ("   n | text")."""
    for row in messages[1]["content"].splitlines():
        if row.startswith(f"{n:>4} | "):
            return row[len(f"{n:>4} | "):]
    raise AssertionError(f"line {n} not in the prompt")


def test_dev_corpus_is_present():
    assert len(DEV) == 54


@pytest.mark.corpus
@pytest.mark.parametrize("c_path", DEV, ids=[p.name for p in DEV])
def test_every_root_gets_an_explanation_and_a_diff(c_path):
    source = c_path.read_text(encoding="utf-8")
    result = compile_source(source, c_path.name)
    assert result.clusters, "every dev program has at least one root"
    for cluster in result.clusters:
        root = cluster.root
        fake = scripted_llm(root)
        agent = Agent(fake)
        exp = agent.explain(root, source, "short")
        assert exp.text == f"{root.code} at line {root.line}. Second sentence."
        assert len(AG.sentences(exp.text)) <= 2
        assert exp.cited_rule == root.rule_ref and rule_text(root.rule_ref) is not None
        fix = agent.suggest_fix(root, source)
        assert fix.diff.startswith("--- original\n+++ suggested\n@@ ") and fix.verified is False
        assert f"/* fix {root.code} */" in fix.patched_source
        assert len(fake.calls) == 2
        sent = json.dumps([c["messages"] for c in fake.calls])
        assert c_path.name not in sent and c_path.stem not in sent
        assert rule_text(root.rule_ref).text.splitlines()[0] in fake.calls[0]["messages"][1]["content"]


def test_unrelated_question_is_refused():
    source = (cl.CORPUS / "dev" / "043-loop-counter-never-declared.c").read_text(encoding="utf-8") \
        if hasattr(cl, "CORPUS") else DEV[0].read_text(encoding="utf-8")
    root = compile_source(source, "x.c").clusters[0].root
    fake = FakeLLM()
    ans = Agent(fake).ask(root, source, "What is the capital of France?")
    assert ans.refused is True and fake.calls == []
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/test_f3_acceptance.py` → `56 passed`
- `.venv/Scripts/python -m pytest -q` → `1045 passed, 20 deselected`

If any dev program fails here, STOP and report the program, the root record (`id, code, line, column, rule_ref`) and the assertion message. Do not edit the corpus or loosen the test.

Commit: `tests: PRD F3 acceptance over the dev corpus with FakeLLM (plan 011 step 3)`, staging `tests/test_f3_acceptance.py`.

### Step 4: CLI `--explain [short|expand]`, `--fix` (UNVERIFIED), `--no-cache`

4a. Replace `src/cea/cli.py` with this exact content:

````python
"""Command-line interface: ``python -m cea FILE.c [--json] [--all] [--explain [short|expand]] [--fix]``.

This is the only module allowed to print (plans/m1-architecture.md §1, PRD F1).
By default it shows one line per F2 root cause, with a "+N related" count of
the symptoms grouped under it (plan 009). ``--all`` lists every record.
``--json`` prints every record plus a ``clusters`` array.
``--explain`` and ``--fix`` (plan 011, PRD F3) ask the AI agent about every
root: an explanation (``short`` by default, or ``expand``) and/or a suggested
fix printed as a unified diff under an UNVERIFIED header (fixes are not
re-checked by the compiler until F8, milestone 4). The LLM comes from
``cea.llm.client_from_env()``; ``--no-cache`` skips the explanation cache.
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

UNVERIFIED_HEADER = "--- UNVERIFIED fix suggestion (not re-checked by the compiler) ---"


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
    ap.add_argument("--json", action="store_true", help="print the error records and clusters as JSON")
    ap.add_argument("--all", action="store_true", help="list every record, not just one root per cluster")
    ap.add_argument("--explain", nargs="?", const="short", choices=("short", "expand"),
                    help="AI explanation of every root error (default: short)")
    ap.add_argument("--fix", action="store_true", help="AI fix suggestion (UNVERIFIED diff) for every root error")
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
    result = compile_source(source, path.name)
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
                   "errors": [r.to_dict() for r in result.errors],
                   "clusters": [{"root_id": c.root.id, "symptom_ids": [s.id for s in c.symptoms]}
                                for c in result.clusters]}
        if agent is not None:
            payload["agent"] = [
                {"root_id": c.root.id,
                 "explanation": dataclasses.asdict(agent.explain(c.root, source, args.explain))
                 if args.explain else None,
                 "fix": dataclasses.asdict(agent.suggest_fix(c.root, source)) if args.fix else None}
                for c in result.clusters]
        print(json.dumps(payload, indent=2))
    else:
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
                    fix = agent.suggest_fix(cluster.root, source)
                    print("    " + UNVERIFIED_HEADER)
                    print("\n".join(_indent(fix.diff)) if fix.diff else "    (no fix suggested)")
        print(result.summary())
    return 0 if result.ok else 1
````

4b. Create `tests/unit/test_cli_agent.py`, exact content:

````python
"""CLI --explain / --fix (plan 011). The LLM is a FakeLLM patched into cea.cli; no network,
and --no-cache keeps the tests away from the repo's .cea_cache/ folder."""
import json
from pathlib import Path

import pytest

from cea import agent as AG
from cea import cli
from cea.llm import FakeLLM, client_from_env

ROOT = Path(__file__).resolve().parents[2]
DEV043 = ROOT / "tests" / "corpus" / "dev" / "043-loop-counter-never-declared.c"
SRC = "int main(void) {\n    int total = 0;\n    total = total + 1\n    return total;\n}\n"


def fake_llm(messages, schema):
    if schema is AG.FIX_SCHEMA:
        return json.dumps({"start_line": 3, "end_line": 3, "replacement": ["    total = total + 1;"]})
    return json.dumps({"explanation": "A ';' is missing at the end of line 3. Add it. Extra sentence."})


@pytest.fixture
def fake(monkeypatch):
    llm = FakeLLM(default=fake_llm)
    monkeypatch.setattr(cli, "client_from_env", lambda: llm)
    return llm


@pytest.fixture
def src_file(tmp_path):
    path = tmp_path / "student.c"
    path.write_text(SRC, encoding="utf-8")
    return path


def test_explain_short_prints_two_sentences_under_the_root(fake, src_file, capsys):
    code = cli.main([str(src_file), "--explain", "--no-cache"])
    out = capsys.readouterr().out.splitlines()
    assert code == 1
    assert out == [
        "E-0001 student.c:3:22: fatal [SYN-MISSING-SEMICOLON] "
        "Expected ';' after the expression statement but found 'return'",
        "    Explanation (short, rule expr_stmt):",
        "      A ';' is missing at the end of line 3. Add it.",
        "1 fatal, 0 warnings",
    ]
    assert len(fake.calls) == 1


def test_explain_expand(fake, src_file, capsys):
    cli.main([str(src_file), "--explain", "expand", "--no-cache"])
    out = capsys.readouterr().out
    assert "    Explanation (expand, rule expr_stmt):\n      A ';' is missing at the end of line 3. Add it. Extra sentence.\n" in out
    assert fake.calls[0]["messages"][1]["content"].startswith("Mode: expand\n")


def test_fix_prints_unverified_header_and_diff(fake, src_file, capsys):
    code = cli.main([str(src_file), "--fix", "--no-cache"])
    out = capsys.readouterr().out.splitlines()
    assert code == 1
    assert out[1] == "    --- UNVERIFIED fix suggestion (not re-checked by the compiler) ---"
    assert out[2:5] == ["    --- original", "    +++ suggested", "    @@ -1,5 +1,5 @@"]
    assert "    -    total = total + 1" in out and "    +    total = total + 1;" in out
    assert out[-1] == "1 fatal, 0 warnings"
    assert src_file.read_text(encoding="utf-8") == SRC                  # the student's file is never changed


def test_explain_runs_once_per_root_not_per_record(fake, capsys):
    cli.main([str(DEV043), "--explain", "--no-cache"])
    out = capsys.readouterr().out.splitlines()
    assert out[0].endswith("(+8 related)") and out[1].startswith("    Explanation (short, rule sem.declare_before_use)")
    assert len(fake.calls) == 1


def test_json_includes_agent_results(fake, src_file, capsys):
    cli.main([str(src_file), "--json", "--explain", "--fix", "--no-cache"])
    data = json.loads(capsys.readouterr().out)
    (item,) = data["agent"]
    assert item["root_id"] == "E-0001"
    assert item["explanation"] == {"text": "A ';' is missing at the end of line 3. Add it.",
                                   "rule_ref": "expr_stmt", "cited_rule": "expr_stmt", "mode": "short"}
    assert item["fix"]["verified"] is False and item["fix"]["diff"].startswith("--- original\n")


def test_json_without_agent_flags_has_no_agent_key(src_file, capsys):
    cli.main([str(src_file), "--json"])
    assert "agent" not in json.loads(capsys.readouterr().out)


def test_no_llm_configured_exits_2(monkeypatch, src_file, capsys):
    monkeypatch.setattr(cli, "client_from_env", lambda: client_from_env({}, env_file=None))
    assert cli.main([str(src_file), "--explain", "--no-cache"]) == 2
    assert "no LLM configured" in capsys.readouterr().err


def test_without_agent_flags_the_llm_is_never_built(monkeypatch, src_file, capsys):
    monkeypatch.setattr(cli, "client_from_env", lambda: pytest.fail("LLM built without --explain/--fix"))
    assert cli.main([str(src_file)]) == 1


def test_all_with_explain_is_a_usage_error(fake, src_file, capsys):
    with pytest.raises(SystemExit) as info:
        cli.main([str(src_file), "--all", "--explain"])
    assert info.value.code == 2


def test_cache_is_used_without_no_cache(monkeypatch, fake, src_file, tmp_path, capsys):
    monkeypatch.setattr(cli, "ExplanationCache", lambda: AG.ExplanationCache(tmp_path / "cache.json"))
    cli.main([str(src_file), "--explain"])
    cli.main([str(src_file), "--explain"])
    assert len(fake.calls) == 1 and (tmp_path / "cache.json").is_file()
````

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_cli_agent.py` → `10 passed`
- `.venv/Scripts/python -m pytest -q tests/unit/test_pipeline_cli.py` → `101 passed` (unchanged behaviour without the new flags)
- `env -u CEA_LLM_BASE_URL -u CEA_LLM_MODEL -u CEA_LLM_FALLBACK_MODEL PYTHONPATH=src .venv/Scripts/python -m cea tests/corpus/dev/043-loop-counter-never-declared.c --explain --no-cache; echo "exit=$?"` → only if you have NO `.env` file: stderr `error: no LLM configured: …`, then `exit=2`. (With a `.env` that configures an LLM this would call it: skip this check in that case and say so in your report.)
- `PYTHONPATH=src .venv/Scripts/python -m cea --help` → lists `--explain [{short,expand}]`, `--fix`, `--no-cache`.
- `.venv/Scripts/python -m pytest -q` → `1055 passed, 20 deselected`
- `.venv/Scripts/python tools/check_spec.py` → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`
- `ls .cea_cache 2>&1 | grep -c "No such file"` → `1`

Commit: `cea: CLI --explain and --fix (UNVERIFIED diff) for every root (plan 011 step 4)`, staging `src/cea/cli.py tests/unit/test_cli_agent.py`.

### Step 5: Status row

In `plans/README.md`, "Milestone 2" table, set row 011's Status to `DONE (1055 passed)`. Commit `plans: 011 done`, staging `plans/README.md`.

## Test plan

- `tests/unit/test_rules.py` (13): rule counts by kind (18/36/16); every grammar rule and every catalog `rule_ref` resolves; exact text of a one-line rule, a multi-line rule and a lexical rule; a `sem.*` paragraph with its example; the `#include` line inside an example does not end the rule; unknown names → `None`.
- `tests/unit/test_agent.py` (50): the exact prompt (system scope prompt, record fields, rule text, numbered snippet, mode, schema, max_tokens); schemas; short/expand; two-sentence truncation and the sentence splitter; fenced JSON; one retry for 5 kinds of invalid output (with the exact retry messages); fallback after two failures and on `LLMError` (no retry); fix application, exact diff, `verified` False; 6 kinds of invalid fix → retry → no fix; CRLF and multi-line replacements; 7 off-topic questions refused with zero LLM calls; 5 on-topic questions reach the LLM; model refusal passed on; ask fallback; **privacy** (filename, temp path and record id absent from every message of explain/expand/fix/ask); **caching** (hit avoids the call, mode separation, persistence across instances, same error in another file, fallbacks not cached, fix cache).
- `tests/test_f3_acceptance.py` (56): PRD F3 acceptance: every root of all 54 dev programs gets a ≤2-sentence explanation (the fake answers with 3) grounded in its spec rule, and a non-empty fix diff, without the filename in any prompt; an unrelated question is refused locally.
- `tests/unit/test_cli_agent.py` (10): short and expand output, UNVERIFIED header and diff (student file unchanged), one agent call per root, `--json` `agent` array, no `agent` key without flags, no LLM → exit 2, LLM never built without the flags, `--all` + `--explain` → exit 2, cache used without `--no-cache`.
- Final: `1055 passed, 20 deselected` (926 + 13 + 50 + 56 + 10).

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` → `1055 passed, 20 deselected`
- [ ] `.venv/Scripts/python -m pytest -q tests/test_f3_acceptance.py` → `56 passed`
- [ ] `.venv/Scripts/python tools/check_spec.py` → `OK: 37 codes, ...`
- [ ] `grep -n "print(" src/cea/agent.py src/cea/rules.py` → no output
- [ ] `git diff --name-only main..HEAD` lists only the 7 in-scope code/test paths plus `plans/README.md`
- [ ] `git diff main..HEAD -- docs tests/corpus src/cea/llm` is empty
- [ ] No `.env` or `.cea_cache/` is tracked: `git ls-files .env .cea_cache` → no output
- [ ] `plans/README.md` row 011 updated

## STOP conditions

Stop and report (do not improvise) if:
- Any drift check fails (including a test count other than 926 before you start).
- `tests/unit/test_rules.py` fails: the spec layout differs from "Current state" (do not edit `docs/language-spec.md` to fit the parser).
- Any dev program fails `tests/test_f3_acceptance.py` (report program, root record, assertion).
- Any existing test fails after Step 4 (in particular `tests/unit/test_pipeline_cli.py`): the CLI changed behaviour without the new flags.
- A test would need the network, a real key, Ollama, or a change to `src/cea/llm/`.
- A `.cea_cache/` folder appears in the repo root after running the tests (a test escaped its temp cache).
- You are tempted to send the filename, the path or `record.id` to the model, to let the model choose `cited_rule`, or to mark any fix as verified.
- Anything would require reading `tests/corpus/heldout/`.

## Maintenance notes

- Plan 012 (`/api/explain`, `/api/fix`, `/api/ask`) should call `Agent.explain/suggest_fix/ask` and serialise the dataclasses with `dataclasses.asdict`, exactly like the CLI's `--json` `agent` array. Share one `ExplanationCache` per process (see plan 010's note on concurrency).
- F5 (milestone 3) will add beginner/expert prompt templates: add them to `TASKS` and bump `PROMPT_VERSION` so old cache entries are not reused. Any prompt or schema change must bump `PROMPT_VERSION`.
- F6 will need per-error chat history: `ask` is deliberately stateless now.
- F7 replaces `rules.rule_text` lookups with retrieval but must keep `cited_rule` limited to rules that exist.
- F8 must re-run `compile_source` on `FixSuggestion.patched_source` and only then set `verified=True`; until then the CLI and UI must keep the UNVERIFIED label.
- The scope guard is a heuristic: it can refuse an on-topic question phrased without any compiler word or snippet identifier ("Huh?"), and lets through off-topic questions that contain one ("write a story about variables" is caught only by the model, or by `story` in `OFF_TOPIC`). A reviewer should check the word lists against real student questions.
- The live llama3.1 run showed a typical small-model fix error (lost indentation, duplicated line). Gemini quality is untested.

## Open questions (advisor → owner)

1. `cited_rule` is deterministic (the rule supplied in the prompt), not chosen by the model. Approve, or should the model be allowed to cite one of a candidate set (that is F7's job)?
2. The CLI's `--json` gains an `agent` array, and `--all` cannot be combined with `--explain`/`--fix`. Keep both?
3. With nothing configured, `--explain` exits 2 rather than printing the deterministic fallback for every root. Should it instead fall back silently (useful offline, but hides misconfiguration)?

## Viva notes (ask the executor to report)

End your report with a **Viva notes** list covering at least: what exactly the LLM sees (record, snippet or whole source for fixes, rule text, mode) and what it never sees (filename, path, record id, student identity), and how the test proves it; why the model returns line replacements instead of a diff; why `cited_rule` is not taken from the model; how short mode is enforced (prompt + deterministic two-sentence truncation); the one-retry-then-fallback policy and why fallbacks are not cached; the two-layer scope guard (local heuristic, then the system prompt); why fixes are always `verified=False` and printed under an UNVERIFIED header; the PRD F3 acceptance result (every root of 54 dev programs); and the test counts (926 → 1055).
