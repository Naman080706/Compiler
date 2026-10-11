"""OpenAICompatClient and FallbackClient against a local fake HTTP server (plan 010).

The server is stdlib ``http.server`` on 127.0.0.1 in a background thread; it
records every request and answers from a per-test script. No test reaches the
real network. The key used here is a dummy string.
"""
import json
import logging
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cea.llm import FallbackClient, FakeLLM, LLMError, OpenAICompatClient

DUMMY_KEY = "dummy-key-0123456789-DO-NOT-USE"


def ok_body(content):
    return {"id": "x", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}]}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                     "body": json.loads(raw.decode("utf-8"))})
        status, payload, delay = self.server.script.pop(0) if self.server.script else (200, ok_body("default"), 0)
        if payload == "ECHO_AUTH":                      # a provider that echoes the auth header in its error
            payload = {"error": {"message": f"bad credentials: {self.headers.get('Authorization')}"}}
        if delay:
            time.sleep(delay)
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass                                         # the client already gave up (timeout test)

    def log_message(self, *args):
        pass                                             # keep pytest output clean


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        pass


@pytest.fixture
def server():
    srv = _Server(("127.0.0.1", 0), _Handler)
    srv.requests, srv.script = [], []
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    srv.base_url = f"http://127.0.0.1:{srv.server_address[1]}/v1/"
    yield srv
    srv.shutdown()
    srv.server_close()


def client(srv, **kw):
    kw.setdefault("timeout", 5.0)
    return OpenAICompatClient(srv.base_url, "test-model", DUMMY_KEY, **kw)


MSGS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "héllo"}]


# ---------------------------------------------------------------- request and response
def test_request_shape_and_reply(server):
    server.script.append((200, ok_body("Hi there ✓"), 0))
    assert client(server).complete(MSGS, max_tokens=123, temperature=0.0) == "Hi there ✓"
    (req,) = server.requests
    assert req["path"] == "/v1/chat/completions"                       # trailing slash of base_url handled
    assert req["headers"]["authorization"] == f"Bearer {DUMMY_KEY}"
    assert req["headers"]["content-type"] == "application/json"
    assert req["body"] == {"model": "test-model", "messages": MSGS, "max_tokens": 123, "temperature": 0.0}


def test_json_schema_becomes_response_format(server):
    schema = {"type": "object", "properties": {"explanation": {"type": "string"}}, "required": ["explanation"]}
    server.script.append((200, ok_body('{"explanation": "x"}'), 0))
    assert client(server).complete(MSGS, json_schema=schema) == '{"explanation": "x"}'
    body = server.requests[0]["body"]
    assert body["response_format"] == {"type": "json_schema",
                                       "json_schema": {"name": "cea_response", "schema": schema}}
    assert (body["max_tokens"], body["temperature"]) == (400, 0.2)       # contract defaults


def test_no_key_sends_no_authorization_header(server):
    server.script.append((200, ok_body("ok"), 0))
    OpenAICompatClient(server.base_url, "m", None, timeout=5).complete(MSGS)
    assert "authorization" not in server.requests[0]["headers"]


# ---------------------------------------------------------------- error mapping
@pytest.mark.parametrize("status,payload,fragment", [
    (401, {"error": {"message": "API key not valid"}}, "HTTP 401"),
    (429, {"error": {"message": "quota exceeded"}}, "HTTP 429"),
    (500, b"<html>oops</html>", "HTTP 500"),
    (200, b"not json at all", "malformed response"),
    (200, {"choices": []}, "malformed response"),
    (200, {"choices": [{"message": {"content": None}}]}, "empty completion"),
    (200, ok_body("   "), "empty completion"),
])
def test_errors_map_to_llmerror(server, status, payload, fragment):
    server.script.append((status, payload, 0))
    with pytest.raises(LLMError) as info:
        client(server).complete(MSGS)
    assert fragment in str(info.value)
    assert info.value.status == (status if status != 200 else None)


def test_timeout_maps_to_llmerror(server):
    server.script.append((200, ok_body("late"), 1.5))
    with pytest.raises(LLMError, match="timed out"):
        client(server, timeout=0.3).complete(MSGS)


def test_unreachable_server_maps_to_llmerror():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]                       # closed again: nothing listens there
    c = OpenAICompatClient(f"http://127.0.0.1:{port}/v1", "m", DUMMY_KEY, timeout=1.0)
    with pytest.raises(LLMError) as info:
        c.complete(MSGS)
    assert DUMMY_KEY not in str(info.value)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/v1", "localhost:11434/v1"])
def test_only_http_urls_are_accepted(url):
    with pytest.raises(ValueError):
        OpenAICompatClient(url, "m")


# ---------------------------------------------------------------- the key never leaks
def test_key_not_in_error_message_logs_or_repr(server, caplog):
    caplog.set_level(logging.DEBUG, logger="cea.llm")
    server.script.append((401, "ECHO_AUTH", 0))
    c = client(server)
    with pytest.raises(LLMError) as info:
        c.complete(MSGS)
    assert "bad credentials: Bearer ***" in str(info.value)             # the echoed key was redacted
    assert DUMMY_KEY not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert DUMMY_KEY not in caplog.text
    assert DUMMY_KEY not in repr(c) and "api_key=set" in repr(c)


def test_key_not_in_fallback_error(server, caplog):
    caplog.set_level(logging.DEBUG, logger="cea.llm")
    server.script += [(401, "ECHO_AUTH", 0), (503, "ECHO_AUTH", 0)]
    fb = FallbackClient(client(server, name="primary"), client(server, name="fallback"))
    with pytest.raises(LLMError) as info:
        fb.complete(MSGS)
    text = str(info.value)
    assert "primary failed" in text and "fallback failed" in text and info.value.status == 503
    assert DUMMY_KEY not in text and DUMMY_KEY not in caplog.text and DUMMY_KEY not in repr(fb)


# ---------------------------------------------------------------- fallback
def test_fallback_used_when_primary_fails(server):
    server.script += [(429, {"error": {"message": "quota"}}, 0), (200, ok_body("from fallback"), 0)]
    fb = FallbackClient(client(server, name="primary"), client(server, name="fallback"))
    assert fb.complete(MSGS, json_schema={"type": "object"}, max_tokens=50) == "from fallback"
    assert fb.last_used == "fallback"
    assert len(server.requests) == 2
    assert server.requests[0]["body"] == server.requests[1]["body"]     # same request sent to both


def test_primary_success_skips_fallback():
    primary, fallback = FakeLLM(["primary says hi"]), FakeLLM(["never"])
    fb = FallbackClient(primary, fallback)
    assert fb.complete(MSGS) == "primary says hi"
    assert fb.last_used == "primary" and len(fallback.calls) == 0


def test_fallback_passes_arguments_through():
    primary, fallback = FakeLLM([LLMError("down")]), FakeLLM(["ok"])
    FallbackClient(primary, fallback).complete(MSGS, json_schema={"type": "object"}, max_tokens=7, temperature=0.5)
    assert fallback.calls[0]["json_schema"] == {"type": "object"}
    assert (fallback.calls[0]["max_tokens"], fallback.calls[0]["temperature"]) == (7, 0.5)
