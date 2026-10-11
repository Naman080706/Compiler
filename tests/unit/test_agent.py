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
        assert schema["type"] == "object" and set(schema["required"]) <= set(schema["properties"]) <= set(schema["required"]) | {"citations"}
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
    assert exp.text == "Syntax phase: Line 3, column 22: Expected ';' after the expression statement but found 'return'."
    assert (exp.rule_ref, exp.cited_rule) == ("expr_stmt", "expr_stmt")


def test_expand_fallback_includes_the_rule(rec):
    exp = Agent(FakeLLM(default="nope")).explain(rec, SRC, "expand")
    assert exp.text.startswith("Syntax phase: Line 3, column 22: Expected ';'")
    assert "This breaks the language rule 'expr_stmt'.\n\nexpr_stmt      = expression" in exp.text


def test_llm_error_falls_back_without_retry(rec):
    fake = FakeLLM([LLMError("network down")])
    exp = Agent(fake).explain(rec, SRC)
    assert len(fake.calls) == 1 and exp.text.startswith("Syntax phase: Line 3, column 22: ")


def test_fallback_short_text_is_at_most_two_sentences():
    src = "int main(void) {\n    char c = 'ab';\n    return 0;\n}\n"
    r = next(e for e in compile_source(src, "t.c").errors if e.code == "LEX-BAD-CHAR-LITERAL")
    exp = Agent(FakeLLM(default="nope")).explain(r, src)
    assert exp.text == f"Lexical phase: Line 2, column 14: {r.message}."
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
