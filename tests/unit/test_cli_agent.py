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


def test_fix_prints_verified_header_and_diff(fake, src_file, capsys):
    code = cli.main([str(src_file), "--fix", "--no-cache"])
    out = capsys.readouterr().out.splitlines()
    assert code == 1
    assert out[1] == "    " + cli.VERIFIED_HEADER
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
                                   "rule_ref": "expr_stmt", "cited_rule": "expr_stmt", "mode": "short",
                                   "verbosity": "beginner", "citations": ["rule:expr_stmt"]}
    assert item["fix"]["verified"] is True and item["fix"]["diff"].startswith("--- original\n")
    assert item["fix"]["attempts"] == 1


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


def test_fix_that_cannot_be_verified_prints_no_fix_note(monkeypatch, src_file, capsys):
    llm = FakeLLM(default=json.dumps({"start_line": 3, "end_line": 3, "replacement": ["    total = total + 1"]}))
    monkeypatch.setattr(cli, "client_from_env", lambda: llm)
    cli.main([str(src_file), "--fix", "--no-cache"])
    out = capsys.readouterr().out
    assert "    No verified fix found; see explanation" in out and "Verified fix" not in out and "UNVERIFIED" not in out
    cli.main([str(src_file), "--json", "--fix", "--no-cache"])
    fix = json.loads(capsys.readouterr().out)["agent"][0]["fix"]
    assert fix["verified"] is False and fix["diff"] == "" and fix["patched_source"] == "" and fix["attempts"] == 3
