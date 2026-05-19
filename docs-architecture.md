# 資料庫在此專案中的角色

資料庫檔案：**SQLite** — [Chat History/session.db](Chat%20History/session.db)

所有 DB 操作集中於 [db.py](db.py)，[matcher.py](matcher.py) 不觸碰 DB（純邏輯），[app.py](app.py) 是唯一呼叫者。

---

## 三張 Table（[db.py:15-53](db.py#L15-L53)）

| Table | 用途 | 生命週期 |
|---|---|---|
| **sessions** | 儲存「進行中」對話狀態（state、resolved_ids、pending_dims、turn_count…），PK = user_id | 對話結束即 DELETE |
| **conversations** | 對話**結束後**的永久記錄（resolved / message_received） | 只增不刪 |
| **messages** | 真人客服留言池（user_id、display_name、content、handled） | 只增、狀態可更新 |

---

## 兩條來源的寫入路徑差異（關鍵）

### LINE 使用者 — 全走 DB

[app.py:82-127](app.py#L82-L127)

```
LINE /callback
  ├─ db.get_session(user_id)         ← 讀 sessions
  ├─ db.is_expired() → db.reset_session()  ← 逾時清 sessions
  ├─ matcher.process(text, session)  ← 純邏輯，不碰 DB
  ├─ 依結果：
  │    resolved / message_received → db.log_conversation() + db.reset_session()
  │    進行中                       → db.save_session()  (UPSERT)
  └─ message_received              → db.save_message()
```

### Web 使用者 — 記憶體 session + 只寫結果

[app.py:44-64, 224-270](app.py#L44-L64)

```
Web /chat
  ├─ _WEB_SESSION (dict in memory)   ← 不讀 sessions 表，省 I/O
  ├─ matcher.process(...)
  ├─ resolved / message_received → db.log_conversation()  ← 仍寫 conversations
  └─ message_received          → db.save_message()         ← 仍寫 messages
```

> 註：註解寫「單用戶，省去 SQLite I/O」→ Web 端 session 不持久化，只有對話**結果**落 DB。

---

## 管理後台（只讀 + 小更新）

[app.py:273-316](app.py#L273-L316)

- `GET /admin/messages` → `db.get_messages(start, end)` 以台灣時間 08:30 為批次切點查詢 messages
- `POST /admin/messages/<id>/handle` → `db.mark_handled()` 切換 handled 旗標

---

## 啟動時初始化

[app.py:736](app.py#L736) → `db.init_db()`：建三張表（IF NOT EXISTS）。

---

## 架構圖拓撲

```
┌──────────────┐        ┌──────────────┐
│ LINE User    │        │ Web User     │
└──────┬───────┘        └──────┬───────┘
       │ /callback              │ /chat
       ▼                        ▼
┌─────────────────────────────────────────┐
│              app.py (Flask)             │
│  ┌──────────────┐    ┌───────────────┐  │
│  │ LINE handler │    │ Web handler   │  │
│  │              │    │ _WEB_SESSION  │  │  ← in-memory
│  └──────┬───────┘    └───────┬───────┘  │
│         │ session R/W        │ 只寫結果 │
│         ▼                    ▼          │
│  ┌──────────────────────────────────┐   │
│  │ matcher.process() (pure, no DB)  │   │
│  └──────────────────────────────────┘   │
└─────────┬──────────────┬──────────┬─────┘
          │              │          │
          ▼              ▼          ▼
      ┌────────┐   ┌──────────────┐ ┌─────────┐
      │sessions│   │conversations │ │messages │
      │(live)  │   │(archive)     │ │(客服池) │
      └────────┘   └──────────────┘ └─────────┘
                                         ▲
                                         │ 讀 / 標記
                                   /admin/messages
                                   (客服後台)
```

---

## 3 條重要資料流（可在圖上標色區分）

1. 🟦 **活躍 session 流**（只 LINE 有）：sessions ↔ app.py，每次對話讀→判→寫/刪
2. 🟩 **歷史歸檔流**（LINE + Web 共用）：對話結束 → conversations（INSERT only）
3. 🟧 **客服留言流**：使用者留言 → messages → 客服後台讀/標記已處理
