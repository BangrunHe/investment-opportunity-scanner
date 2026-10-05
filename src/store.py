"""估值数据 SQLite 归档：历史快照累积、去重、读取。"""

import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "valuations.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS valuations (
    index_code TEXT NOT NULL,
    date       TEXT NOT NULL,
    ts         INTEGER,
    pe         REAL,
    pb         REAL,
    pe_percent REAL,
    pb_percent REAL,
    roe        REAL,
    yeild      REAL,
    PRIMARY KEY (index_code, date)
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_SCHEMA)
    return conn


def save_records(records) -> int:
    """写入估值记录（(index_code, date) 重复则覆盖），返回写入条数。"""
    if not records:
        return 0
    conn = connect()
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO valuations
                (index_code, date, ts, pe, pb, pe_percent, pb_percent, roe, yeild)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r["index_code"],
                    r["date"],
                    r.get("ts"),
                    r.get("pe"),
                    r.get("pb"),
                    r.get("pe_percent"),
                    r.get("pb_percent"),
                    r.get("roe"),
                    r.get("yeild"),
                )
                for r in records
            ],
        )
        conn.commit()
        return len(records)
    finally:
        conn.close()


def load_history(index_code: str) -> list:
    """按日期升序返回某指数的全部历史记录。"""
    conn = connect()
    try:
        cur = conn.execute(
            """
            SELECT index_code, date, ts, pe, pb, pe_percent, pb_percent, roe, yeild
            FROM valuations WHERE index_code = ? ORDER BY date ASC
            """,
            (index_code,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def load_latest() -> list:
    """返回每个指数最新一天快照的记录列表。"""
    conn = connect()
    try:
        cur = conn.execute(
            """
            SELECT v.index_code, v.date, v.ts, v.pe, v.pb,
                   v.pe_percent, v.pb_percent, v.roe, v.yeild
            FROM valuations v
            JOIN (
                SELECT index_code, MAX(date) AS max_date
                FROM valuations GROUP BY index_code
            ) m ON v.index_code = m.index_code AND v.date = m.max_date
            """
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
