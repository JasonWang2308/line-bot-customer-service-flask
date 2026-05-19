"""
db — SQLite 持久化（資料層）

定位:
    集中所有 SQLite 讀寫，提供 LINE Bot 的會話狀態與真人客服留言。
    本模組不耦合 Flask / LINE / menu_engine，可獨立測試。

資料表:
    sessions  — 每位 LINE 使用者目前在決策樹的路徑與狀態
                user_id      TEXT PK
                current_path TEXT (JSON list[int])
                state        TEXT ('idle' | 'awaiting_message')
                created_at   TEXT (UTC ISO8601)
                updated_at   TEXT (UTC ISO8601)
    messages  — 真人客服留言（與舊程式 schema 完全相容）
                id           INTEGER PK
                user_id      TEXT
                display_name TEXT
                content      TEXT
                handled      INTEGER (0|1)
                created_at   TEXT (UTC ISO8601)

包含單元 (units):
    init_db                         建表（若不存在）
    get_session / save_session      session 讀 / 寫（upsert）
    reset_session                   清除指定使用者 session
    save_message / get_messages     留言寫 / 查（支援日期區間與已處理狀態過濾）
    mark_handled                    標記留言處理狀態
    is_expired                      判斷 session 是否逾時（給逾時重置用）
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_DIR = Path(__file__).parent / "Chat History"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = str(DB_DIR / "session.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id      TEXT PRIMARY KEY,
                current_path TEXT    DEFAULT '[]',
                state        TEXT    DEFAULT 'idle',
                created_at   TEXT,
                updated_at   TEXT
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


# ── Session ───────────────────────────────────────────────

def _default_session(user_id: str) -> dict:
    return {
        "user_id":      user_id,
        "current_path": [],
        "state":        "idle",
        "created_at":   None,
        "updated_at":   None,
    }


def _decode_path(raw: str) -> list:
    """current_path 欄位解碼；任何錯誤一律回 []，不讓壞資料弄壞 caller。"""
    try:
        path = json.loads(raw or "[]")
        return path if isinstance(path, list) else []
    except (TypeError, ValueError):
        return []


def get_session(user_id: str) -> dict:
    """取得 session；不存在則回傳預設值（不寫入 DB）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ?", (user_id,)
        ).fetchone()

    if row is None:
        return _default_session(user_id)

    return {
        "user_id":      row["user_id"],
        "current_path": _decode_path(row["current_path"]),
        "state":        row["state"] or "idle",
        "created_at":   row["created_at"],
        "updated_at":   row["updated_at"],
    }


def save_session(session: dict):
    """新增或更新 session。"""
    now = _now()
    created = session.get("created_at") or now
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO sessions (user_id, current_path, state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                current_path = excluded.current_path,
                state        = excluded.state,
                updated_at   = excluded.updated_at
        """, (
            session["user_id"],
            json.dumps(session.get("current_path", []), ensure_ascii=False),
            session.get("state", "idle"),
            created,
            now,
        ))
        conn.commit()


def reset_session(user_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()


# ── 留言 ──────────────────────────────────────────────────

def save_message(user_id: str, display_name: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, display_name, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, display_name, content, _now()),
        )
        conn.commit()


def get_messages(handled: int | None = None,
                 start: str | None = None,
                 end: str | None = None) -> list[dict]:
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
        conn.execute(
            "UPDATE messages SET handled = ? WHERE id = ?",
            (handled, msg_id),
        )
        conn.commit()


def delete_message(msg_id: int) -> bool:
    """永久刪除一則留言。回傳 True 代表確實有刪到一筆。"""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
        conn.commit()
        return cur.rowcount > 0


# ── 工具 ──────────────────────────────────────────────────

def is_expired(session: dict, timeout_secs: int) -> bool:
    """session 的最後更新時間已超過 timeout_secs 秒回 True。"""
    updated = session.get("updated_at")
    if not updated:
        return False
    try:
        last = datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ")
        return (datetime.utcnow() - last).total_seconds() > timeout_secs
    except (TypeError, ValueError):
        return False


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
