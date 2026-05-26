"""SQLite 状态库：流水线的唯一事实来源。

每个段落是一行。翻译进度、断点续跑、监控面板都基于这张表。
"""
import sqlite3
import time
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS segments (
    id         INTEGER PRIMARY KEY,
    juan_no    INTEGER NOT NULL,   -- 卷号（文件序号）
    seq        INTEGER NOT NULL,   -- 全书全局顺序
    local_no   INTEGER NOT NULL,   -- 卷内顺序
    kind       TEXT NOT NULL,      -- juan | heading | byline | para | verse
    level      INTEGER DEFAULT 0,  -- heading 层级
    source     TEXT NOT NULL,      -- 原文（繁体）
    n_chars    INTEGER NOT NULL,
    translated TEXT,               -- 译文（简体白话）
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending | done | error
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_status ON segments(status);
CREATE INDEX IF NOT EXISTS idx_seq ON segments(seq);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(readonly: bool = False) -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        uri = f"file:{config.DB_PATH}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30)
    else:
        conn = sqlite3.connect(config.DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def set_meta(conn, key: str, value) -> None:
    conn.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def add_meta_number(conn, key: str, delta: float) -> None:
    cur = float(get_meta(conn, key, 0) or 0)
    set_meta(conn, key, cur + delta)


def stats(conn) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) n, COALESCE(SUM(n_chars),0) c "
        "FROM segments GROUP BY status"
    ).fetchall()
    out = {"pending": (0, 0), "done": (0, 0), "error": (0, 0)}
    for r in rows:
        out[r["status"]] = (r["n"], r["c"])
    total_n = sum(v[0] for v in out.values())
    total_c = sum(v[1] for v in out.values())
    return {
        "total_n": total_n, "total_c": total_c,
        "done_n": out["done"][0], "done_c": out["done"][1],
        "pending_n": out["pending"][0], "pending_c": out["pending"][1],
        "error_n": out["error"][0], "error_c": out["error"][1],
    }
