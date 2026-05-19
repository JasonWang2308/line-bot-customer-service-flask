# LINE Bot Customer Service (Decision-Tree Edition)

一個跑在自己電腦上的 LINE 客服模擬器：手機外殼模擬 LINE 對話、視覺化選單樹編輯器、真人客服留言後台，三個畫面齊全。決策樹改完即時生效，不用重啟，不用 ngrok。

A local LINE customer-service simulator. Three pages: a LINE-style phone shell for the chat preview, a visual decision-tree editor, and a human-agent inbox. Edit the tree in the browser and the bot picks it up immediately — no restart, no ngrok needed.

> ⚠️ `menu.json` 與 `templates.json` 的內容是通用 SaaS 客服範例 (Account / Billing / Subscription / Other)。換成自己的業務內容即可使用。
> The decision tree and reply templates are generic SaaS customer-service placeholders.

---

## 三個入口 / The three entry points

| URL | 用途 / Purpose | 適合誰 / For |
|---|---|---|
| `http://localhost:5000/` | LINE 風格手機殼，模擬使用者跟客服 bot 對話 / LINE-style phone shell | dev / demo |
| `http://localhost:5000/editor` | 視覺化選單樹編輯器 / Visual decision-tree editor | admins |
| `http://localhost:5000/admin/messages` | 真人客服留言管理頁 / Human-agent inbox | support team |

無需 LINE Developers 帳號，無需 ngrok。

---

## 我怎麼做出這個 / How I built it

這個專案經過幾次重新設計，每次都因為前一版撞到牆才換做法。

This one went through several rewrites — each previous version hit a wall.

### 第 0 版：no-code（Dify / Make）

- 拖元件、串 webhook，幾分鐘就有個能回答的 LINE bot
- 撞牆點：條件分支稍微複雜（多層追問、回上一層、逾時重置）就難維護；對話狀態管理做不太出來；改流程都得回 SaaS 後台、不在 git 裡

Started with Dify + Make. Fast for "hello world", but conditional flow, state, and version control all hit walls fast.

### 第 1 版：RAG

- 把客服文件切 chunk、做 embedding、找相近段落回答
- 撞牆點：客服 Q&A 是「結構化」的—— 同樣 topic 配不同 action 答案完全不同，相似度比對不出這種邏輯；回答品質不穩定

Switched to RAG. Wrong fit for structured Q&A where intent dimensions matter as much as topic.

### 第 2 版：類專家系統（規則 + tag set）

- 每筆 Q&A 預先標 dimension tag，使用者輸入解析成 tag set，做集合交集找答案
- 撞牆點：每新增 Q 都要手動補 tag，admin 非工程師看不懂 JSON

A tag-based expert system. Better than RAG for structured Q&A, but tagging became a maintenance burden and admins couldn't read the JSON.

### 第 3 版（現在）：決策樹 + visual editor + no-code 後台

| 層 / Layer | 模組 / Module | 職責 / Responsibility |
|---|---|---|
| Data | `menu_engine.py` | 樹節點 load/save/lookup，與 Flask/LINE 解耦 |
| Data | `templates_engine.py` | 可重複使用的回覆「公版」CRUD |
| Data | `db.py` | SQLite（sessions / messages）|
| Service | `messages.py` | 留言查詢 + 統計（route 變薄殼）|
| Integration | `line_bot.py` | LINE webhook → menu_engine |
| Domain | `chatbot/handler.py` | 樹狀導航狀態機（web 模擬器用）|
| API | `app.py` | Flask routes，只負責 HTTP 殼 |
| UI | `templates/editor.html` + `static/editor/` | 視覺化編輯器（樹清單 + d3.js 樹狀圖 + 公版管理）|
| UI | `templates/index.html` + `static/viewer.js` | LINE 風格手機殼 |

關鍵設計 / Key design choices:

- `label` 只是顯示文字，admin 改名不影響程式；行為由 `action` 欄位決定（`collect_message` / `call_phone`）。`label` is display-only — admins rename freely without breaking code; behavior is gated by an explicit `action` field
- 新 action 三步走：`menu_engine.VALID_ACTIONS` 註冊 → `line_bot.ACTION_HANDLERS` 補 handler → 編輯器下拉自動透過 `/api/actions` 出現。Adding a new action is a 3-step contract across data / integration / UI
- 公版（templates）與選單分離：節點建立時可一鍵套用公版內容再微調。Reusable reply templates are stored separately so admins don't copy-paste
- 檔案存 JSON 而非 DB：menu 與 templates 是「設定」不是「資料」，git diff 可讀，admin 也能直接編輯

### 1. 研究階段 / Research

- 比較了 RAG、規則引擎、決策樹三條路；對結構化客服情境，**決策樹為符合限制的解答**
- 讀了 LINE Messaging API webhook / Quick Reply / Postback 的限制（13 顆 button、20 字 label）
- 學 d3.js 怎麼畫樹狀圖（樹狀預覽分頁）
- GCP Compute Engine、Docker、靜態網域、HTTPS 部署都是這個專案邊做邊補的
- SQL：用 SQLite（關聯式）做 sessions 與 messages 兩張表；對照之前試過 pickle / JSON file storage（NoSQL 風格），這次選 SQLite 是因為支援 transactional UPSERT 而且容器掛 volume 很簡單

### 2. 框架階段 / Scaffolding

從一個檔案塞所有東西的雛形，重構成「資料層 / 服務層 / 介接層 / API 殼 / UI」五段。每段有明確的依賴方向（UI → API → service → data，不可逆）。

Refactored from a single-file prototype into a 5-layer split with strict dependency direction.

### 3. AI 迭代階段 / AI-assisted iteration

- 樹狀資料結構、路徑導航狀態機、編輯器的拖拉與儲存流程，都是把資料形狀和介面定義講清楚後跟 AI 協作完成的
- 我畫流程圖、AI 補實作；改 bug 時 AI 幫忙找邊界條件（空樹、單一節點、超過 13 個子節點、label 超過 20 字）
- d3.js 樹狀圖視覺化完全靠 AI 寫，但事前定好「點節點要 emit 什麼事件、編輯器要怎麼接」這個 contract

學到的事：**先把「資料 → 行為」的對應講清楚，AI 才能寫出穩的程式**。

Lesson: nail down the data-to-behavior contract first, then AI can fill in the implementation reliably.

---

## 啟動：用 Docker / Quick start with Docker

需要先裝 Docker Desktop (Windows / Mac) 或 Docker Engine (Linux)。

```bash
docker compose up -d --build
# Open http://localhost:5000/
```

**日常操作 / Day-to-day:**

```bash
docker compose logs -f       # tail logs
docker compose stop          # pause (data preserved)
docker compose start         # resume
docker compose down          # remove container (data preserved on host)
docker compose up -d --build # rebuild after Python changes
```

不用 Docker 的話：

```bash
pip install -r requirements.txt
python app.py
```

---

## 體驗流程 / Demo flow

1. 進 <http://localhost:5000/> ，看到 LINE 風格手機殼裡只有一筆官方帳號「**Demo Customer Service**」
2. **點客服列** → 對話畫面從右滑入
3. **打字送出** → 主選單泡泡冒出來，內含 Account / Billing / Subscription / Other 四個分類
4. **點任一個按鈕** → 該泡泡按鈕變灰、自己的訊息冒出來、下方來一顆新的子選單泡泡
5. 走到底層：
   - 有設定文字的節點 → 顯示內容
   - `call_phone` 動作 → 顯示電話 + 撥打按鈕（`tel:` URI）
   - `collect_message` 動作 → 進留言模式，下一句話會存進 SQLite
6. 對話標頭：左上 ‹ 滑回聊天列表
7. 底部「+」按鈕模擬 LINE 的附件選單 — bot 會擋掉並提示要打字
8. 底部「重新開始聊天」清空對話、回到聊天列表

---

## 怎麼改對話內容 / How to edit content

到 <http://localhost:5000/editor>：

- **編輯分頁**：左邊樹狀清單，點任一節點 → 右邊改 label / description / text / action / phone，按「儲存」寫回 `menu.json`
- **樹狀圖預覽**：把整棵選單樹畫成圖（d3.js），拖曳平移、滾輪縮放，點節點跳回編輯
- **公版管理**：建立可重複使用的回覆內容，多個節點可套用同一份公版

存檔後切回 `/` 對話模擬器會自動拉新版。

The editor writes JSON files (`menu.json`, `templates.json`) directly — git diff stays readable.

---

## 留言管理 / Human-agent inbox

走 `collect_message` 節點留下的訊息會存進 `Chat History/session.db` (SQLite)。

到 <http://localhost:5000/admin/messages>：

- 用 **待處理 / 已處理 / 全部** 分頁過濾
- 用 **日期區間** 查詢（以 08:30 為日切，台北時區）
- **標記已處理** ↔ 取消標記
- **刪除留言**（兩段防誤刪）：先解鎖 🔒 → 🔓，再點 🗑️，最後 modal 確認

---

## 接上真正的 LINE Bot / Connect to real LINE

複製 `.env.example` 為 `.env`，填入 LINE Developers Console 拿到的兩個值：

```
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
```

重啟 docker，然後用 ngrok / Cloudflare Tunnel 把 `localhost:5000` 暴露到公網 HTTPS：

```bash
ngrok http 5000
```

把 ngrok 給的網址 + `/callback` 設到 LINE Developers Console 的 webhook URL 即可。LINE 真機與網頁模擬器的留言都會在同一份 SQLite。

---

## 專案結構 / Repo layout

```
.
├── Dockerfile / docker-compose.yml / .dockerignore
├── DOCKER.md / COMPLIANCE.md
│
├── app.py                     ← Flask routes
├── line_bot.py                ← LINE webhook (only when connected to real LINE)
├── menu_engine.py             ← tree data layer
├── templates_engine.py        ← reply-template data layer
├── messages.py                ← message service layer
├── messages_constants.py      ← shared strings & LINE limits
├── time_utils.py              ← TW timezone helpers
├── db.py                      ← SQLite
│
├── chatbot/                   ← decision-tree handler (web simulator)
│   ├── handler.py
│   ├── menu.json
│   └── templates.json
│
├── menu.json                  ← decision tree (editor writes back here)
├── templates.json             ← reusable reply templates
├── .env.example
├── requirements.txt
│
├── templates/
│   ├── index.html             ← phone shell (chat list + chat view)
│   ├── editor.html            ← visual tree editor
│   └── admin_messages.html    ← inbox
│
├── static/
│   ├── css/style.css
│   ├── js/chat.js             ← phone-shell interaction
│   ├── viewer.js              ← bot conversation logic
│   ├── menu-utils.js          ← tree helpers
│   ├── editor.css / editor/   ← editor assets (d3 tree viz, list, form)
│   └── img/rich-menu.jpg
│
└── Chat History/              ← runtime SQLite (auto-created)
```

---

## 常見問題 / FAQ

**Q: 啟動後瀏覽器空白 / 連不上**
A: `docker compose ps` 看容器是不是 `Up`。`Restarting` 的話跑 `docker compose logs -f`。最常見是 port 5000 被占用，把 `docker-compose.yml` 的 `"5000:5000"` 改成 `"5001:5000"`。

**Q: 編輯器存了但模擬器沒更新**
A: 切到 `/` 分頁時 `viewer.js` 會自動拉新 menu。如果一直在同一頁，按底部「重新開始聊天」或 Ctrl+F5。

**Q: 改了 HTML / CSS / JS 容器要重建嗎？**
A: 不用。Ctrl+F5 就拿到新版。只有改 Python 才需要 `docker compose up -d --build`。

**Q: SQLite `database disk image is malformed`**
A: 刪掉 `Chat History/session.db`，下次啟動會自動建空檔（舊留言會丟）。

---

## 用到的技術 / Tech stack

- **Backend**: Python 3.11 + Flask + gunicorn
- **DB**: SQLite
- **LINE**: line-bot-sdk-python v3
- **Frontend**: vanilla HTML/CSS/JS (no build step)
- **Tree viz**: D3.js v7 (CDN)
- **Container**: Docker + docker-compose

---

## License

MIT — see [LICENSE](LICENSE).
