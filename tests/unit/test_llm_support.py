"""FakeLLM, ExplanationCache, client_from_env and tools/llm_smoke.py (plan 010). No network."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cea.llm import (ExplanationCache, FakeLLM, FallbackClient, LLMClient, LLMError, OpenAICompatClient,
                     client_from_env)
from cea.llm.config import read_env_file

ROOT = Path(__file__).resolve().parents[2]
DUMMY_KEY = "dummy-key-0123456789-DO-NOT-USE"
MSGS = [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------- FakeLLM
def test_fake_llm_script_then_default_and_records_calls():
    fake = FakeLLM(["one", LLMError("boom"), lambda m, s: f"n={len(m)} schema={s is not None}"], default="dflt")
    assert fake.complete(MSGS) == "one"
    with pytest.raises(LLMError, match="boom"):
        fake.complete(MSGS)
    assert fake.complete(MSGS, json_schema={"type": "object"}) == "n=1 schema=True"
    assert fake.complete(MSGS) == "dflt"
    assert len(fake.calls) == 4 and fake.calls[2]["json_schema"] == {"type": "object"}
    assert fake.calls[0] == {"messages": MSGS, "json_schema": None, "max_tokens": 400, "temperature": 0.2}


def test_fake_llm_without_default_raises_when_empty():
    with pytest.raises(LLMError):
        FakeLLM().complete(MSGS)


def test_fake_llm_copies_messages():
    fake, msgs = FakeLLM(default="x"), [{"role": "user", "content": "a"}]
    fake.complete(msgs)
    msgs[0]["content"] = "changed"
    assert fake.calls[0]["messages"][0]["content"] == "a"


@pytest.mark.parametrize("obj", [FakeLLM(), OpenAICompatClient("http://localhost:1/v1", "m"),
                                 FallbackClient(FakeLLM(), FakeLLM())])
def test_every_client_satisfies_the_protocol(obj):
    assert isinstance(obj, LLMClient)


# ---------------------------------------------------------------- ExplanationCache
SIG = {"code": "SYN-MISSING-SEMICOLON", "line": 5, "snippet": "x = 1\ny = 2"}


def test_cache_roundtrip_and_persistence(tmp_path):
    path = tmp_path / "c" / "explanations.json"
    cache = ExplanationCache(path)
    assert cache.get(SIG, "short") is None and len(cache) == 0
    cache.put(SIG, "short", {"text": "Missing ';'."})
    assert cache.get(SIG, "short") == {"text": "Missing ';'."}
    assert cache.get(SIG, "expand") is None                             # mode is part of the key
    again = ExplanationCache(path)                                      # a new process reads the file
    assert again.get(SIG, "short") == {"text": "Missing ';'."} and len(again) == 1


def test_cache_key_is_sha256_and_order_independent():
    k = ExplanationCache.key(SIG, "short")
    assert len(k) == 64 and int(k, 16) >= 0
    assert k == ExplanationCache.key(dict(reversed(list(SIG.items()))), "short")
    assert k != ExplanationCache.key(SIG, "expand")


def test_cache_file_has_no_plain_source_in_keys(tmp_path):
    cache = ExplanationCache(tmp_path / "e.json")
    cache.put(SIG, "short", {"text": "t"})
    data = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    assert list(data) == [ExplanationCache.key(SIG, "short")]


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", ""])
def test_corrupt_cache_file_counts_as_empty(tmp_path, content):
    path = tmp_path / "e.json"
    path.write_text(content, encoding="utf-8")
    cache = ExplanationCache(path)
    assert cache.get(SIG, "short") is None
    cache.put(SIG, "short", {"text": "t"})
    assert ExplanationCache(path).get(SIG, "short") == {"text": "t"}


def test_default_cache_path_is_git_ignored_folder():
    assert ExplanationCache().path == ROOT / ".cea_cache" / "explanations.json"


# ---------------------------------------------------------------- client_from_env
def test_nothing_configured_raises():
    with pytest.raises(LLMError, match="no LLM configured"):
        client_from_env({}, env_file=None)


def test_primary_only():
    c = client_from_env({"CEA_LLM_BASE_URL": "https://example.invalid/v1beta/openai/",
                         "CEA_LLM_API_KEY": DUMMY_KEY, "CEA_LLM_MODEL": "gemini-x"}, env_file=None)
    assert isinstance(c, OpenAICompatClient)
    assert (c.name, c.model, c.timeout) == ("primary", "gemini-x", 30.0)
    assert c.url == "https://example.invalid/v1beta/openai/chat/completions"
    assert DUMMY_KEY not in repr(c)


def test_fallback_only_uses_ollama_default_url():
    c = client_from_env({"CEA_LLM_FALLBACK_MODEL": "llama3.1"}, env_file=None)
    assert isinstance(c, OpenAICompatClient)
    assert (c.name, c.url, c.timeout) == ("fallback", "http://localhost:11434/v1/chat/completions", 120.0)


def test_both_configured_gives_fallback_client():
    c = client_from_env({"CEA_LLM_BASE_URL": "https://example.invalid/v1", "CEA_LLM_MODEL": "g",
                         "CEA_LLM_API_KEY": DUMMY_KEY, "CEA_LLM_FALLBACK_MODEL": "llama3.1",
                         "CEA_LLM_FALLBACK_BASE_URL": "http://127.0.0.1:9/v1", "CEA_LLM_TIMEOUT": "7"},
                        env_file=None)
    assert isinstance(c, FallbackClient)
    assert (c.primary.timeout, c.fallback.url) == (7.0, "http://127.0.0.1:9/v1/chat/completions")
    assert DUMMY_KEY not in repr(c)


def test_model_without_base_url_is_not_a_primary():
    with pytest.raises(LLMError):
        client_from_env({"CEA_LLM_MODEL": "g", "CEA_LLM_API_KEY": DUMMY_KEY}, env_file=None)


def test_bad_timeout_is_an_llmerror_without_the_key():
    with pytest.raises(LLMError, match="CEA_LLM_TIMEOUT") as info:
        client_from_env({"CEA_LLM_BASE_URL": "https://e.invalid/v1", "CEA_LLM_MODEL": "g",
                         "CEA_LLM_API_KEY": DUMMY_KEY, "CEA_LLM_TIMEOUT": "soon"}, env_file=None)
    assert DUMMY_KEY not in str(info.value)


def test_env_file_is_read_and_environment_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nexport CEA_LLM_FALLBACK_MODEL='from-file'\n"
                        "CEA_LLM_FALLBACK_BASE_URL=\"http://127.0.0.1:8/v1\"\nnot a pair\n", encoding="utf-8")
    assert read_env_file(env_file) == {"CEA_LLM_FALLBACK_MODEL": "from-file",
                                       "CEA_LLM_FALLBACK_BASE_URL": "http://127.0.0.1:8/v1"}
    c = client_from_env({"CEA_LLM_FALLBACK_MODEL": "from-env"}, env_file=env_file)
    assert (c.model, c.url) == ("from-env", "http://127.0.0.1:8/v1/chat/completions")
    assert read_env_file(tmp_path / "missing.env") == {}


# ---------------------------------------------------------------- repo files of this plan
def test_env_example_lists_every_variable_and_no_key_value():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    values = read_env_file(ROOT / ".env.example")
    for name in ("CEA_LLM_BASE_URL", "CEA_LLM_API_KEY", "CEA_LLM_MODEL",
                 "CEA_LLM_FALLBACK_BASE_URL", "CEA_LLM_FALLBACK_MODEL"):
        assert name in values, name
    assert values["CEA_LLM_API_KEY"] == ""
    assert "generativelanguage.googleapis.com/v1beta/openai/" in text


def test_requirements_dev_includes_runtime_requirements():
    lines = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
    assert "-r requirements.txt" in lines
    assert (ROOT / "requirements.txt").is_file()


def test_smoke_script_skips_without_configuration():
    env = {k: v for k, v in os.environ.items() if not k.startswith("CEA_LLM_")}
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "llm_smoke.py"), "--no-env-file"],
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT, env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("SKIPPED: no LLM configured")
