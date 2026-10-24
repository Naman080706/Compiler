"""PRD F9: the personalised error model (cea.profile + the API endpoints). FakeLLM only; no network."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from cea import api
from cea.agent import Agent
from cea.llm import FakeLLM
from cea.pipeline import compile_source
from cea.profile import THRESHOLD, ProfileStore, choose_depth

SID = "stu_7f3a9c21d4e85b06"
OTHER = "stu_0000aaaa1111bbbb"
SEMI = "int main(void) {\n    int t = 0;\n    t = t + 1\n    return t;\n}\n"        # missing-semicolon
UNDECL = "int main(void) {\n    y = 1;\n    return 0;\n}\n"                          # undeclared-identifier
CATEGORY = "missing-semicolon"


def roots(src):
    return [c.root for c in compile_source(src, "t.c").clusters]


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "sub" / "profiles.sqlite3")


class RecordingLLM:
    def __init__(self):
        self.inner = FakeLLM(default=json.dumps({"explanation": "Scripted explanation.", "citations": []}))
        self.sent = []

    def complete(self, messages, *, json_schema=None, max_tokens=400, temperature=0.2):
        self.sent.append(messages)
        return self.inner.complete(messages, json_schema=json_schema, max_tokens=max_tokens, temperature=temperature)


@pytest.fixture
def web(store):
    llm = RecordingLLM()
    api.app.dependency_overrides[api.get_agent] = lambda: Agent(llm)
    api.app.dependency_overrides[api.get_profiles] = lambda: store
    yield TestClient(api.app), llm
    api.app.dependency_overrides.clear()


def compile_in(client, src, session, student=SID):
    return client.post("/api/compile", json={"source": src, "student_id": student, "session_id": session}).json()


def explain_in(client, src, student=SID, **extra):
    rid = next(c.root.id for c in compile_source(src, "t.c").clusters)
    resp = client.post("/api/explain", json={"source": src, "record_id": rid, "student_id": student, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------- counting rules
def test_database_lives_in_a_created_folder(store):
    store.record_compile(SID, "s1", roots(SEMI))
    assert store.path.exists() and store.path.parent.name == "sub"
    assert sqlite3.connect(store.path).execute("select count(*) from category_counts").fetchone() == (1,)


def test_each_root_counts_once_per_compile_not_its_symptoms(store):
    src = "int main(void) {\n    x = 1;\n    x = 2;\n    x = 3;\n    return 0;\n}\n"      # 3 records, one root
    assert len(compile_source(src, "t.c").errors) == 3 and len(roots(src)) == 1
    store.record_compile(SID, "s1", roots(src))
    assert store.counts(SID) == {"undeclared-identifier": 1}


def test_same_signature_counts_once_per_session(store):
    for _ in range(4):
        store.record_compile(SID, "s1", roots(SEMI))
    assert store.hits(SID, CATEGORY) == 1
    store.record_compile(SID, "s2", roots(SEMI))
    assert store.hits(SID, CATEGORY) == 2


def test_moving_the_error_to_another_line_is_the_same_signature(store):
    store.record_compile(SID, "s1", roots(SEMI))
    store.record_compile(SID, "s1", roots("\n\n" + SEMI))
    assert store.hits(SID, CATEGORY) == 1


def test_different_signatures_in_one_session_both_count(store):
    two = "int main(void) {\n    int a = 1\n    int b = 2\n    return 0;\n}\n"
    rs = roots(two)
    store.record_compile(SID, "s1", rs)
    assert store.hits(SID, CATEGORY) == 2          # two distinct signatures (found "int" and "return")


def test_students_are_separate_and_reset_deletes_everything(store):
    store.record_compile(SID, "s1", roots(SEMI))
    store.record_compile(OTHER, "s1", roots(UNDECL))
    assert store.counts(SID) == {CATEGORY: 1} and store.counts(OTHER) == {"undeclared-identifier": 1}
    store.reset(SID)
    assert store.counts(SID) == {}
    store.record_compile(SID, "s1", roots(SEMI))                 # the seen-list was reset too
    assert store.hits(SID, CATEGORY) == 1 and store.hits(OTHER, "undeclared-identifier") == 1


def test_record_action_counts_per_student_and_shows_in_analytics(store):
    store.record_action(SID, "correct")
    store.record_action(SID, "correct")
    store.record_action(OTHER, "correct")
    assert store.action_count(SID, "correct") == 2 and store.action_count(OTHER, "correct") == 1
    assert store.analytics(SID)["corrections"] == 2
    assert store.action_count(SID, "never-used") == 0
    store.reset(SID)                                            # reset clears the action counts too
    assert store.action_count(SID, "correct") == 0 and store.action_count(OTHER, "correct") == 1


def test_choose_depth_manual_toggle_always_overrides():
    assert choose_depth(None, 0) == ("expert", False)
    assert choose_depth(None, THRESHOLD - 1) == ("expert", False)
    assert choose_depth(None, THRESHOLD) == ("beginner", True)
    assert choose_depth("expert", 99) == ("expert", False)
    assert choose_depth("beginner", 0) == ("beginner", False)


# ---------------------------------------------------------------- API
def test_profile_endpoints_view_and_reset(web):
    client, _ = web
    compile_in(client, SEMI, "sess0001")
    view = client.get(f"/api/profile/{SID}").json()
    assert view == {"student_id": SID, "threshold": 3,
                    "categories": [{"category": CATEGORY, "hits": 1, "depth": "terse"}]}
    assert client.delete(f"/api/profile/{SID}").json()["categories"] == []
    assert client.get(f"/api/profile/{SID}").json()["categories"] == []


@pytest.mark.parametrize("method", ["get", "delete"])
def test_profile_endpoints_reject_bad_ids(web, method):
    client, _ = web
    assert getattr(client, method)("/api/profile/bad id!").status_code in (404, 422)
    assert getattr(client, method)("/api/profile/short").status_code == 422


def test_compile_without_a_student_id_stores_nothing(web, store):
    client, _ = web
    assert client.post("/api/compile", json={"source": SEMI}).status_code == 200
    assert not store.path.exists()


def test_invalid_student_id_is_rejected_on_compile(web):
    client, _ = web
    assert client.post("/api/compile", json={"source": SEMI, "student_id": "a b"}).status_code == 422


# ---------------------------------------------------------------- acceptance: simulated 5-session run
def test_five_sessions_depth_grows_for_the_repeated_category_only(web):
    client, llm = web
    depths = []
    for n in range(1, 6):
        compile_in(client, SEMI, f"session{n:02d}")
        if n == 2:
            compile_in(client, UNDECL, f"session{n:02d}")             # one unrelated error, once
        n_before = len(llm.sent)
        semi = explain_in(client, SEMI)
        undecl = explain_in(client, UNDECL)
        text = lambda i: llm.sent[i][1]["content"]
        depths.append((semi["personalised"]["depth"], undecl["personalised"]["depth"],
                       "Worked example" in text(n_before), "Worked example" in text(n_before + 1),
                       semi["verbosity"], undecl["verbosity"]))
    # hits for the repeated category after sessions 1..5 are 1..5; the threshold is reached in session 3
    assert [d[0] for d in depths] == ["terse", "terse", "full", "full", "full"]
    assert [d[2] for d in depths] == [False, False, True, True, True]          # worked example appears
    assert [d[4] for d in depths] == ["expert", "expert", "beginner", "beginner", "beginner"]
    # the unrelated category was hit once, so it never changes
    assert [d[1] for d in depths] == ["terse"] * 5 and [d[3] for d in depths] == [False] * 5
    assert [d[5] for d in depths] == ["expert"] * 5
    view = client.get(f"/api/profile/{SID}").json()["categories"]
    assert {c["category"]: (c["hits"], c["depth"]) for c in view} == {
        CATEGORY: (5, "full"), "undeclared-identifier": (1, "terse")}


def test_manual_toggle_overrides_the_automatic_depth(web, store):
    client, llm = web
    for n in range(1, 5):
        compile_in(client, SEMI, f"session{n:02d}")
    assert store.hits(SID, CATEGORY) >= THRESHOLD
    out = explain_in(client, SEMI, verbosity="expert")
    assert out["verbosity"] == "expert" and out["personalised"]["override"] is True
    assert "Worked example" not in llm.sent[-1][1]["content"] and "Verbosity: expert" in llm.sent[-1][1]["content"]


def test_without_a_student_id_explain_keeps_the_old_default(web):
    client, llm = web
    rid = next(c.root.id for c in compile_source(SEMI, "t.c").clusters)
    out = client.post("/api/explain", json={"source": SEMI, "record_id": rid}).json()
    assert out["verbosity"] == "beginner" and "personalised" not in out


# ---------------------------------------------------------------- privacy
def test_student_id_never_appears_in_llm_messages(web):
    client, llm = web
    for n in range(1, 5):
        compile_in(client, SEMI, f"session{n:02d}")
        explain_in(client, SEMI)
        explain_in(client, SEMI, mode="expand")
    rid = next(c.root.id for c in compile_source(SEMI, "t.c").clusters)
    client.post("/api/ask", json={"source": SEMI, "record_id": rid, "question": "why is the semicolon needed?",
                                  "student_id": SID, "history": []})
    assert llm.sent
    blob = json.dumps(llm.sent)
    assert SID not in blob and "session01" not in blob


def test_student_id_is_not_part_of_the_cache_key(web, tmp_path):
    from cea.llm import ExplanationCache
    client, _ = web
    cache = ExplanationCache(tmp_path / "cache.json")
    api.app.dependency_overrides[api.get_agent] = lambda: Agent(RecordingLLM(), cache=cache)
    explain_in(client, SEMI)
    stored = (tmp_path / "cache.json").read_text(encoding="utf-8")
    assert stored and SID not in stored
