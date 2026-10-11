"""Milestone 3: F5 verbosity, F6 per-error follow-up Q&A, F7 RAG grounding. FakeLLM only; no network."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cea import agent as AG
from cea import api
from cea.agent import Agent
from cea.catalog import load_catalog
from cea.llm import ExplanationCache, FakeLLM
from cea.pipeline import compile_source
from cea.retrieval import load_index, retrieve
from cea.rules import load_rules

ROOT = Path(__file__).resolve().parents[2]
SRC = "int main(void) {\n    int total = 0;\n    total = total + 1\n    return total;\n}\n"
SRC_UNDECLARED = "int main(void) {\n    x = 1;\n    return 0;\n}\n"


@pytest.fixture
def rec():
    (r,) = compile_source(SRC, "input.c").errors
    return r


def user_msg(call):
    return call["messages"][1]["content"]


def chunk_ids(messages):
    import re
    return re.findall(r"^  \[([^\]]+)\]$", messages[1]["content"], re.MULTILINE)


# ---------------------------------------------------------------- F7 corpus and retrieval
def test_rule_chunks_cover_every_spec_rule_and_are_in_sync():
    index = load_index()
    for name in load_rules():
        assert f"rule:{name}" in index.chunks
    assert sum(1 for c in index.chunks.values() if c.kind != "fix") == len(load_rules())
    assert any(n.startswith("sem.") for n in load_rules())
    check = subprocess.run([sys.executable, str(ROOT / "tools" / "build_rag.py"), "--check"], cwd=ROOT)
    assert check.returncode == 0, "docs/rag/rules.md is stale: run python tools/build_rag.py"


def test_one_fix_pattern_per_catalog_code_tagged_with_code_phase_rule_ref():
    index = load_index()
    catalog = load_catalog()
    assert len(catalog) == 37
    for code, entry in catalog.items():
        chunk = index.get(f"fix:{code}")
        assert chunk is not None, code
        assert (chunk.code, chunk.phase, chunk.rule_ref) == (code, entry.phase, entry.rule_ref)
        assert "Common mistake:" in chunk.text and "Fix:" in chunk.text
    assert sum(1 for c in index.chunks.values() if c.kind == "fix") == 37


def test_retrieval_is_keyed_and_deterministic(rec):
    first = retrieve(rec)
    assert [c.id for c in first][:2] == ["rule:expr_stmt", "fix:SYN-MISSING-SEMICOLON"]
    assert [c.id for c in retrieve(rec)] == [c.id for c in first]
    assert all(c.id in load_index().chunks for c in first)
    assert len(first) <= 2 + 2          # rule, fix pattern and at most two expected-token rules


def test_retrieval_semantic_phase_uses_the_sem_rule():
    (r, *_) = compile_source(SRC_UNDECLARED, "input.c").errors
    ids = [c.id for c in retrieve(r)]
    assert ids == ["rule:sem.declare_before_use", "fix:SEM-UNDECLARED-VAR"]


def test_chromadb_is_not_a_requirement():
    import re
    reqs = (ROOT / "requirements.txt").read_text() + (ROOT / "requirements-dev.txt").read_text()
    assert not re.search(r"chroma", reqs, re.IGNORECASE)


# ---------------------------------------------------------------- F5 verbosity
def verbosity_llm():
    def respond(messages, schema):
        if "Verbosity: expert" in messages[1]["content"]:
            return json.dumps({"explanation": "3:22 missing ';' (expr_stmt)", "citations": ["rule:expr_stmt"]})
        return json.dumps({"explanation": "Think of ';' as the full stop of a sentence. Line 3 lacks it. "
                                          "The rule expr_stmt needs one.", "citations": ["rule:expr_stmt"]})
    return FakeLLM(default=respond)


def test_same_error_gives_different_text_per_verbosity_with_same_facts(rec):
    agent = Agent(verbosity_llm())
    beginner = agent.explain(rec, SRC, "short", "beginner")
    expert = agent.explain(rec, SRC, "short", "expert")
    assert beginner.text != expert.text
    assert len(expert.text) < len(beginner.text)
    assert (beginner.rule_ref, beginner.cited_rule) == (expert.rule_ref, expert.cited_rule) == ("expr_stmt", "expr_stmt")
    assert beginner.citations == expert.citations == ["rule:expr_stmt"]
    assert (beginner.verbosity, expert.verbosity) == ("beginner", "expert")


def test_each_verbosity_has_its_own_prompt_template(rec):
    fake = verbosity_llm()
    agent = Agent(fake)
    agent.explain(rec, SRC, "short", "beginner")
    agent.explain(rec, SRC, "short", "expert")
    beginner, expert = (user_msg(c) for c in fake.calls)
    assert "Verbosity: beginner" in beginner and "plain language" in beginner and "analogy" in beginner
    assert "Verbosity: expert" in expert and "ONE terse line" in expert and "analogy" not in expert.split("Task:")[1].replace("no analogy", "")
    assert beginner.split("Task:")[0].replace("beginner", "X") == expert.split("Task:")[0].replace("expert", "X")


def test_expert_expand_template_and_unknown_verbosity(rec):
    fake = verbosity_llm()
    Agent(fake).explain(rec, SRC, "expand", "expert")
    assert "grammar rule text" in user_msg(fake.calls[0])
    with pytest.raises(ValueError):
        Agent(fake).explain(rec, SRC, "short", "novice")


def test_expert_short_is_one_sentence_and_expert_fallback_is_terse(rec):
    long = json.dumps({"explanation": "First. Second. Third."})
    assert Agent(FakeLLM([long])).explain(rec, SRC, "short", "expert").text == "First."
    fb = Agent(FakeLLM()).explain(rec, SRC, "short", "expert")
    assert fb.text.startswith("3:22 SYN-MISSING-SEMICOLON") and fb.text.endswith("(expr_stmt)")


def test_cache_is_keyed_by_verbosity(rec, tmp_path):
    cache = ExplanationCache(tmp_path / "c.json")
    agent = Agent(verbosity_llm(), cache)
    b = agent.explain(rec, SRC, "short", "beginner")
    e = agent.explain(rec, SRC, "short", "expert")
    assert len(cache) == 2 and b.text != e.text
    again = Agent(FakeLLM(), cache).explain(rec, SRC, "short", "expert")
    assert again.text == e.text and again.citations == ["rule:expr_stmt"]


# ---------------------------------------------------------------- F7 citations
def test_prompt_includes_retrieved_rule_and_fix_pattern(rec):
    fake = FakeLLM([json.dumps({"explanation": "x"})])
    Agent(fake).explain(rec, SRC)
    text = user_msg(fake.calls[0])
    assert "Reference chunks (cite the ids you use):" in text
    assert "[rule:expr_stmt]" in text and "[fix:SYN-MISSING-SEMICOLON]" in text
    assert "Common mistake:" in text and "Fix: Add ; at the end" in text


def test_citations_outside_the_retrieved_set_are_dropped(rec):
    reply = json.dumps({"explanation": "x", "citations": ["rule:expr_stmt", "rule:made_up", 7, "sem.type_compat",
                                                          "rule:expr_stmt", "fix:SYN-MISSING-SEMICOLON"]})
    exp = Agent(FakeLLM([reply])).explain(rec, SRC)
    assert exp.citations == ["rule:expr_stmt", "fix:SYN-MISSING-SEMICOLON"]


@pytest.mark.parametrize("reply", [json.dumps({"explanation": "x"}),
                                   json.dumps({"explanation": "x", "citations": ["rule:nope"]}),
                                   json.dumps({"explanation": "x", "citations": "rule:expr_stmt"})])
def test_no_valid_citation_falls_back_to_the_grounding_rule(rec, reply):
    assert Agent(FakeLLM([reply])).explain(rec, SRC).citations == ["rule:expr_stmt"]


def test_model_failure_still_returns_valid_citations(rec):
    exp = Agent(FakeLLM()).explain(rec, SRC)
    assert exp.citations == ["rule:expr_stmt"]


def test_metrics_f7_meets_target():
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "metrics_f7.py")], capture_output=True,
                          text=True, encoding="utf-8", cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "= 100.0% (target >= 90%)" in proc.stdout
    assert "non-existent citations: 0 (must be 0)" in proc.stdout


# ---------------------------------------------------------------- F6 follow-up Q&A
ANSWER = json.dumps({"answer": "A statement ends with ';' (rule expr_stmt).", "refused": False})


def test_semicolon_question_prompt_contains_the_grammar_rule_for_that_location(rec):
    fake = FakeLLM([ANSWER])
    ans = Agent(fake).ask(rec, SRC, "why does it expect a semicolon here?")
    assert not ans.refused
    text = user_msg(fake.calls[0])
    assert 'expr_stmt      = expression , ";" ;' in text and "Language rule expr_stmt (grammar)" in text
    assert "[fix:SYN-MISSING-SEMICOLON]" in text
    assert "using only the error record, source lines, language rule, reference chunks and earlier conversation" in text


def test_history_goes_into_the_prompt_in_order(rec):
    fake = FakeLLM([ANSWER])
    history = [{"question": "q one?", "answer": "a one"}, {"question": "q two?", "answer": "a two"}]
    Agent(fake).ask(rec, SRC, "and then? semicolon", history)
    text = user_msg(fake.calls[0])
    assert "Earlier conversation about this error:" in text
    assert text.index("Student: q one?") < text.index("Assistant: a one") < text.index("Student: q two?")
    assert text.index("Assistant: a two") < text.index('Student question: """and then? semicolon"""')


def test_history_is_capped_and_clipped(rec):
    history = [{"question": f"question {i}", "answer": f"answer {i}" + "z" * 5000} for i in range(AG.MAX_HISTORY + 4)]
    kept = AG.clip_history(history)
    assert len(kept) == AG.MAX_HISTORY
    assert kept[0]["question"] == "question 4" and kept[-1]["question"] == f"question {AG.MAX_HISTORY + 3}"
    assert all(len(t["answer"]) <= AG.MAX_HISTORY_CHARS for t in kept)
    fake = FakeLLM([ANSWER])
    Agent(fake).ask(rec, SRC, "semicolon?", history)
    text = user_msg(fake.calls[0])
    assert "question 3" not in text and "question 4" in text


def test_malformed_history_turns_are_ignored():
    assert AG.clip_history([{"question": "q"}, "x", {"question": 1, "answer": "a"}, None] if False else
                           [{"question": "q"}, {"question": 1, "answer": "a"}]) == []
    assert AG.clip_history(None) == []


def test_off_topic_is_still_refused_without_calling_the_llm(rec):
    fake = FakeLLM([ANSWER])
    ans = Agent(fake).ask(rec, SRC, "what is the weather today?", [{"question": "a", "answer": "b"}])
    assert ans.refused and fake.calls == []


# ---------------------------------------------------------------- API
@pytest.fixture
def client():
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def use_agent(llm):
    api.app.dependency_overrides[api.get_agent] = lambda: Agent(llm)


def test_api_explain_passes_verbosity_and_returns_citations(client):
    fake = verbosity_llm()
    use_agent(fake)
    # SRC_UNDECLARED's rule is a sem.* rule, so the scripted citation falls back to the grounding rule
    out = {}
    for v in ("beginner", "expert"):
        resp = client.post("/api/explain", json={"source": SRC, "record_id": "E-0001", "mode": "short", "verbosity": v})
        assert resp.status_code == 200, resp.text
        out[v] = resp.json()
    assert out["beginner"]["text"] != out["expert"]["text"]
    assert {o["verbosity"] for o in out.values()} == {"beginner", "expert"}
    assert out["beginner"]["rule_ref"] == out["expert"]["rule_ref"] == "expr_stmt"
    assert out["beginner"]["cited_rule"] == out["expert"]["cited_rule"] == "expr_stmt"
    assert out["expert"]["citations"] == ["rule:expr_stmt"]
    assert "Verbosity: expert" in user_msg(fake.calls[1])


def test_api_verbosity_defaults_to_beginner_and_rejects_unknown(client):
    use_agent(verbosity_llm())
    ok = client.post("/api/explain", json={"source": SRC, "record_id": "E-0001"})
    assert ok.json()["verbosity"] == "beginner"
    bad = client.post("/api/explain", json={"source": SRC, "record_id": "E-0001", "verbosity": "pirate"})
    assert bad.status_code == 422


def test_api_ask_sends_history_and_caps_request_size(client):
    fake = FakeLLM(default=ANSWER)
    use_agent(fake)
    turn = {"question": "why a semicolon?", "answer": "It ends the statement."}
    resp = client.post("/api/ask", json={"source": SRC, "record_id": "E-0001", "question": "and the next one?",
                                         "history": [turn], "extra": "ignored"})
    assert resp.status_code == 200 and resp.json()["refused"] is False
    assert "Student: why a semicolon?" in user_msg(fake.calls[0])
    many = [turn] * (api.MAX_HISTORY_TURNS + 1)
    too_long = client.post("/api/ask", json={"source": SRC, "record_id": "E-0001", "question": "semicolon?",
                                             "history": many})
    assert too_long.status_code == 422
    no_history = client.post("/api/ask", json={"source": SRC, "record_id": "E-0001", "question": "semicolon?"})
    assert no_history.status_code == 200


def test_short_follow_up_inside_a_thread_reaches_the_model_but_unrelated_one_does_not(rec):
    turn = [{"question": "why a semicolon?", "answer": "It ends the statement."}]
    assert not AG.is_off_topic("and then?", rec, in_thread=True)
    assert AG.is_off_topic("and then?", rec)
    assert AG.is_off_topic("tell me a joke", rec, in_thread=True)
    fake = FakeLLM([ANSWER])
    assert not Agent(fake).ask(rec, SRC, "and then?", turn).refused and len(fake.calls) == 1
