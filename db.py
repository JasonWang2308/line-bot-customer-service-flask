import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "Chat History" / "session.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id      TEXT PRIMARY KEY,
                state        TEXT    DEFAULT 'idle',
                resolved_ids TEXT    DEFAULT '[]',
                pending_dims TEXT    DEFAULT '[]',
                current_dim  TEXT,
                raw_input    TEXT,
                turn_count   INTEGER DEFAULT 0,
                created_at   TEXT,
                updated_at   TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT,
                raw_input    TEXT,
                resolved_ids TEXT,
                status       TEXT,
                qa_id        TEXT,
                turn_count   INTEGER,
                created_at   TEXT,
                ended_at     TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT,
                display_name TEXT,
                content      TEXT,
                handled      INTEGER DEFAULT 0,
                created_at   TEXT
            )
        """)
        conn.commit()


# ── 讀取 ──────────────────────────────────────────────

def get_session(user_id: str) -> dict:
    """取得 session；不存在則回傳預設值（不寫入 DB）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ?", (user_id,)
        ).fetchone()

    if row is None:
        return {
            "user_id":      user_id,
            "state":        "idle",
            "resolved_ids": [],
            "pending_dims": [],
            "current_dim":  None,
            "raw_input":    None,
            "turn_count":   0,
            "created_at":   None,
            "updated_at":   None,
        }

    return {
        "user_id":      row["user_id"],
        "state":        row["state"],
        "resolved_ids": json.loads(row["resolved_ids"]),
        "pending_dims": json.loads(row["pending_dims"]),
        "current_dim":  row["current_dim"],
        "raw_input":    row["raw_input"],
        "turn_count":   row["turn_count"],
        "created_at":   row["created_at"],
        "updated_at":   row["updated_at"],
    }


# ── 寫入 ──────────────────────────────────────────────

def save_session(session: dict):
    """新增或更新整筆 session。"""
    now = _now()
    created = session.get("created_at") or now

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO sessions
                (user_id, state, resolved_ids, pending_dims, current_dim,
                 raw_input, turn_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                state        = excluded.state,
                resolved_ids = excluded.resolved_ids,
                pending_dims = excluded.pending_dims,
                current_dim  = excluded.current_dim,
                raw_input    = excluded.raw_input,
                turn_count   = excluded.turn_count,
                updated_at   = excluded.updated_at
        """, (
            session["user_id"],
            session["state"],
            json.dumps(session["resolved_ids"],  ensure_ascii=False),
            json.dumps(session["pending_dims"],  ensure_ascii=False),
            session.get("current_dim"),
            session.get("raw_input"),
            session.get("turn_count", 0),
            created,
            now,
        ))
        conn.commit()


def reset_session(user_id: str):
    """對話結束後清除 session，回到 idle。"""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE user_id = ?", (user_id,)
        )
        conn.commit()


# ── 對話記錄 ───────────────────────────────────────────

def log_conversation(session: dict, status: str, qa_id: str | None = None):
    """將已結束的對話寫入 conversations 永久記錄。"""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO conversations
                (user_id, raw_input, resolved_ids, status, qa_id, turn_count, created_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get("user_id"),
            session.get("raw_input"),
            json.dumps(session.get("resolved_ids", []), ensure_ascii=False),
            status,
            qa_id,
            session.get("turn_count", 0),
            session.get("created_at"),
            _now(),
        ))
        conn.commit()


# ── 留言 ──────────────────────────────────────────────

def save_message(user_id: str, display_name: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, display_name, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, display_name, content, _now())
        )
        conn.commit()


def get_messages(handled: int | None = None, start: str | None = None, end: str | None = None) -> list[dict]:
    sql = "SELECT * FROM messages"
    conditions = []
    params: list = []
    if handled is not None:
        conditions.append("handled = ?")
        params.append(handled)
    if start is not None:
        conditions.append("created_at >= ?")
        params.append(start)
    if end is not None:
        conditions.append("created_at < ?")
        params.append(end)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def mark_handled(msg_id: int, handled: int):
    with get_conn() as conn:
        conn.execute("UPDATE messages SET handled = ? WHERE id = ?", (handled, msg_id))
        conn.commit()


# ── 工具 ──────────────────────────────────────────────

def is_expired(session: dict, timeout_secs: int) -> bool:
    """回傳 True 表示 session 的最後更新時間已超過 timeout_secs 秒。"""
    updated = session.get("updated_at")
    if not updated:
        return False
    try:
        last = datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ")
        return (datetime.utcnow() - last).total_seconds() > timeout_secs
    except ValueError:
        return False


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
