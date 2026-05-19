# LINE Bot Customer Service (Flask)

LINE 機器人 + Web 介面的雙通道客服系統。使用者用自然語言問問題，後端先把詞彙正規化成「維度 ID」，再走決策樹追問釐清，最後用反向索引找到最佳 Q&A 回覆；無法回答時把對話轉成留言給真人客服處理，後台可以看待處理與已處理。

A LINE bot + web chat customer-service system. User input is normalised into dimension IDs, fed through a decision-tree clarifier, then matched against a small Q&A knowledge base via an inverted tag index. If no match, the conversation is logged as a ticket for human agents, viewable in a built-in admin page.

> ⚠️ 知識庫（`Knowledge/qa.json`、`dictionary.json`、`rules.json`）的內容是 placeholder，示範通用 SaaS 客服情境。請替換為自己的業務 Q&A 後再使用。
> The knowledge base files are placeholder content showing a generic SaaS customer-service example. Replace them with your own Q&A.

---

## 它在做什麼 / What it does

1. **輸入解析**：使用者打 `我想換方案` → 用 greedy longest-match 對到字典裡的同義詞（`subscription`、`change plan` …）→ 解析出維度 IDs（`C03`：Subscription, `A01`：How-to）
2. **決策樹追問**：如果還缺維度（例如沒指定 action），系統會自動丟出 quick-reply 按鈕讓使用者選
3. **規則比對**：用 rules.json 定義的條件（`{"C": ["C02", "C04"]}` 之類）動態決定要追問哪些維度
4. **反向索引匹配**：把所有已 resolved 的 IDs 做交集查 QA，找出唯一最相關的答案
5. **真人 fallback**：找不到、衝突、或使用者主動要求時，蒐集留言 → 寫到 `messages` 表 → 真人客服在 `/admin/messages` 處理
6. **雙通道**：LINE 通道走 SQLite session；Web 通道用記憶體 session 省 I/O，但結果一樣寫 DB

---

## 技術棧 / Tech stack

- **Flask** — HTTP framework
- **line-bot-sdk (v3)** — LINE messaging API
- **SQLite** — sessions / conversations / messages 三張表
- **純 Python 邏輯引擎** — 無 LLM、無 ML，全部是顯式規則（matcher.py）
- **GCP Compute Engine** + **靜態 IP / 域名** — production deploy

---

## 倉庫結構 / Repo layout

```
.
├── app.py                # Flask routes: /callback (LINE) /chat (web) /admin/messages
├── matcher.py            # 純邏輯：parse_input → compute_pending_dims → match QA
├── db.py                 # SQLite layer：sessions / conversations / messages
├── Knowledge/
│   ├── dictionary.json   # term → dimension ID（含同義詞）
│   ├── rules.json        # ask_order + 條件式追問規則
│   └── qa.json           # 終端答案，tags 指回 dimension IDs
├── requirements.txt
├── docs-architecture.md  # DB 三張表的職責 + 兩條寫入路徑
└── .env.example
```

---

## 我怎麼做出這個 / How I built it

這個專案的路徑比較曲折，因為我換了好幾次「怎麼做」。

This one took the most pivoting — I went through several different approaches before landing on the current one.

### 第 0 版：no-code / SaaS 起步

最早用 **Dify** + **Make**：拖元件、串 webhook，幾分鐘就有個能回答的 LINE bot。但很快撞牆——
- 答案邏輯一複雜（多條件、需要追問），no-code 工具的條件分支很難維護
- 對話狀態管理（逾時、回上一層）做不太出來
- 部署 / 監控 / 改 prompt 都得回 SaaS 後台，不在自己的 git 裡

I started with no-code: **Dify** + **Make** for the LINE webhook. Easy to get something working in minutes, but conditional logic and state management both hit a wall fast.

### 第 1 版：RAG + 規則引擎

想自己做就先試 **RAG**：把客服文件切 chunk、做 embedding、查最相近的段落回給使用者。問題：
- Q&A 是「結構化」的——同樣的 topic 配不同的 action 會有完全不同的答案，相似度比對抓不到這種邏輯
- 回答品質飄忽，不確定下一次同樣的問題會不會給同樣的答案

於是改成**類專家系統**：把 Q&A 預先標 tag，使用者問題解析成 tag set，做集合交集找答案。這個版本工作了，但每次新增 Q 都要手動補 tag，dictionary 也越來越亂。

Switched from RAG to a tag-based expert system. Each QA gets dimension tags, user input is parsed to a tag set, and the answer is whichever QA's tag set is a superset of the input. Cleaner than RAG for structured Q&A, but the tagging burden grew fast.

### 第 2 版（現在）：決策樹 + no-code 後台

最後的設計：

- 維度（C / T / A）用**單字母 prefix** 表示，從 ID 字串本身就能知道是哪個維度
- **`ask_order`** 列出系統會主動追問的順序；**`condition`** 用一個物件（`{"C": ["C02", "C04"]}`）表示「只有當 C 維度是 C02 或 C04 時才追問」——這讓追問邏輯變成資料而不是程式
- 沒被命中的維度自動丟出快速回覆按鈕讓使用者點
- 答案的 `tags` 用反向索引預先建好，查詢時是 O(tags) 而不是 O(QA)

這個版本最大的好處：**新增 Q&A 不用改 Python 程式碼**，只要動 `Knowledge/*.json`。我也順便做了個 `/admin/messages` 頁面讓真人客服在瀏覽器裡處理工單。

The final design encodes dimensions as ID prefixes (`C01` → category, `A01` → action), uses an `ask_order` + `condition` data structure to drive clarifying questions, and indexes QAs by tag for O(tags) lookup. Adding new Q&A means editing JSON only — no Python changes.

### 1. 研究階段 / Research

- 比較了 RAG、規則引擎、決策樹三條路；對小型結構化客服情境，**規則引擎勝**
- 讀了一些 chatbot 設計參考，理解 slot-filling / disambiguation 的概念
- 找到「反向索引」這個資料結構解掉了「QA 太多查不動」的擔憂（其實實際也沒幾筆，但結構正確）
- SQL：學了關聯式 SQLite（這個專案用），也試過 NoSQL（pickle / json file storage）—— 最後選 SQLite 因為它支援 transactional UPSERT 而且零部署成本
- 部署：GCP Compute Engine 起 VM、申請靜態 IP、Cloud DNS 接域名、HTTPS 用 Caddy，這些都是這個專案邊做邊學的

### 2. 框架階段 / Scaffolding

- 三檔分工：`app.py` 只處理 HTTP + LINE callback，`matcher.py` 純邏輯不碰 DB，`db.py` 只負責 SQLite。這個分層是後來才重構出來的，原本全部塞在 `app.py`
- DB 設計：`sessions`（活躍對話、結束就刪）、`conversations`（永久歸檔）、`messages`（真人客服工單）三張表，職責很清楚（細節在 [docs-architecture.md](docs-architecture.md)）
- LINE 用 SQLite 持久化 session（reconnect 後對話不丟）；Web 用記憶體 session 省 I/O，但結果都會寫 `conversations`

### 3. AI 迭代階段 / AI-assisted iteration

- 整套規則引擎的核心 ~150 行（`matcher.py` 的 `compute_pending_dims` / `viable_options` / `detect_conflict`）是和 AI 對話逐步打磨出來的
- 我畫好資料流（在 docs-architecture.md 有圖），AI 負責對應實作；改 bug 時 AI 也幫我加 test case
- 後台 HTML（`/admin/messages` 那頁的 Tailwind + filter tab）幾乎是 AI 一鍵生成的，我做的是定 spec：「待處理 / 已處理 / 全部三個 tab，日期切點 08:30」

學到的事：**先講清楚資料的形狀和流向，AI 才能寫出正確的程式**。我每次卡住，回頭看都是因為當下沒想清楚「這份資料是誰寫的、誰讀的、生命週期多久」。

Lesson: AI works much better once you've decided **the shape of the data and its lifecycle**. Every time I got stuck, it was because I hadn't pinned down who writes, who reads, and how long each piece of state lives.

---

## 跑起來 / How to run

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 設定 LINE 憑證
cp .env.example .env
# 編輯 .env，填入 LINE Channel Secret / Access Token

# 3. 跑起來
python app.py
# Flask runs on http://0.0.0.0:5000
```

需要把 `/callback` 設成 LINE Developers Console 的 Webhook URL（要 HTTPS — 開發時用 ngrok 或 Cloudflare Tunnel）。

Set the LINE Webhook URL to `https://your-domain/callback` (HTTPS required — use ngrok or Cloudflare Tunnel during development).

### Web chat

開瀏覽器到 `http://localhost:5000/` — 用同一份知識庫，但不需要 LINE 帳號就能測。

Open `http://localhost:5000/` in the browser for a simple web chat against the same knowledge base.

### Admin

`http://localhost:5000/admin/messages` — 看真人客服 inbox（沒做認證，production 請加上 reverse proxy + auth）。

The admin inbox at `/admin/messages` has no built-in auth — put it behind a reverse proxy with authentication for production.

---

## 後續可以做的事 / Next steps

- Admin 後台加認證
- 規則引擎支援更複雜的 condition（OR / NOT / 巢狀）
- Knowledge JSON 加 schema validation，避免新增資料時打錯結構
- 把 LINE callback 改成異步處理（目前同步回應在尖峰可能會卡）

---

## License

MIT — see [LICENSE](LICENSE).
