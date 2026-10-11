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
