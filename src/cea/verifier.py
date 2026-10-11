"""PRD F8: the self-verifying fix engine.

``verify_fix`` asks the agent for a patch, applies it to a COPY of the source string
(never a file), re-runs the whole compiler pipeline on the copy and accepts the patch
only when all of these hold:

(a) the original error is gone. It is matched by (code, rule_ref) near its location
    after the line is mapped through the diff (``difflib`` opcodes), not by exact line;
(b) no NEW fatal error appears anywhere (every other fatal error of the original is
    matched to the new result the same way; an unmatched new fatal is "new");
(c) the guardrails hold: every changed line lies within GUARD_LINES of the error's
    line or span, at most MAX_CHANGED_LINES lines change, and the changed region does
    not lose identifiers or statements (so deleting or commenting out code is rejected).

A rejected patch is retried with the reason and the new errors as context, up to
``max_attempts`` times, within an overall ``timeout`` (seconds). After that there is
no fix: ``diff`` is empty, ``patched_source`` is the original and ``verified`` is False.
Nothing here prints.
"""
from __future__ import annotations

import difflib
import threading
import time
from collections.abc import Callable

from cea.agent import Agent, FixSuggestion
from cea.diagnostics import ErrorSink
from cea.lexer import lex
from cea.pipeline import CompileResult, compile_source
from cea.records import ErrorRecord
from cea.tokens import TokenKind

MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT = 10.0          # seconds, overall
GUARD_LINES = 3                 # a patch may touch lines within +-3 of the error's line or span
MAX_CHANGED_LINES = 6
MATCH_SLACK = 1                 # lines of slack when matching the error to its mapped location
OTHER_SLACK = 2                 # slack for matching the other pre-existing fatal errors
DISPLAY_NAME = "input.c"


# ---------------------------------------------------------------- line mapping
def _opcodes(old: str, new: str) -> tuple[list, int, int]:
    a, b = old.splitlines(), new.splitlines()
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    return ops, len(a), len(b)


def map_lines(old: str, new: str, first: int, last: int | None = None) -> tuple[int, int]:
    """Map the 1-based inclusive old line range [first, last] to a 1-based range of ``new``.

    Lines in an unchanged block shift with the block; a line inside a replaced block maps to
    that block's new lines; a line inside a deleted block maps to the two lines around the gap.
    """
    last = first if last is None else last
    ops, n_old, n_new = _opcodes(old, new)

    def one(line: int) -> tuple[int, int]:
        k = line - 1
        if k >= n_old:                                    # at or after EOF: shift by the length change
            return line + (n_new - n_old), line + (n_new - n_old)
        for tag, i1, i2, j1, j2 in ops:
            if i1 <= k < i2:
                if tag == "equal":
                    return j1 + (k - i1) + 1, j1 + (k - i1) + 1
                if j2 == j1:                              # deleted block
                    return j1, j1 + 1
                return j1 + 1, j2
        return line, line

    lows, highs = zip(*(one(n) for n in range(first, last + 1)))
    lo = max(1, min(lows))
    return lo, max(lo, max(highs))


def changed_blocks(old: str, new: str) -> list[tuple[int, int, int, int]]:
    """(i1, i2, j1, j2) 0-based half-open ranges of every non-equal opcode."""
    return [(i1, i2, j1, j2) for tag, i1, i2, j1, j2 in _opcodes(old, new)[0] if tag != "equal"]


# ---------------------------------------------------------------- guardrails
def _counts(text: str) -> tuple[int, int]:
    """(identifier tokens, ';' tokens) of a code fragment; comments contribute nothing."""
    toks = lex(text, ErrorSink(text)).tokens
    idents = sum(1 for t in toks if t.kind is TokenKind.IDENT)
    stmts = sum(1 for t in toks if t.kind is TokenKind.PUNCT and t.text == ";")
    return idents, stmts


def check_guardrails(record: ErrorRecord, old: str, new: str) -> str | None:
    """None when the patch passes the guardrails, else a short reason."""
    blocks = changed_blocks(old, new)
    if not blocks:
        return "the patch changes nothing"
    n_old = len(old.splitlines())
    lo, hi = record.line - GUARD_LINES, max(record.line, record.span_end.line) + GUARD_LINES
    changed = 0
    for i1, i2, j1, j2 in blocks:
        changed += max(i2 - i1, j2 - j1)
        touched = range(i1 + 1, i2 + 1) if i2 > i1 else [max(1, i1), min(max(n_old, 1), i1 + 1)]   # insert: neighbours
        if any(not lo <= line <= hi for line in touched):
            return f"the patch touches lines more than {GUARD_LINES} lines away from the error (line {record.line})"
    if changed > MAX_CHANGED_LINES:
        return f"the patch changes {changed} lines (at most {MAX_CHANGED_LINES} allowed)"
    a, b = old.splitlines(), new.splitlines()
    old_text = "\n".join(line for i1, i2, _, _ in blocks for line in a[i1:i2])
    new_text = "\n".join(line for _, _, j1, j2 in blocks for line in b[j1:j2])
    if ("//" in new_text or "/*" in new_text) and not ("//" in old_text or "/*" in old_text):
        return "the patch comments code out"
    (oi, os_), (ni, ns) = _counts(old_text), _counts(new_text)
    if ni < oi or ns < os_:
        return "the patch deletes code (fewer identifiers or statements in the changed region)"
    return None


# ---------------------------------------------------------------- re-checking the compile result
def _near(rec: ErrorRecord, key: tuple[str, str], lo: int, hi: int) -> bool:
    return (rec.code, rec.rule_ref) == key and lo <= rec.line <= hi


def original_error_remains(record: ErrorRecord, old: str, new: str, result: CompileResult) -> bool:
    lo, hi = map_lines(old, new, record.line, max(record.line, record.span_end.line))
    key = (record.code, record.rule_ref)
    return any(_near(r, key, lo - MATCH_SLACK, hi + MATCH_SLACK) for r in result.errors)


def new_fatal_errors(old_result: CompileResult, record: ErrorRecord, old: str, new: str,
                     result: CompileResult) -> list[ErrorRecord]:
    """Fatal errors of ``result`` that match none of the original fatal errors other than ``record``."""
    pool = [r for r in result.errors if r.severity == "fatal"]
    for orig in old_result.errors:
        if orig.severity != "fatal" or orig.id == record.id:
            continue
        lo, hi = map_lines(old, new, orig.line, max(orig.line, orig.span_end.line))
        for r in pool:
            if _near(r, (orig.code, orig.rule_ref), lo - OTHER_SLACK, hi + OTHER_SLACK):
                pool.remove(r)
                break
    return pool


# ---------------------------------------------------------------- the loop
def _failure(source: str, attempts: int, reason: str) -> FixSuggestion:
    return FixSuggestion(diff="", patched_source=source, verified=False, attempts=attempts, reason=reason)


def _describe(records: list[ErrorRecord]) -> str:
    return "; ".join(f"{r.code} at line {r.line}: {r.message}" for r in records[:5])


def _call_with_deadline(fn: Callable[[], FixSuggestion], seconds: float) -> FixSuggestion | None:
    """Run ``fn`` in a daemon thread; None when it does not finish in time (the thread is abandoned)."""
    box: list = []

    def run() -> None:
        try:
            box.append(fn())
        except BaseException as exc:      # noqa: BLE001 - re-raised below, in the caller's thread
            box.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(max(seconds, 0.0))
    if worker.is_alive() or not box:
        return None
    if isinstance(box[0], BaseException):
        raise box[0]
    return box[0]


def verify_fix(agent: Agent, record: ErrorRecord, source: str, *, max_attempts: int = MAX_ATTEMPTS,
               timeout: float = DEFAULT_TIMEOUT,
               compile_fn: Callable[[str, str], CompileResult] = compile_source) -> FixSuggestion:
    """A verified fix for ``record`` (a root error of ``source``), or an unverified FixSuggestion with no diff."""
    deadline = time.monotonic() + timeout
    base = compile_fn(source, DISPLAY_NAME)
    feedback: str | None = None
    reason = "no patch was proposed"
    for attempt in range(1, max_attempts + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _failure(source, attempt - 1, f"timed out after {timeout:g}s")
        proposal = _call_with_deadline(
            lambda: agent.suggest_fix(record, source, feedback=feedback, store=False), remaining)
        if proposal is None:
            return _failure(source, attempt, f"timed out after {timeout:g}s")
        if not proposal.diff or proposal.patched_source == source:
            reason, feedback = "no patch was proposed", None
            continue
        patched = proposal.patched_source                       # a copy; the caller's text is never touched
        bad = check_guardrails(record, source, patched)
        if bad:
            reason = bad
            feedback = f"Your previous edit was rejected: {bad}. Make a small edit that fixes the error without deleting code."
            continue
        result = compile_fn(patched, DISPLAY_NAME)
        if original_error_remains(record, source, patched, result):
            reason = "the original error is still there"
            same = [r for r in result.errors if r.code == record.code]
            feedback = "Your previous edit was rejected: the same error is still reported (" + _describe(same) + ")."
            continue
        fresh = new_fatal_errors(base, record, source, patched, result)
        if fresh:
            reason = f"the patch introduces a new error ({fresh[0].code} at line {fresh[0].line})"
            feedback = "Your previous edit was rejected: it causes new errors: " + _describe(fresh) + "."
            continue
        agent.remember_fix(record, source, proposal)
        return FixSuggestion(diff=proposal.diff, patched_source=patched, verified=True, attempts=attempt,
                             reason="verified: the error is gone and no new fatal error appears",
                             edit=proposal.edit)
    return _failure(source, max_attempts, reason)
