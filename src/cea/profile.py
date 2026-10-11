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

import os
import re
import sqlite3
import threading
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
            finally:
                conn.close()
