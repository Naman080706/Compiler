"""Compile analytics: per-student event log and GET /api/profile/{id}/analytics."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from cea import api
from cea.pipeline import compile_source
from cea.profile import ProfileStore

SID = "stu_0123456789abcdef"
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
BAD = "int main() { x = 1; return 0 }\n"
GOOD = "int main() { return 0; }\n"


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "p.sqlite3")


@pytest.fixture
def client(store, monkeypatch):
    api.app.dependency_overrides[api.get_profiles] = lambda: store
    real = store.analytics
    monkeypatch.setattr(store, "analytics", lambda sid, days=30, now=None: real(sid, days, NOW))
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def log(store, source, days_ago=0, sid=SID):
    res = compile_source(source, "main.c")
    store.record_event(sid, res.errors, [c.root for c in res.clusters], res.engine, NOW - timedelta(days=days_ago))
    return res


def test_empty_profile(client):
    data = client.get(f"/api/profile/{SID}/analytics").json()
    assert len(data["daily"]) == 30
    assert all(d["compiles"] == 0 for d in data["daily"])
    assert data["totals"] == {"compiles": 0, "successful": 0, "success_rate": 0.0, "errors": 0, "avg_errors": 0.0}
    assert data["streak"] == 0 and data["recent"] == [] and data["top_codes"] == []
    assert data["trend"]["direction"] == "flat"


def test_zero_filled_days_and_totals(client, store):
    bad = log(store, BAD, 0)
    log(store, GOOD, 0)
    log(store, BAD, 5)
    data = client.get(f"/api/profile/{SID}/analytics?days=7").json()
    assert len(data["daily"]) == 7 and data["daily"][-1]["date"] == "2026-10-14"
    by = {d["date"]: d for d in data["daily"]}
    fatal = len([r for r in bad.errors if r.severity == "fatal"])
    assert by["2026-10-14"] == {"date": "2026-10-14", "compiles": 2, "successful": 1, "errors": fatal}
    assert by["2026-10-13"]["compiles"] == 0
    assert data["totals"]["compiles"] == 3 and data["totals"]["successful"] == 1
    assert data["totals"]["success_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert data["top_codes"][0]["count"] >= 1
    assert sum(p["count"] for p in data["phases"]) == data["totals"]["errors"]
    assert len(data["recent"]) == 3 and data["recent"][0]["ok"] is True


def test_streak(client, store):
    for d in (0, 1, 2, 4):
        log(store, GOOD, d)
    assert client.get(f"/api/profile/{SID}/analytics").json()["streak"] == 3
    log(store, GOOD, 1, sid="stu_other_000000")
    assert client.get("/api/profile/stu_other_000000/analytics").json()["streak"] == 1  # yesterday still counts


def test_trend_down(client, store):
    log(store, BAD, 25)
    log(store, GOOD, 1)
    t = client.get(f"/api/profile/{SID}/analytics").json()["trend"]
    assert t["direction"] == "down" and t["first_half"] > t["second_half"] == 0


def test_compile_records_event_without_source_and_reset_clears(client, store):
    client.post("/api/compile", json={"source": BAD, "student_id": SID})
    dump = "\n".join(str(r) for r in sqlite3.connect(store.path).execute("SELECT * FROM compile_events"))
    assert dump and "main()" not in dump and "return" not in dump
    client.post("/api/compile", json={"source": GOOD})  # no student id: nothing logged
    assert len(sqlite3.connect(store.path).execute("SELECT * FROM compile_events").fetchall()) == 1
    client.delete(f"/api/profile/{SID}")
    assert sqlite3.connect(store.path).execute("SELECT COUNT(*) FROM compile_events").fetchone()[0] == 0


def test_bad_inputs(client):
    assert client.get("/api/profile/bad/analytics").status_code == 422
    assert client.get(f"/api/profile/{SID}/analytics?days=0").status_code == 422
