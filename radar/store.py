"""SQLite storage. One file, WAL mode, safe for the poller + server threads."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY,
    fingerprint  TEXT UNIQUE,
    title        TEXT NOT NULL,
    url          TEXT,
    domain       TEXT,
    outlet       TEXT,
    lang         TEXT,
    kind         TEXT,              -- news | video | trendnews
    published_at TEXT,
    first_seen   TEXT NOT NULL,
    entities     TEXT,              -- comma separated lexicon keys
    cluster_id   INTEGER,
    rank         INTEGER            -- position in a ranked feed (Google top stories), else NULL
);
CREATE INDEX IF NOT EXISTS idx_items_first_seen ON items(first_seen);
CREATE INDEX IF NOT EXISTS idx_items_cluster    ON items(cluster_id);

CREATE TABLE IF NOT EXISTS clusters (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    title_en    TEXT,
    summary     TEXT,
    signature   TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    score       REAL DEFAULT 0,
    peak_score  REAL DEFAULT 0,
    breakdown   TEXT,
    trend_query TEXT,
    picture     TEXT
);
CREATE INDEX IF NOT EXISTS idx_clusters_last_seen ON clusters(last_seen);

CREATE TABLE IF NOT EXISTS trends (
    id         INTEGER PRIMARY KEY,
    query      TEXT NOT NULL,
    geo        TEXT NOT NULL,
    traffic    INTEGER DEFAULT 0,
    prev_traffic INTEGER DEFAULT 0,
    rank       INTEGER DEFAULT 0,
    prev_rank  INTEGER DEFAULT 0,
    peak_traffic INTEGER DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    picture    TEXT,
    entities   TEXT,
    UNIQUE(query, geo)
);

CREATE TABLE IF NOT EXISTS trend_history (
    query   TEXT NOT NULL,
    geo     TEXT NOT NULL,
    ts      TEXT NOT NULL,
    traffic INTEGER,
    rank    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_trend_hist ON trend_history(query, geo, ts);

CREATE TABLE IF NOT EXISTS source_health (
    name       TEXT PRIMARY KEY,
    url        TEXT,
    kind       TEXT,
    last_ok    TEXT,
    last_fail  TEXT,
    last_error TEXT,
    failures   INTEGER DEFAULT 0,   -- consecutive
    last_count INTEGER DEFAULT 0,
    last_ms    INTEGER DEFAULT 0,
    total_ok   INTEGER DEFAULT 0,
    total_fail INTEGER DEFAULT 0,
    fresh_count INTEGER DEFAULT 0,  -- items inside the freshness window, last poll
    last_fresh TEXT                 -- when this source last produced a fresh item
);

CREATE TABLE IF NOT EXISTS sections (
    section      TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT,
    outlet       TEXT,
    lang         TEXT,
    published_at TEXT,
    rank         INTEGER,
    ts           TEXT NOT NULL,
    PRIMARY KEY (section, title)
);

CREATE TABLE IF NOT EXISTS reading (
    source  TEXT NOT NULL,
    title   TEXT NOT NULL,
    url     TEXT,
    rank    INTEGER,
    views   INTEGER,
    ts      TEXT NOT NULL,
    PRIMARY KEY (source, title)
);

CREATE TABLE IF NOT EXISTS cluster_history (
    cluster_id INTEGER NOT NULL,
    ts         TEXT NOT NULL,
    score      REAL,
    item_count INTEGER,
    outlets    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_hist ON cluster_history(cluster_id, ts);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY,
    cluster_id INTEGER NOT NULL,
    ts         TEXT NOT NULL,
    score      REAL,
    delivered  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def conn() -> sqlite3.Connection:
    """Thread-local connection — sqlite objects are not shareable."""
    existing = getattr(_local, "conn", None)
    if existing is not None:
        return existing
    c = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    _local.conn = c
    return c


# Columns added after the first release. init() adds any that are missing so
# an existing radar.db keeps working across upgrades without being rebuilt.
_MIGRATIONS = {
    "trends": [
        ("rank", "INTEGER DEFAULT 0"),
        ("prev_rank", "INTEGER DEFAULT 0"),
        ("peak_traffic", "INTEGER DEFAULT 0"),
    ],
    "items": [
        ("rank", "INTEGER"),
    ],
    "source_health": [
        ("fresh_count", "INTEGER DEFAULT 0"),
        ("last_fresh", "TEXT"),
    ],
}


def init() -> None:
    c = conn()
    c.executescript(SCHEMA)
    for table, columns in _MIGRATIONS.items():
        have = {row["name"] for row in c.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns:
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def record_source(name: str, url: str, kind: str, ok: bool,
                  count: int = 0, ms: int = 0, error: str = "",
                  fresh: int = 0) -> None:
    """One line per source per poll: the raw material for the health strip.

    `fresh` is how many of the items were inside the freshness window. A feed
    that answers every time but has not produced a fresh item in a day is, for
    this radar's purposes, dead — and the strip says so.
    """
    now = now_iso()
    c = conn()
    c.execute(
        "INSERT OR IGNORE INTO source_health(name, url, kind) VALUES (?,?,?)",
        (name, url, kind),
    )
    if ok:
        c.execute(
            """UPDATE source_health SET url=?, kind=?, last_ok=?, failures=0,
               last_count=?, last_ms=?, total_ok=total_ok+1, last_error='',
               fresh_count=?, last_fresh=CASE WHEN ?>0 THEN ? ELSE last_fresh END
               WHERE name=?""",
            (url, kind, now, count, ms, fresh, fresh, now, name),
        )
    else:
        c.execute(
            """UPDATE source_health SET url=?, kind=?, last_fail=?, last_error=?,
               failures=failures+1, last_ms=?, total_fail=total_fail+1 WHERE name=?""",
            (url, kind, now, error[:120], ms, name),
        )


def source_health() -> list[dict]:
    rows = conn().execute(
        "SELECT * FROM source_health ORDER BY failures DESC, name"
    ).fetchall()
    return [dict(r) for r in rows]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_meta(key: str, default: str = "") -> str:
    row = conn().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key: str, value: str) -> None:
    conn().execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def housekeeping() -> None:
    """Drop rows past the retention window and clusters left with no items."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.RETENTION_DAYS)).isoformat()
    c = conn()
    c.execute("DELETE FROM items WHERE first_seen < ?", (cutoff,))
    hist_cutoff = (datetime.now(timezone.utc)
                   - timedelta(days=config.HISTORY_RETENTION_DAYS)).isoformat()
    c.execute("DELETE FROM cluster_history WHERE ts < ?", (hist_cutoff,))
    c.execute("DELETE FROM trend_history WHERE ts < ?", (hist_cutoff,))
    c.execute("DELETE FROM alerts WHERE ts < ?", (cutoff,))
    c.execute(
        "DELETE FROM clusters WHERE last_seen < ? "
        "AND id NOT IN (SELECT DISTINCT cluster_id FROM items WHERE cluster_id IS NOT NULL)",
        (cutoff,),
    )
    c.execute("DELETE FROM trends WHERE last_seen < ?", (cutoff,))
    c.execute("DELETE FROM reading WHERE ts < ?", (hist_cutoff,))
    c.execute("DELETE FROM sections WHERE ts < ?", (hist_cutoff,))
    # A source that has been removed from config stops being written to; after
    # two days without a poll its row is retired so the strip stays truthful.
    # SQLite's scalar MAX() returns NULL if any argument is NULL, which would
    # retire every source that has never failed. Coalesce each side first.
    c.execute(
        "DELETE FROM source_health "
        "WHERE MAX(COALESCE(last_ok, ''), COALESCE(last_fail, '')) < ?",
        (hist_cutoff,),
    )
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
