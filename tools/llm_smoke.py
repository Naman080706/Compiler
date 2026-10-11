"""Optional live smoke test of the configured LLM (plan 010). NOT part of pytest.

Sends one tiny JSON-schema request through ``cea.llm.client_from_env()`` and
prints which provider answered, the latency and the parsed reply. It never
prints the API key. With nothing configured it prints ``SKIPPED: ...`` and
exits 0 without any network access.

Usage (from the project root):
    python tools/llm_smoke.py                 # reads .env, then the environment
    python tools/llm_smoke.py --no-env-file   # environment variables only

Exit status: 0 success or skipped, 1 the LLM call failed.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cea.llm import FallbackClient, LLMError, client_from_env  # noqa: E402
from cea.llm.config import DEFAULT_ENV_FILE  # noqa: E402

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
MESSAGES = [
    {"role": "system", "content": "Reply with a single JSON object only."},
    {"role": "user", "content": 'In C, which character ends a statement? Reply as {"answer": "<character>"}.'},
]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python tools/llm_smoke.py", description=__doc__.splitlines()[0])
    ap.add_argument("--no-env-file", action="store_true", help="ignore the .env file")
    args = ap.parse_args(argv)
    try:
        client = client_from_env(env_file=None if args.no_env_file else DEFAULT_ENV_FILE)
    except LLMError as exc:
        print(f"SKIPPED: {exc}")
        return 0
    started = time.monotonic()
    try:
        text = client.complete(MESSAGES, json_schema=SCHEMA, max_tokens=100, temperature=0.0)
    except LLMError as exc:
        print(f"FAILED: {exc}")
        return 1
    elapsed = time.monotonic() - started
    used = client
    if isinstance(client, FallbackClient):
        used = client.primary if client.last_used == "primary" else client.fallback
    print(f"OK: provider={used.name} model={used.model} seconds={elapsed:.2f}")
    print(f"raw reply: {text!r}")
    try:
        print(f"parsed: {json.loads(text)}")
    except ValueError:
        print("parsed: (reply is not valid JSON)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
