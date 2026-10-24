"""PRD F9: the personalised error model (stdlib ``sqlite3``).

One local database (``.cea_data/profiles.sqlite3``) keeps, per pseudonymous student id, a
count of errors per catalog CATEGORY across sessions. The id is a random token made by the
browser; the server only uses it as a key and it is never put in an LLM message.

Counting (``record_compile``): each ROOT cluster counts once per compile, and the same error
signature (code, rule_ref, found, message; no line numbers) counts at most once per session.
A category with ``THRESHOLD`` or more hits earns fuller explanations (``beginner`` verbosity
plus a worked example); other categories stay terse (``expert`` verbosity). The manual F5
toggle always overrides (``choose_depth``). ``reset`` deletes everything stored for an id.
Nothing here prints.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from collections.abc import Iterable
from pathlib import Path

from cea.catalog import REPO_ROOT, load_catalog
from cea.records import ErrorRecord

THRESHOLD = 3
DEFAULT_DB = REPO_ROOT / ".cea_data" / "profiles.sqlite3"
STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
DEFAULT_SESSION = "default"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS category_counts (
    student_id TEXT NOT NULL, category TEXT NOT NULL, hits INTEGER NOT NULL,
    PRIMARY KEY (student_id, category));
CREATE TABLE IF NOT EXISTS seen (
    student_id TEXT NOT NULL, session_id TEXT NOT NULL, signature TEXT NOT NULL,
    PRIMARY KEY (student_id, session_id, signature));
CREATE TABLE IF NOT EXISTS compile_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, ts TEXT NOT NULL,
    ok INTEGER NOT NULL, fatal INTEGER NOT NULL, warnings INTEGER NOT NULL,
    phases TEXT NOT NULL, categories TEXT NOT NULL, codes TEXT NOT NULL, engine TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS compile_events_student ON compile_events (student_id, ts);
CREATE TABLE IF NOT EXISTS action_counts (
    student_id TEXT NOT NULL, action TEXT NOT NULL, count INTEGER NOT NULL,
    PRIMARY KEY (student_id, action));
"""


def valid_student_id(value: object) -> bool:
    return isinstance(value, str) and STUDENT_ID_RE.fullmatch(value) is not None


def category_of(record: ErrorRecord) -> str | None:
    entry = load_catalog().get(record.code)
    return entry.category if entry is not None else None


def signature_of(record: ErrorRecord) -> str:
    """The error signature: what the error is, not where it is."""
    return "|".join((record.code, record.rule_ref, record.found, record.message))


def choose_depth(verbosity: str | None, hits: int) -> tuple[str, bool]:
    """(verbosity, worked_example) for one explanation.

    An explicit F5 choice always wins and gets no automatic example. Otherwise a category with
    THRESHOLD or more hits gets ("beginner", True) and any other category ("expert", False).
    """
    if verbosity in ("beginner", "expert"):
        return verbosity, False
    return ("beginner", True) if hits >= THRESHOLD else ("expert", False)


class ProfileStore:
    def __init__(self, path: Path | str | None = None):
        if path is None:
            path = os.environ.get("CEA_PROFILE_DB") or DEFAULT_DB
        self.path = Path(path)
        self._lock = threading.Lock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        if not self._ready:
            conn.executescript(_SCHEMA)
            self._ready = True
        return conn

    def record_compile(self, student_id: str, session_id: str | None, roots: Iterable[ErrorRecord]) -> None:
        """Count the root clusters of one compile (once each; a signature once per session)."""
        session = session_id or DEFAULT_SESSION
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    for rec in roots:
                        category = category_of(rec)
                        if category is None:
                            continue
                        added = conn.execute("INSERT OR IGNORE INTO seen VALUES (?, ?, ?)",
                                             (student_id, session, signature_of(rec))).rowcount
                        if added:
                            conn.execute(
                                "INSERT INTO category_counts VALUES (?, ?, 1) ON CONFLICT(student_id, category) "
                                "DO UPDATE SET hits = hits + 1", (student_id, category))
            finally:
                conn.close()

    def record_event(self, student_id: str, records: Iterable[ErrorRecord], roots: Iterable[ErrorRecord],
                     engine: str, when: datetime | None = None) -> None:
        """Log one compile for the analytics: counts and codes only, never the source code."""
        records = list(records)
        fatal = [r for r in records if r.severity == "fatal"]
        phases = Counter(r.phase for r in fatal)
        roots = list(roots)
        codes = Counter(r.code for r in roots)
        cats = Counter(c for c in (category_of(r) for r in roots) if c)
        ts = (when or datetime.now(UTC)).astimezone(UTC).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO compile_events (student_id, ts, ok, fatal, warnings, phases, categories, codes, engine) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (student_id, ts, int(not fatal), len(fatal), len(records) - len(fatal),
                         json.dumps(phases), json.dumps(cats), json.dumps(codes), engine))
            finally:
                conn.close()

    def analytics(self, student_id: str, days: int = 30, now: datetime | None = None,
                  tz_offset_minutes: int = 0) -> dict:
        """Dashboard numbers for the last ``days`` local days (today included), zero-filled.

        ``tz_offset_minutes`` is the viewer's offset east of UTC (IST = +330), so days and times
        follow the student's own calendar. Timestamps are still stored in UTC.
        """
        shift = timedelta(minutes=tz_offset_minutes)
        now = (now or datetime.now(UTC)).astimezone(UTC) + shift
        today = now.date()
        start = today - timedelta(days=days - 1)
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT ts, ok, fatal, warnings, phases, categories, codes, engine "
                                    "FROM compile_events WHERE student_id = ? ORDER BY ts, id", (student_id,)).fetchall()
                corr_row = conn.execute("SELECT count FROM action_counts WHERE student_id = ? AND action = 'correct'",
                                        (student_id,)).fetchone()
            finally:
                conn.close()
        corrections = corr_row[0] if corr_row else 0
        events = [(datetime.fromisoformat(r[0]).astimezone(UTC) + shift, *r[1:]) for r in rows]
        active = {e[0].date() for e in events}
        streak, day = 0, today if today in active else today - timedelta(days=1)
        while day in active:
            streak += 1
            day -= timedelta(days=1)
        window = [e for e in events if start <= e[0].date() <= today]
        series = {start + timedelta(days=i): {"compiles": 0, "successful": 0, "errors": 0} for i in range(days)}
        phases: Counter = Counter()
        codes: Counter = Counter()
        cats: Counter = Counter()
        first = [0, 0]
        second = [0, 0]
        half = start + timedelta(days=days // 2)
        for ts, ok, fatal, _w, ph, ct, cd, _eng in window:
            d = series[ts.date()]
            d["compiles"] += 1
            d["successful"] += ok
            d["errors"] += fatal
            phases.update(json.loads(ph))
            cats.update(json.loads(ct))
            codes.update(json.loads(cd))
            bucket = first if ts.date() < half else second
            bucket[0] += fatal
            bucket[1] += 1
        total = len(window)
        errors = sum(e[2] for e in window)
        avg_first = round(first[0] / first[1], 2) if first[1] else None
        avg_second = round(second[0] / second[1], 2) if second[1] else None
        if avg_first is None or avg_second is None or avg_first == avg_second:
            direction = "flat"
        else:
            direction = "down" if avg_second < avg_first else "up"
        top = lambda c, key: [{key: k, "count": n} for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]  # noqa: E731
        return {
            "student_id": student_id, "days": days,
            "daily": [{"date": d.isoformat(), **v} for d, v in series.items()],
            "totals": {"compiles": total, "successful": sum(e[1] for e in window),
                       "success_rate": round(sum(e[1] for e in window) / total, 4) if total else 0.0,
                       "errors": errors, "avg_errors": round(errors / total, 2) if total else 0.0},
            "streak": streak,
            "corrections": corrections,       # times the "Correct whole program" button was used (F8 whole-file)
            "phases": [{"phase": p, "count": phases.get(p, 0)} for p in ("lexical", "syntax", "semantic")],
            "top_codes": top(codes, "code"),
            "top_categories": top(cats, "category"),
            "trend": {"first_half": avg_first, "second_half": avg_second, "direction": direction},
            "recent": [{"ts": (e[0] - shift).isoformat(), "ok": bool(e[1]), "fatal": e[2], "warnings": e[3]}
                       for e in reversed(events[-10:])],
            "today": _day_summary(events, today, shift),
            "yesterday": _day_summary(events, today - timedelta(days=1), shift),
        }

    def record_action(self, student_id: str, action: str) -> None:
        """Count one use of a UI action (e.g. the whole-program ``correct`` button), per student."""
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO action_counts VALUES (?, ?, 1) ON CONFLICT(student_id, action) "
                        "DO UPDATE SET count = count + 1", (student_id, action))
            finally:
                conn.close()

    def action_count(self, student_id: str, action: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT count FROM action_counts WHERE student_id = ? AND action = ?",
                                   (student_id, action)).fetchone()
            finally:
                conn.close()
        return row[0] if row else 0

    def counts(self, student_id: str) -> dict[str, int]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT category, hits FROM category_counts WHERE student_id = ? "
                                    "ORDER BY category", (student_id,)).fetchall()
            finally:
                conn.close()
        return dict(rows)

    def hits(self, student_id: str, category: str | None) -> int:
        return self.counts(student_id).get(category or "", 0)

    def view(self, student_id: str) -> dict:
        """The student's profile as shown in the UI: counts and the depth each category gets."""
        counts = self.counts(student_id)
        return {"student_id": student_id, "threshold": THRESHOLD,
                "categories": [{"category": c, "hits": n, "depth": "full" if n >= THRESHOLD else "terse"}
                               for c, n in counts.items()]}

    def reset(self, student_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute("DELETE FROM category_counts WHERE student_id = ?", (student_id,))
                    conn.execute("DELETE FROM seen WHERE student_id = ?", (student_id,))
                    conn.execute("DELETE FROM compile_events WHERE student_id = ?", (student_id,))
                    conn.execute("DELETE FROM action_counts WHERE student_id = ?", (student_id,))
            finally:
                conn.close()


def _day_summary(events: list, day, shift: timedelta) -> dict:
    """One local day: totals, the most common mistake, and that day's compiles (newest first)."""
    todays = [e for e in events if e[0].date() == day]
    codes: Counter = Counter()
    for e in todays:
        codes.update(json.loads(e[6]))
    top = sorted(codes.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "date": day.isoformat(),
        "compiles": len(todays),
        "successful": sum(e[1] for e in todays),
        "errors": sum(e[2] for e in todays),
        "warnings": sum(e[3] for e in todays),
        "top_code": {"code": top[0][0], "count": top[0][1]} if top else None,
        "compiles_list": [{"ts": (e[0] - shift).isoformat(), "ok": bool(e[1]), "fatal": e[2], "warnings": e[3]}
                          for e in reversed(todays)],
    }
