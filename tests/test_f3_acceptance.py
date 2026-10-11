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
    assert len(DEV) == 69


@pytest.mark.corpus
@pytest.mark.parametrize("c_path", DEV, ids=[p.name for p in DEV])
def test_every_root_gets_an_explanation_and_a_diff(c_path):
    source = c_path.read_text(encoding="utf-8")
    result = compile_source(source, c_path.name, engine="cea")
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
