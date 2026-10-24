"""FastAPI backend (plan 012, plans/m2-architecture.md section 3), through TestClient.

No network: the agent is injected through the ``get_agent`` dependency, either
as ``SpyAgent`` (records exactly what the API hands the agent) or as the real
``Agent`` over ``FakeLLM``.
"""
import pytest
from fastapi.testclient import TestClient

from cea import api
from cea.agent import Agent, Answer, Correction, Explanation, FixSuggestion
from cea.llm import FakeLLM
from cea.llm import client_from_env as real_client_from_env
from cea.pipeline import compile_source
from cea.profile import ProfileStore
from cea.records import ErrorRecord

SRC_OK = "int main(void) {\n    return 0;\n}\n"
SRC_UNDECLARED = "int main(void) {\n    x = 1;\n    x = 2;\n    return 0;\n}\n"      # E-0001 root, E-0002 symptom
SRC_CASCADE = "int main(void) {\n    int x = 5 @ 2;\n    return x;\n}\n"              # LEX root, SYN symptom
SRC_WARNING = "int main(void) {\n    int unused = 1;\n    return 0;\n}\n"            # one warning only
RECORD_KEYS = ["id", "phase", "code", "severity", "line", "column", "found", "expected", "snippet",
               "root_id", "rule_ref", "language", "caused_by", "span_end", "message"]
PRIVATE = {"filename": "alice-smith-hw3.c", "file_path": "C:/Users/alice.smith/hw3.c",
           "student": "Alice Smith", "student_id": "S1234567"}
DUMMY_KEY = "dummy-key-not-real-0123"
PRIMARY = {"CEA_LLM_BASE_URL": "https://example.invalid/v1/", "CEA_LLM_MODEL": "m", "CEA_LLM_API_KEY": DUMMY_KEY}


class SpyAgent:
    """Stands in for cea.agent.Agent and records every call's arguments."""

    def __init__(self):
        self.calls = []

    def explain(self, record, source, mode="short", verbosity="beginner"):
        self.calls.append(("explain", record, source, mode, verbosity))
        return Explanation(text=f"why {record.id}", rule_ref=record.rule_ref, cited_rule=None, mode=mode,
                           verbosity=verbosity, citations=["rule:" + record.rule_ref])

    def suggest_fix(self, record, source, feedback=None, store=True):
        self.calls.append(("fix", record, source))
        patched = source.replace("    x = 1;", "    int x = 1;").replace(" @ ", " * ")     # a genuine fix for the test sources
        return FixSuggestion(diff=Agent.unified_diff(source, patched), patched_source=patched)

    def remember_fix(self, record, source, fix):
        pass

    def correct(self, source, records, feedback=None):
        self.calls.append(("correct", source, [r.id for r in records]))
        fixed = source.replace("    x = 1;", "    int x = 1;").replace(" @ ", " * ")
        return Correction(corrected_source=fixed, changes=["Declared x before using it."])

    def ask(self, record, source, question, history=None):
        self.calls.append(("ask", record, source, question, history))
        return Answer(text=f"answer to {question}", refused=False)


class BrokenAgent:
    """Every call fails, as an unreachable LLM would."""

    def explain(self, *args):
        raise RuntimeError("model unreachable")

    suggest_fix = ask = correct = explain


class RecordingLLM:
    """Wraps FakeLLM and keeps every message list the agent sends (LLMClient protocol)."""

    def __init__(self, inner):
        self.inner = inner
        self.sent = []

    def complete(self, messages, *, json_schema=None, max_tokens=400, temperature=0.2):
        self.sent.append(messages)
        return self.inner.complete(messages, json_schema=json_schema, max_tokens=max_tokens,
                                   temperature=temperature)


@pytest.fixture
def client(tmp_path):
    api.app.dependency_overrides[api.get_profiles] = lambda: ProfileStore(tmp_path / "profiles.sqlite3")
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    api._env_agent.cache_clear()


@pytest.fixture
def spy():
    agent = SpyAgent()
    api.app.dependency_overrides[api.get_agent] = lambda: agent
    return agent


def body(path, source, **extra):
    """A valid request body for ``path``."""
    data = {"source": source}
    if path != "/api/compile":
        data["record_id"] = "E-0001"
    if path == "/api/explain":
        data["mode"] = "short"
    if path == "/api/ask":
        data["question"] = "Why is this an error?"
    data.update(extra)
    return data


AGENT_PATHS = ["/api/explain", "/api/fix", "/api/ask"]


# ---------------------------------------------------------------- /api/health
def use_config(monkeypatch, environ, env_file=None):
    """Make the API see exactly this configuration through plan 010's real client_from_env()."""
    monkeypatch.setattr(api, "client_from_env", lambda: real_client_from_env(environ, env_file=env_file))


def without_gcc(health):
    assert isinstance(health.pop("gcc"), bool)      # whether gcc is installed (for the engine fallback)
    return health


@pytest.mark.parametrize("environ,expected", [
    (PRIMARY, "primary"),
    ({**PRIMARY, "CEA_LLM_FALLBACK_MODEL": "small"}, "primary"),
    ({"CEA_LLM_BASE_URL": "https://example.invalid/v1/", "CEA_LLM_FALLBACK_MODEL": "small"}, "fallback"),
    ({"CEA_LLM_FALLBACK_MODEL": "small"}, "fallback"),
    ({"CEA_LLM_API_KEY": DUMMY_KEY}, "none"),
    ({**PRIMARY, "CEA_LLM_TIMEOUT": "soon"}, "none"),
    ({}, "none"),
])
def test_health(client, monkeypatch, environ, expected):
    use_config(monkeypatch, environ)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert without_gcc(resp.json()) == {"status": "ok", "llm": expected}
    assert DUMMY_KEY not in resp.text


def test_health_reads_the_env_file(client, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in PRIMARY.items()), encoding="utf-8")
    use_config(monkeypatch, {}, env_file)
    resp = client.get("/api/health")
    assert without_gcc(resp.json()) == {"status": "ok", "llm": "primary"} and DUMMY_KEY not in resp.text


def test_health_environment_wins_over_the_env_file(client, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in PRIMARY.items()), encoding="utf-8")
    use_config(monkeypatch, {"CEA_LLM_MODEL": ""}, env_file)
    assert without_gcc(client.get("/api/health").json()) == {"status": "ok", "llm": "none"}


# ---------------------------------------------------------------- /api/compile
def test_compile_valid_program(client):
    resp = client.post("/api/compile", json={"source": SRC_OK})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "summary": "0 fatal, 0 warnings", "records": [], "clusters": [],
                           "engine": "cea", "engine_note": None}


def test_compile_undeclared_groups_uses(client):
    data = client.post("/api/compile", json={"source": SRC_UNDECLARED}).json()
    assert data["ok"] is False and data["summary"] == "2 fatal, 0 warnings"
    assert [list(r) for r in data["records"]] == [RECORD_KEYS, RECORD_KEYS]
    assert [(r["id"], r["code"], r["line"], r["root_id"]) for r in data["records"]] == [
        ("E-0001", "SEM-UNDECLARED-VAR", 2, "E-0001"), ("E-0002", "SEM-UNDECLARED-VAR", 3, "E-0001")]
    assert data["clusters"] == [{"root_id": "E-0001", "symptom_ids": ["E-0002"]}]


def test_compile_cascade_has_one_cluster(client):
    data = client.post("/api/compile", json={"source": SRC_CASCADE}).json()
    assert [(r["phase"], r["code"]) for r in data["records"]] == [
        ("lexical", "LEX-INVALID-CHAR"), ("syntax", "SYN-MISSING-SEMICOLON")]
    assert data["clusters"] == [{"root_id": "E-0001", "symptom_ids": ["E-0002"]}]


def test_compile_warning_only_still_ok(client):
    data = client.post("/api/compile", json={"source": SRC_WARNING}).json()
    assert data["ok"] is True and data["summary"] == "0 fatal, 1 warning"
    assert [(r["code"], r["severity"]) for r in data["records"]] == [("WRN-UNUSED-VAR", "warning")]


def test_compile_matches_the_pipeline(client):
    data = client.post("/api/compile", json={"source": SRC_CASCADE}).json()
    assert data["records"] == [r.to_dict() for r in compile_source(SRC_CASCADE, "x.c").errors]


def test_compile_needs_no_agent(client):
    api.app.dependency_overrides[api.get_agent] = BrokenAgent
    assert client.post("/api/compile", json={"source": SRC_OK}).status_code == 200


# ---------------------------------------------------------------- size limit and validation
@pytest.mark.parametrize("path", ["/api/compile", *AGENT_PATHS])
def test_source_over_64kb_is_413(client, spy, path):
    resp = client.post(path, json=body(path, "a" * (64 * 1024 + 1)))
    assert resp.status_code == 413
    assert spy.calls == []


def test_source_of_exactly_64kb_is_accepted(client):
    assert client.post("/api/compile", json={"source": "a" * (64 * 1024)}).status_code == 200


def test_limit_counts_utf8_bytes_not_characters(client):
    source = "\u00e9" * (32 * 1024 + 1)      # 32769 characters, 65538 bytes
    assert client.post("/api/compile", json={"source": source}).status_code == 413


@pytest.mark.parametrize("path,data", [
    ("/api/compile", {}),
    ("/api/compile", {"source": 42}),
    ("/api/explain", {"source": SRC_UNDECLARED}),
    ("/api/explain", {"source": SRC_UNDECLARED, "record_id": "E-0001", "mode": "long"}),
    ("/api/fix", {"record_id": "E-0001"}),
    ("/api/ask", {"source": SRC_UNDECLARED, "record_id": "E-0001"}),
    ("/api/ask", {"source": SRC_UNDECLARED, "record_id": "E-0001", "question": ""}),
    ("/api/ask", {"source": SRC_UNDECLARED, "record_id": "E-0001", "question": "q" * 1001}),
])
def test_invalid_body_is_422(client, spy, path, data):
    assert client.post(path, json=data).status_code == 422
    assert spy.calls == []


# ---------------------------------------------------------------- unknown record ids
@pytest.mark.parametrize("path", AGENT_PATHS)
@pytest.mark.parametrize("source,record_id", [(SRC_UNDECLARED, "E-0099"), (SRC_UNDECLARED, "e-0001"),
                                              (SRC_OK, "E-0001")])
def test_unknown_record_id_is_404(client, spy, path, source, record_id):
    resp = client.post(path, json=body(path, source, record_id=record_id))
    assert resp.status_code == 404
    assert spy.calls == []


# ---------------------------------------------------------------- /api/explain, /api/fix, /api/ask
@pytest.mark.parametrize("mode", ["short", "expand"])
def test_explain(client, spy, mode):
    resp = client.post("/api/explain", json=body("/api/explain", SRC_UNDECLARED, record_id="E-0002", mode=mode))
    assert resp.status_code == 200
    assert resp.json() == {"text": "why E-0002", "rule_ref": "sem.declare_before_use", "cited_rule": None,
                           "mode": mode, "verbosity": "beginner", "citations": ["rule:sem.declare_before_use"]}
    ((name, record, source, got_mode, _verbosity),) = spy.calls
    assert (name, record.id, source, got_mode) == ("explain", "E-0002", SRC_UNDECLARED, mode)


def test_explain_mode_defaults_to_short(client, spy):
    resp = client.post("/api/explain", json={"source": SRC_UNDECLARED, "record_id": "E-0001"})
    assert resp.status_code == 200 and resp.json()["mode"] == "short"


def test_fix_is_shown_only_when_verified(client, spy):
    resp = client.post("/api/fix", json=body("/api/fix", SRC_CASCADE))
    assert resp.status_code == 200
    data = resp.json()
    patched = SRC_CASCADE.replace(" @ ", " * ")
    assert data == {"diff": Agent.unified_diff(SRC_CASCADE, patched), "patched_source": patched,
                    "verified": True, "attempts": 1, "reason": data["reason"]}
    assert [(c[0], c[1].code) for c in spy.calls] == [("fix", "LEX-INVALID-CHAR")]


def test_unverified_fix_is_withheld(client, spy):
    """The spy's edit does not fix SRC_WARNING's root, so there is no root; use a source it cannot fix."""
    src = "int main(void) {\n    int x = 5 # 2;\n    return x;\n}\n"
    resp = client.post("/api/fix", json=body("/api/fix", src))
    data = resp.json()
    assert resp.status_code == 200 and data["verified"] is False
    assert data["diff"] == "" and data["patched_source"] == src and data["attempts"] == 3 and data["reason"]


def test_ask(client, spy):
    resp = client.post("/api/ask", json=body("/api/ask", SRC_UNDECLARED, question="Where is x declared?"))
    assert resp.status_code == 200
    assert resp.json() == {"text": "answer to Where is x declared?", "refused": False}
    assert spy.calls[0][3] == "Where is x declared?"


# ---------------------------------------------------------------- /api/analyze (pipeline view)
def test_analyze_returns_tokens_tree_and_symbols(client):
    resp = client.post("/api/analyze", json={"source": "int main(void) {\n    int x = 1;\n    return x;\n}\n"})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"tokens", "tree", "treeNodes", "symbols"}
    assert {"name": "main", "type": "int", "kind": "function", "line": 1} in data["symbols"]
    assert {"name": "x", "type": "int", "kind": "local", "line": 2} in data["symbols"]
    assert data["tokens"][0] == {"kind": "KEYWORD", "text": "int", "line": 1, "col": 1}
    assert "Program" in data["tree"] and "FunctionDecl" in data["tree"]


# ---------------------------------------------------------------- /api/run (compile + execute)
def test_run_executes_the_program_and_returns_its_output(client, monkeypatch):
    from cea import runner
    fake = runner.RunResult(gcc_available=True, compiled=True, compile_output="", stdout="sum = 15\n",
                            stderr="", exit_code=0, timed_out=False, truncated=False)
    monkeypatch.setattr(api, "run_program", lambda source: fake)
    resp = client.post("/api/run", json={"source": "int main(void){return 0;}\n"})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"gcc_available", "compiled", "compile_output", "stdout", "stderr",
                         "exit_code", "timed_out", "truncated"}
    assert data["compiled"] is True and data["stdout"] == "sum = 15\n" and data["exit_code"] == 0


def test_run_rejects_a_source_over_the_size_limit(client):
    resp = client.post("/api/run", json={"source": "a" * (64 * 1024 + 1)})
    assert resp.status_code == 413


# ---------------------------------------------------------------- /api/correct (F8 whole program)
def test_correct_rewrites_the_whole_program_and_counts_the_click(client, spy):
    sid = "stu_" + "c" * 20
    resp = client.post("/api/correct", json={"source": SRC_UNDECLARED, "student_id": sid})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"corrected_source", "diff", "changes", "verified", "before_summary",
                         "after_summary", "remaining_fatal", "attempts", "reason"}
    assert data["verified"] is True and data["remaining_fatal"] == 0
    assert "int x = 1;" in data["corrected_source"] and data["changes"]
    assert data["diff"] and data["before_summary"] and data["after_summary"].startswith("0 fatal")
    # the agent got the source and the root ids, never the student id
    assert spy.calls[0][0] == "correct" and sid not in repr(spy.calls)
    # the click is counted in the profile analytics
    analytics = client.get(f"/api/profile/{sid}/analytics?days=30&tz=0").json()
    assert analytics["corrections"] == 1


def test_correct_counts_the_click_even_when_already_compiling(client, spy):
    sid = "stu_" + "d" * 20
    resp = client.post("/api/correct", json={"source": SRC_OK, "student_id": sid})
    data = resp.json()
    assert data["verified"] is True and data["diff"] == "" and data["changes"] == []
    assert spy.calls == []                                   # the agent is not even called
    assert client.get(f"/api/profile/{sid}/analytics?days=30&tz=0").json()["corrections"] == 1


def test_correct_never_leaks_private_fields_to_the_agent(client, spy):
    resp = client.post("/api/correct", json={"source": SRC_UNDECLARED, **PRIVATE})
    assert resp.status_code == 200
    seen = repr(spy.calls)
    for value in PRIVATE.values():
        assert value not in seen


def test_correct_agent_failure_is_502(client):
    api.app.dependency_overrides[api.get_agent] = BrokenAgent
    resp = client.post("/api/correct", json={"source": SRC_UNDECLARED})
    assert resp.status_code == 502 and "model unreachable" not in resp.text


@pytest.mark.parametrize("path", AGENT_PATHS)
def test_agent_failure_is_502(client, path):
    api.app.dependency_overrides[api.get_agent] = BrokenAgent
    resp = client.post(path, json=body(path, SRC_UNDECLARED))
    assert resp.status_code == 502
    assert "model unreachable" not in resp.text


# ---------------------------------------------------------------- privacy: only compiler context reaches the agent
@pytest.mark.parametrize("path", AGENT_PATHS)
def test_filename_and_extra_fields_never_reach_the_agent(client, spy, path):
    resp = client.post(path, json=body(path, SRC_UNDECLARED, **PRIVATE))
    assert resp.status_code == 200
    (call,) = spy.calls
    record, source = call[1], call[2]
    assert isinstance(record, ErrorRecord) and source == SRC_UNDECLARED
    assert len(call) == (3 if path == "/api/fix" else 5)                 # no extra arguments
    seen = repr(call) + repr(record.to_dict())
    for value in PRIVATE.values():
        assert value not in seen
    assert "alice" not in seen.lower()


# ---------------------------------------------------------------- the real Agent over FakeLLM
@pytest.fixture
def fake_agent():
    llm = RecordingLLM(FakeLLM(["not json"] * 20))
    api.app.dependency_overrides[api.get_agent] = lambda: Agent(llm)
    return llm


@pytest.mark.parametrize("path,keys", [("/api/explain", {"text", "rule_ref", "cited_rule", "mode", "verbosity", "citations",
                                                         "personalised"}),
                                       ("/api/fix", {"diff", "patched_source", "verified", "attempts", "reason"}),
                                       ("/api/ask", {"text", "refused"})])
def test_real_agent_over_fake_llm(client, fake_agent, path, keys):
    resp = client.post(path, json=body(path, SRC_UNDECLARED, **PRIVATE))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) == keys
    if path == "/api/fix":
        assert data["verified"] is False
    sent = repr(fake_agent.sent).lower()
    assert "alice" not in sent and "hw3" not in sent and "s1234567" not in sent


# ---------------------------------------------------------------- the default dependency
def test_get_agent_builds_the_agent_with_the_cache(monkeypatch):
    made = []

    class SpyCache:
        def __init__(self, path=None):
            made.append(path)

    api._env_agent.cache_clear()
    monkeypatch.setattr(api, "client_from_env", lambda: FakeLLM([]))
    monkeypatch.setattr(api, "ExplanationCache", SpyCache)
    try:
        agent = api.get_agent()
        assert isinstance(agent, Agent) and api.get_agent() is agent      # built once
        assert made == [None]                                              # ExplanationCache() at its default path
    finally:
        api._env_agent.cache_clear()


def test_unconfigured_llm_is_503(client, monkeypatch):
    def broken():
        raise RuntimeError("no CEA_LLM_* configuration")
    api._env_agent.cache_clear()
    monkeypatch.setattr(api, "client_from_env", broken)
    resp = client.post("/api/explain", json=body("/api/explain", SRC_UNDECLARED))
    assert resp.status_code == 503


# ---------------------------------------------------------------- CORS and routes
def test_cors_allows_the_vite_dev_origin(client):
    resp = client.options("/api/compile", headers={"Origin": "http://localhost:5173",
                                                   "Access-Control-Request-Method": "POST",
                                                   "Access-Control-Request-Headers": "content-type"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize("origin", ["http://evil.example", "http://127.0.0.1:5173", "http://localhost:3000"])
def test_cors_rejects_other_origins(client, origin):
    pre = client.options("/api/compile", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 400
    assert "access-control-allow-origin" not in pre.headers
    get = client.get("/api/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in get.headers


def test_exactly_the_contract_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {(p, m) for p, ops in paths.items() for m in ops} == {
        ("/api/compile", "post"), ("/api/explain", "post"), ("/api/fix", "post"), ("/api/ask", "post"),
        ("/api/correct", "post"), ("/api/run", "post"), ("/api/analyze", "post"),
        ("/api/health", "get"), ("/api/profile/{student_id}", "get"), ("/api/profile/{student_id}", "delete"),
        ("/api/profile/{student_id}/analytics", "get")}


# ---------------------------------------------------------------- engine / gcc fallback
import shutil  # noqa: E402

needs_gcc = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not on PATH")
SRC_GOTO = "int main(void) {\n    int x = 1;\n    goto end;\nend:\n    return x;\n}\n"


@needs_gcc
def test_compile_falls_back_to_gcc_for_unsupported_features(client):
    data = client.post("/api/compile", json={"source": SRC_GOTO}).json()
    assert data["engine"] == "gcc" and "gcc" in data["engine_note"] and data["ok"] is True


def test_compile_engine_cea_never_uses_gcc(client):
    data = client.post("/api/compile", json={"source": SRC_GOTO, "engine": "cea"}).json()
    assert data["engine"] == "cea" and data["engine_note"] is None
    assert any(r["code"] == "SYN-UNSUPPORTED-FEATURE" for r in data["records"])


@needs_gcc
def test_compile_engine_gcc_is_forced(client):
    data = client.post("/api/compile", json={"source": SRC_OK.replace("return 0;", "return y;"), "engine": "gcc"}).json()
    assert data["engine"] == "gcc" and data["ok"] is False
    assert {r["code"] for r in data["records"]} <= {"GCC-ERROR", "GCC-WARNING", "GCC-NOTE"}


def test_compile_says_so_when_gcc_is_missing(client, monkeypatch):
    monkeypatch.setattr("cea.gcc_fallback.gcc_path", lambda: None)
    data = client.post("/api/compile", json={"source": SRC_GOTO, "engine": "gcc"}).json()
    assert data["engine"] == "cea" and "gcc is not installed" in data["engine_note"]
    assert client.get("/api/health").json()["gcc"] is False


def test_compile_rejects_an_unknown_engine(client):
    assert client.post("/api/compile", json={"source": SRC_OK, "engine": "clang"}).status_code == 422
