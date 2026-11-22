"""Tiny SQLite persistence layer (analyses + runtime settings)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .config import get_settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(get_settings().db_path, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    owner TEXT, repo TEXT, ref TEXT,
                    status TEXT NOT NULL,
                    progress REAL DEFAULT 0,
                    step TEXT DEFAULT '',
                    steps TEXT DEFAULT '[]',
                    error TEXT,
                    result TEXT,
                    created_at REAL, updated_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_analyses_url ON analyses(url);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
                """
            )
            # Any job that was running when the server stopped can never finish.
            _conn.execute(
                "UPDATE analyses SET status='failed', error='Server restarted during analysis' "
                "WHERE status IN ('queued','running')"
            )
            _conn.commit()
        return _conn


def create_analysis(aid: str, url: str, owner: str, repo: str, ref: str | None) -> None:
    now = time.time()
    with _lock:
        conn().execute(
            "INSERT INTO analyses (id,url,owner,repo,ref,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (aid, url, owner, repo, ref, "queued", now, now),
        )
        conn().commit()


def update_analysis(aid: str, **fields: Any) -> None:
    if not fields:
        return
    if "result" in fields and not isinstance(fields["result"], str):
        fields["result"] = json.dumps(fields["result"], default=str)
    if "steps" in fields and not isinstance(fields["steps"], str):
        fields["steps"] = json.dumps(fields["steps"])
    fields["updated_at"] = time.time()
    cols = ",".join(f"{k}=?" for k in fields)
    with _lock:
        conn().execute(f"UPDATE analyses SET {cols} WHERE id=?", (*fields.values(), aid))
        conn().commit()


def _row(r: sqlite3.Row | None, with_result: bool) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    d["steps"] = json.loads(d.get("steps") or "[]")
    if with_result:
        d["result"] = json.loads(d["result"]) if d.get("result") else None
    else:
        d.pop("result", None)
    return d


def get_analysis(aid: str, with_result: bool = True) -> dict | None:
    with _lock:
        r = conn().execute("SELECT * FROM analyses WHERE id=?", (aid,)).fetchone()
    return _row(r, with_result)


def list_analyses(limit: int = 50) -> list[dict]:
    with _lock:
        rows = conn().execute(
            "SELECT id,url,owner,repo,ref,status,progress,step,steps,error,created_at,updated_at,"
            "json_extract(result,'$.meta.description') AS description,"
            "json_extract(result,'$.quality.score') AS score,"
            "json_extract(result,'$.languages[0].name') AS language "
            "FROM analyses ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row(r, False) for r in rows]  # type: ignore[misc]


def find_recent_done(url: str, max_age_s: float) -> dict | None:
    with _lock:
        r = conn().execute(
            "SELECT id FROM analyses WHERE url=? AND status='done' AND created_at>? ORDER BY created_at DESC LIMIT 1",
            (url, time.time() - max_age_s),
        ).fetchone()
    return dict(r) if r else None


def delete_analysis(aid: str) -> None:
    with _lock:
        conn().execute("DELETE FROM analyses WHERE id=?", (aid,))
        conn().commit()


def get_setting(key: str, default: Any = None) -> Any:
    with _lock:
        r = conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(key: str, value: Any) -> None:
    with _lock:
        conn().execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        conn().commit()
