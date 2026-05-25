import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from core.config import cfg

_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(cfg.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db() -> None:
    c = _get_conn()
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id   TEXT    NOT NULL UNIQUE,
            source     TEXT    NOT NULL,
            user_id    TEXT,
            session_id TEXT,
            hash       TEXT,
            data       TEXT,
            tags       TEXT,
            timestamp  REAL    NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_source    ON events(source)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_user_id   ON events(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
    c.commit()


def insert_event(record: Dict[str, Any]) -> None:
    c = _get_conn()
    c.execute(
        """INSERT OR IGNORE INTO events
           (event_id, source, user_id, session_id, hash, data, tags, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record["event_id"],
            record.get("source", ""),
            record.get("user_id", ""),
            record.get("session_id", ""),
            record.get("hash", ""),
            json.dumps(record.get("data", {})),
            json.dumps(record.get("tags", [])),
            record.get("timestamp", time.time()),
        ),
    )
    c.commit()


def query_events(
    source:   Optional[str] = None,
    user_id:  Optional[str] = None,
    limit:    int           = 100,
    offset:   int           = 0,
) -> List[Dict[str, Any]]:
    c   = _get_conn()
    sql = "SELECT * FROM events WHERE 1=1"
    args: list = []
    if source:
        sql += " AND source = ?"; args.append(source)
    if user_id:
        sql += " AND user_id = ?"; args.append(user_id)
    sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    rows = c.execute(sql, args).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["data"] = json.loads(d["data"] or "{}")
        d["tags"] = json.loads(d["tags"] or "[]")
        result.append(d)
    return result
