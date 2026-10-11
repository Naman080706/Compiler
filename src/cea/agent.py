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
  difflib. A raw suggestion is never verified: ``cea.verifier.verify_fix`` (F8)
  re-compiles it and is what the API and CLI show to students.
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
from dataclasses import dataclass, field

from cea.llm import ExplanationCache, LLMClient, LLMError
from cea.records import ErrorRecord
from cea.retrieval import Chunk, retrieve
from cea.rules import RuleText, rule_text

PROMPT_VERSION = 4          # part of every cache signature: bump it when a prompt or schema changes
MODES = ("short", "expand")
VERBOSITIES = ("beginner", "expert")    # PRD F5: two prompt templates, one agent
MAX_HISTORY = 6                         # PRD F6: most recent question/answer pairs sent to the model
MAX_HISTORY_CHARS = 600

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
    # "citations" must be in the schema: a schema-constrained decoder (Ollama) cannot emit a field the
    # schema does not list, so without it a local model never cites (found by the milestone-5 evaluation).
    "properties": {"explanation": {"type": "string"}, "citations": {"type": "array"}},
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
    "short": ("Explain this error to a beginner in at most two sentences: say which compiler phase "
              "(lexical, syntax or semantic) caught it, what is wrong and where (line and column). Reply as JSON: {\"explanation\": \"...\"}"),
    "expand": ("Explain this error fully to a beginner: which compiler phase (lexical, syntax or semantic) caught it, what is wrong, where, why the language rule above "
               "forbids it, and how to fix it. Do not include a diff. Reply as JSON: {\"explanation\": \"...\"}"),
    "fix": ("Suggest the smallest edit that fixes only this error. Lines are numbered from 1. Lines "
            "start_line to end_line (inclusive) are replaced by the replacement lines (no line numbers). "
            "Reply as JSON: {\"start_line\": N, \"end_line\": M, \"replacement\": [\"...\"]}"),
    "ask": ("Answer the student's question below about this error in at most four sentences, using only the "
            "error record, source lines, language rule, reference chunks and earlier conversation above. "
            "If it is not "
            "about this error, this program or the course C subset, refuse. "
            "Reply as JSON: {\"answer\": \"...\", \"refused\": false}"),
}
# PRD F5: the expert templates ask for the same facts in one terse line plus the rule name or error code.
CITE_FORMAT = 'Reply as JSON: {"explanation": "...", "citations": ["<chunk id>"]}'
EXPERT_TASKS = {
    "short": ("Expert mode. Reply with ONE terse line (no analogy, no greeting): the compiler phase that caught it, the fault and its "
              "line:column, then the grammar rule or error code in parentheses. " + CITE_FORMAT),
    "expand": ("Expert mode. Reply with one terse line stating the fault, then the grammar rule text or the "
               "semantic rule it violates; at most three short lines in all, no analogy. " + CITE_FORMAT),
}
BEGINNER_NOTE = (" Beginner mode: use plain language, add a short everyday analogy where it helps, and name "
                 "the rule that was violated. Put the ids of the reference chunks you used in \"citations\": "
                 'e.g. {"explanation": "...", "citations": ["<chunk id>"]}.')
MAX_TOKENS = {"short": 300, "expand": 900, "fix": 900, "ask": 500}


@dataclass
class Explanation:
    text: str
    rule_ref: str
    cited_rule: str | None
    mode: str           # "short" | "expand"
    verbosity: str = "beginner"      # "beginner" | "expert" (PRD F5)
    # F7: ids of the retrieved chunks the explanation cites (model citations outside the retrieved set are dropped)
    citations: list[str] = field(default_factory=list, compare=False)


@dataclass
class FixSuggestion:
    diff: str
    patched_source: str
    verified: bool = False      # True only when cea.verifier re-compiled the patch and accepted it (PRD F8)
    attempts: int = 0           # LLM attempts the verifier used (0 for a raw, unverified suggestion)
    reason: str = ""            # why the patch was accepted or rejected (verifier)
    edit: tuple | None = field(default=None, compare=False, repr=False)   # (start_line, end_line, replacement)


@dataclass
class Answer:
    text: str
    refused: bool


def clip_history(history: list[dict] | None) -> list[dict]:
    """The last MAX_HISTORY well-formed {question, answer} turns, each text clipped (F6 history cap)."""
    turns = []
    for turn in history or []:
        q, a = turn.get("question"), turn.get("answer")
        if isinstance(q, str) and isinstance(a, str):
            turns.append({"question": q.strip()[:MAX_HISTORY_CHARS], "answer": a.strip()[:MAX_HISTORY_CHARS]})
    return turns[-MAX_HISTORY:]


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


def is_off_topic(question: str, record: ErrorRecord | None = None, in_thread: bool = False) -> bool:
    """Cheap local pre-check (F3 scope guard). True = refuse without calling the LLM.

    Refuses an empty question, one that names a clearly unrelated topic, and one
    that has no compiler or C vocabulary, no C punctuation and no identifier
    from the error's snippet. Borderline questions pass and the model decides. Inside a thread
    that already has turns (``in_thread``), a short follow-up such as "and then?" is not refused
    for lacking vocabulary; only an empty or clearly unrelated question is.
    """
    q = question.strip()
    if not q or OFF_TOPIC.search(q):
        return True
    words = {w.lower() for w in _WORD.findall(q)}
    if in_thread or words & ON_TOPIC_WORDS or _C_PUNCT.search(q):
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

    def _context(self, record: ErrorRecord, rule: RuleText | None, mode: str, source_block: str,
                 chunks: list[Chunk] | None = None) -> str:
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
        if chunks:
            parts.append("Reference chunks (cite the ids you use):")
            for chunk in chunks:
                body = "(the language rule above)" if chunk.id == f"rule:{record.rule_ref}" else chunk.text
                parts.append(f"  [{chunk.id}]")
                parts.extend("    " + line for line in body.splitlines())
        parts.append(source_block)
        return "\n".join(parts)

    def _snippet_block(self, record: ErrorRecord) -> str:
        return "Source lines:\n" + self._numbered(record.snippet, max(1, record.line - 1))

    def _messages(self, record: ErrorRecord, mode: str, source_block: str, extra: str = "",
                  verbosity: str = "beginner", chunks: list[Chunk] | None = None) -> list[dict]:
        rule = rule_text(record.rule_ref)
        explaining = mode in MODES
        if explaining and verbosity == "expert":
            task = EXPERT_TASKS[mode]
        else:
            task = TASKS[mode] + (BEGINNER_NOTE if explaining else "")
        user = (self._context(record, rule, mode, source_block, chunks)
                + (f"\nVerbosity: {verbosity}" if explaining else "") + "\nTask: " + task + extra)
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
    def fallback_text(record: ErrorRecord, mode: str, verbosity: str = "beginner") -> str:
        """Deterministic explanation from the catalog message (used when the model fails)."""
        message = record.message.rstrip()
        phase = f"{record.phase.capitalize()} phase: "
        if verbosity == "expert":
            return f"{phase}{record.line}:{record.column} {record.code}: {message} ({record.rule_ref})"
        if not message.endswith((".", "!", "?")):
            message += "."
        text = f"{phase}Line {record.line}, column {record.column}: {message}"
        if mode == "expand":
            text += f" This breaks the language rule '{record.rule_ref}'."
            rule = rule_text(record.rule_ref)
            if rule is not None:
                text += "\n\n" + rule.text
        return text

    @staticmethod
    def validate_citations(raw: object, chunks: list[Chunk], record: ErrorRecord) -> list[str]:
        """F7: keep only citations that are ids of the retrieved chunks (order kept, no duplicates).

        If the model cites nothing valid, the explanation is attributed to the chunk it was grounded
        on: the record's own rule chunk, else the first retrieved chunk. Nothing outside the
        retrieved set can ever be returned.
        """
        retrieved = [c.id for c in chunks]
        kept: list[str] = []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, str) and item in retrieved and item not in kept:
                kept.append(item)
        if not kept and retrieved:
            own = f"rule:{record.rule_ref}"
            kept = [own if own in retrieved else retrieved[0]]
        return kept

    @staticmethod
    def _example_note(chunks: list[Chunk], record: ErrorRecord) -> str:
        """F9: the curated fix-pattern chunk for this code as a worked example the student has earned."""
        own = next((c for c in chunks if c.id == f"fix:{record.code}"), None)
        body = ""
        if own is not None:
            body = ("\nWorked example (a common mistake of this kind and its fix):\n"
                    + "\n".join("  " + line for line in own.text.splitlines()))
        return body + ("\nThis student keeps hitting this kind of error: explain it in more detail "
                       "and finish with a short worked example.")

    def explain(self, record: ErrorRecord, source: str, mode: str = "short",
                verbosity: str = "beginner", worked_example: bool = False) -> Explanation:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        if verbosity not in VERBOSITIES:
            raise ValueError(f"verbosity must be one of {VERBOSITIES}, got {verbosity!r}")
        rule = rule_text(record.rule_ref)
        cited = rule.rule_ref if rule is not None else None
        chunks = retrieve(record)
        key = f"{verbosity}/{mode}" + ("/example" if worked_example else "")     # F9: fuller depth is its own entry
        sig = self._signature(record)
        hit = self.cache.get(sig, key) if self.cache is not None else None
        if hit is not None and isinstance(hit.get("text"), str):
            return Explanation(hit["text"], record.rule_ref, cited, mode, verbosity,
                               self.validate_citations(hit.get("citations"), chunks, record))
        extra = self._example_note(chunks, record) if worked_example else ""
        messages = self._messages(record, mode, self._snippet_block(record), extra, verbosity=verbosity, chunks=chunks)
        obj = self._call_json(messages, EXPLAIN_SCHEMA, mode, check=lambda o: bool(o["explanation"].strip()))
        if obj is None:
            text = self.fallback_text(record, mode, verbosity)
        else:
            text = obj["explanation"].strip()
        if mode == "short":
            text = first_sentences(text, 1 if verbosity == "expert" else 2)
        citations = self.validate_citations(obj.get("citations") if obj is not None else None, chunks, record)
        if obj is not None and self.cache is not None:
            self.cache.put(sig, key, {"text": text, "citations": citations})
        return Explanation(text, record.rule_ref, cited, mode, verbosity, citations)

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

    def _fix_sig(self, record: ErrorRecord, source: str) -> dict:
        return dict(self._signature(record), source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest())

    def suggest_fix(self, record: ErrorRecord, source: str, feedback: str | None = None,
                    store: bool = True) -> FixSuggestion:
        """One raw patch proposal (never verified). ``feedback`` (F8 retry) is why the last patch was
        rejected; it bypasses the cache. ``store=False`` keeps the proposal out of the cache."""
        line_count = len(source.splitlines())

        def valid(o: dict) -> bool:
            if not 1 <= o["start_line"] <= o["end_line"] <= line_count:
                return False
            return self.apply_fix(source, o["start_line"], o["end_line"], o["replacement"]) != source

        sig = self._fix_sig(record, source)
        hit = self.cache.get(sig, "fix") if self.cache is not None and feedback is None else None
        obj = hit if hit is not None and matches_schema(hit, FIX_SCHEMA) and valid(hit) else None
        if obj is None:
            block = "Source (whole file):\n" + self._numbered(source, 1)
            extra = ("\n" + feedback + " Propose a different edit.") if feedback else ""
            obj = self._call_json(self._messages(record, "fix", block, extra), FIX_SCHEMA, "fix", check=valid)
            if obj is None:
                return FixSuggestion(diff="", patched_source=source, verified=False)
            if self.cache is not None and store:
                self.cache.put(sig, "fix", {k: obj[k] for k in ("start_line", "end_line", "replacement")})
        patched = self.apply_fix(source, obj["start_line"], obj["end_line"], obj["replacement"])
        return FixSuggestion(diff=self.unified_diff(source, patched), patched_source=patched, verified=False,
                             edit=(obj["start_line"], obj["end_line"], list(obj["replacement"])))

    def remember_fix(self, record: ErrorRecord, source: str, fix: FixSuggestion) -> None:
        """Cache a fix the verifier accepted (raw, unverified proposals are never cached)."""
        if self.cache is not None and fix.edit is not None:
            start, end, replacement = fix.edit
            self.cache.put(self._fix_sig(record, source), "fix",
                           {"start_line": start, "end_line": end, "replacement": replacement})

    # -- ask
    def ask(self, record: ErrorRecord, source: str, question: str, history: list[dict] | None = None) -> Answer:
        """Answer one follow-up about this error from its record, snippet, retrieved docs and prior turns.

        ``history`` is the client's list of ``{"question", "answer"}`` turns for this error; only the
        last MAX_HISTORY are used.
        """
        turns = clip_history(history)
        if is_off_topic(question, record, in_thread=bool(turns)):
            return Answer(REFUSAL_TEXT, refused=True)
        extra = ""
        if turns:
            extra += "\nEarlier conversation about this error:"
            for t in turns:
                extra += f'\n  Student: {t["question"]}\n  Assistant: {t["answer"]}'
        extra += '\nStudent question: """' + question.strip().replace('"""', "'''") + '"""'
        messages = self._messages(record, "ask", self._snippet_block(record), extra, chunks=retrieve(record))
        obj = self._call_json(messages, ASK_SCHEMA, "ask", check=lambda o: bool(o["answer"].strip()) or o["refused"])
        if obj is None:
            return Answer(NO_ANSWER_TEXT.format(message=record.message), refused=False)
        if obj["refused"]:
            return Answer(obj["answer"].strip() or REFUSAL_TEXT, refused=True)
        return Answer(obj["answer"].strip(), refused=False)
