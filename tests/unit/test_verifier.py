"""PRD F8: the self-verifying fix engine (cea.verifier). FakeLLM is scripted; no network."""
import json
import time

import pytest

from cea import verifier as V
from cea.agent import Agent
from cea.llm import FakeLLM
from cea.pipeline import compile_source

SRC = "int main(void) {\n    int total = 0;\n    total = total + 1\n    return total;\n}\n"      # E-0001: line 3
SRC_B = "int main(void) {\n    int a = 1;\n    b = a;\n    return 0;\n}\n"                      # undeclared b, line 3


def edit(start, end, *lines):
    return json.dumps({"start_line": start, "end_line": end, "replacement": list(lines)})


GOOD = edit(3, 3, "    total = total + 1;")
DELETE_LINE = edit(3, 3)
COMMENT_OUT = edit(3, 3, "    // total = total + 1")
NEW_ERROR = edit(3, 3, "    total = total + 1;", "    zzz = 2;")          # fixes the old error, adds an undeclared name


def root(src):
    return next(c.root for c in compile_source(src, "t.c").clusters if c.root.severity == "fatal")


def run(src, script, **kw):
    llm = FakeLLM(script)
    return V.verify_fix(Agent(llm), root(src), src, **kw), llm


def test_correct_fix_is_verified():
    fix, llm = run(SRC, [GOOD])
    assert fix.verified is True and fix.attempts == 1 and len(llm.calls) == 1
    assert fix.patched_source == SRC.replace("+ 1\n", "+ 1;\n") and fix.diff.startswith("--- original\n")
    assert "verified" in fix.reason


def test_the_source_text_is_never_modified():
    original = str(SRC)
    run(SRC, [GOOD])
    assert SRC == original


@pytest.mark.parametrize("bad", [DELETE_LINE, COMMENT_OUT])
def test_deleting_or_commenting_out_the_offending_line_is_rejected(bad):
    fix, llm = run(SRC, [bad] * 3)
    assert fix.verified is False and fix.diff == "" and fix.patched_source == SRC and fix.attempts == 3
    assert "deletes code" in fix.reason or "comments code out" in fix.reason


def test_a_fix_that_introduces_a_new_error_is_rejected():
    fix, llm = run(SRC, [NEW_ERROR] * 3)
    assert fix.verified is False and fix.diff == ""
    assert "new error" in fix.reason and "SEM-UNDECLARED-VAR" in fix.reason


def test_retry_succeeds_on_the_second_attempt_and_gets_feedback():
    fix, llm = run(SRC, [NEW_ERROR, GOOD])
    assert fix.verified is True and fix.attempts == 2 and len(llm.calls) == 2
    first, second = (c["messages"][1]["content"] for c in llm.calls)
    assert "rejected" not in first
    assert "Your previous edit was rejected" in second and "SEM-UNDECLARED-VAR" in second


def test_three_failures_give_no_fix():
    fix, llm = run(SRC, [DELETE_LINE, NEW_ERROR, edit(1, 1, "int main(void){")])
    assert (fix.verified, fix.diff, fix.patched_source, fix.attempts) == (False, "", SRC, 3)
    assert len(llm.calls) == 3 and fix.reason


def test_invalid_model_output_gives_no_fix():
    fix, _ = run(SRC, ["not json"] * 12)
    assert fix.verified is False and fix.diff == "" and fix.reason == "no patch was proposed"


def test_timeout_is_enforced():
    def slow(messages, schema):
        time.sleep(2)
        return GOOD

    start = time.monotonic()
    fix, _ = run(SRC, [slow], timeout=0.2)
    assert time.monotonic() - start < 1.5
    assert fix.verified is False and fix.diff == "" and "timed out" in fix.reason


def test_timeout_budget_is_shared_across_attempts():
    def slowish(messages, schema):
        time.sleep(0.15)
        return DELETE_LINE

    fix, llm = run(SRC, [slowish] * 5, timeout=0.3)
    assert fix.verified is False and "timed out" in fix.reason and len(llm.calls) <= 3


# ---------------------------------------------------------------- line-shift mapping
def test_map_lines_shifts_with_unchanged_blocks():
    old = "a\nb\nc\nd\n"
    new = "a\nX\nY\nb\nc\nd\n"                      # two lines inserted after line 1
    assert V.map_lines(old, new, 3) == (5, 5)
    assert V.map_lines(old, new, 1) == (1, 1)
    assert V.map_lines(old, new, 2, 3) == (4, 5)


def test_map_lines_inside_a_replaced_or_deleted_block():
    assert V.map_lines("a\nb\nc\n", "a\nB1\nB2\nc\n", 2) == (2, 3)
    assert V.map_lines("a\nb\nc\n", "a\nc\n", 2) == (1, 2)
    assert V.map_lines("a\nb\n", "a\nb\nz\n", 4) == (5, 5)            # past EOF: shifted by the length change


def test_fix_that_shifts_lines_is_still_verified():
    fix, _ = run(SRC_B, [edit(3, 3, "    int b;", "    b = a;")])
    assert fix.verified is True and fix.attempts == 1


def test_error_that_moved_down_is_still_recognised_as_the_same_error():
    # inserting a line above moves the undeclared 'b' from line 3 to line 4; an exact-line match would miss it
    fix, _ = run(SRC_B, [edit(2, 2, "    int a = 1;", "    int c;")] * 3)
    assert fix.verified is False and fix.reason == "the original error is still there"


# ---------------------------------------------------------------- guardrails
def test_guardrail_patch_far_from_the_error_is_rejected():
    decls = "".join("    int v%d = 0;\n" % i for i in range(8))
    src = "int main(void) {\n" + decls + "    v0 = v0 + 1\n    return v0;\n}\n"      # error on line 10
    far = edit(2, 2, "    int v0 = 0; int q = 0;")
    fix, _ = run(src, [far] * 3)
    assert fix.verified is False and "lines away" in fix.reason


def test_guardrail_at_most_six_changed_lines():
    big = edit(2, 3, *["    int pad%d = 0;" % i for i in range(8)], "    total = total + 1;")
    fix, _ = run(SRC, [big] * 3)
    assert fix.verified is False and "at most 6" in fix.reason


def test_guardrail_checks_directly():
    rec = root(SRC)
    assert V.check_guardrails(rec, SRC, SRC.replace("+ 1\n", "+ 1;\n")) is None
    assert V.check_guardrails(rec, SRC, SRC) == "the patch changes nothing"
    assert "deletes code" in V.check_guardrails(rec, SRC, SRC.replace("    total = total + 1\n", ""))
    assert "comments code out" in V.check_guardrails(rec, SRC, SRC.replace("    total", "    /* total").replace("1\n", "1 */\n"))
