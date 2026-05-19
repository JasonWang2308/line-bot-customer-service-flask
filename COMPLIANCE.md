# 合規與品質保證 — 工程留存文件

**文件版本**：1.0
**建立日期**：2026-05-08
**對應產品版本**：line-bot-simulator @ 桌機本機原型
**作者**：開發團隊
**狀態**：📌 **內部留存記錄（Internal Record）— 非合規聲明，非審驗結論**

---

## 1. 文件目的

本文件是 LINE Bot 客服模擬器這個專案在「**原型階段**」的工程留存記錄。

**它不是什麼**：
- 不是任何標準（ISO 9001 / ISO 27001 / GDPR / 個資法）的合規聲明
- 不是審驗報告或外部認證
- 不是法律意見書

**它是什麼**：
- 一份開發團隊對現況的誠實技術紀錄
- 為「將來若商業化、若需走 QMS / ISMS / 個資保護法規」時，預先保留 baseline
- 提前盤點目前實作 vs. 未來合規要求之間的落差，避免日後翻找
- 一份 due diligence record，證明工程端在原型階段就有思考過這些議題

依照組織內部慣例，此文件應與專案原始碼一同保留，於版本控制系統中追蹤變更歷程。

---

## 2. 目前狀態聲明

> **本系統目前為內部原型，無外部銷售、無對外提供服務。**
> 因此**不適用** QMS（ISO 9001）品質管理系統規範，**不適用** ISMS（ISO 27001）資訊安全管理系統規範，**不適用** 個人資料保護法（個資法）下「個人資料檔案安全維護計畫」之強制要求。
>
> 若未來組織決定將本系統商業化、對外銷售或對外提供服務，**第 8 節（商業化前需補強事項）**所列項目應在上線前完成。

---

## 3. 系統概述

| 項目 | 內容 |
|---|---|
| 系統名稱 | LINE Bot 本地模擬器（SaaS Customer Bot — Demo） |
| 預期用途 | 客服 chatbot 流程設計、demo、內部驗收 |
| 部署環境 | 開發人員本機（Windows / Docker） |
| 使用者類型 | （a）模擬使用者：本機瀏覽器操作者 (b)管理員：本機編輯選單樹、查看留言 |
| 對外連線 | 預設無；若啟用 LINE 模式則透過 HTTPS webhook 與 LINE 平台通訊 |
| 預期使用者人數 | 個位數內部人員 |
| 服務水準 | 無 SLA |

---

## 4. 架構與資料流

### 4.1 元件構成

```
[使用者瀏覽器 (本機)]
         │ HTTP (localhost:5000)
         ▼
[Flask App (gunicorn, Docker container)]
   ├── /          → templates/index.html（手機殼模擬器）
   ├── /editor    → templates/editor.html（選單編輯器）
   ├── /admin/messages → templates/admin_messages.html（留言管理）
   ├── /api/menu  ↔ menu.json（檔案系統）
   ├── /api/messages   ↔ db.py
   ├── /admin/messages/<id>[/handle]  ↔ db.py
   └── /callback  → LINE webhook（僅 .env 有金鑰時註冊）
         │
         ▼
[資料層]
   ├── menu.json        ：選單樹（JSON 檔）
   ├── templates.json   ：公版回覆（JSON 檔）
   └── Chat History/session.db ：SQLite 資料庫（session + messages 兩張表）
```

### 4.2 資料流動

1. **本機模擬模式**：瀏覽器 → Flask → 檔案/SQLite → Flask → 瀏覽器（資料不離開本機）
2. **LINE 真機模式**（需手動啟用）：LINE 用戶 → LINE 平台 → 公網 HTTPS → ngrok → 本機 Flask → 同樣資料層
3. 留言（collect_message 流程）：使用者文字 → SQLite messages 表（user_id、display_name、content、created_at、handled 五欄）
4. 管理員操作：標記已處理、刪除留言（含前端二段防誤刪 UI）

### 4.3 對外資料邊界

- 預設模式：所有資料留在本機 docker container + host volume
- LINE 模式：webhook 收到的訊息會走 LINE 平台中介，受 LINE Corporation 隱私政策約束

---

## 5. 資產清單與資料分類

| 資產 | 類型 | 敏感度 | 儲存位置 | 加密 |
|---|---|---|---|---|
| `menu.json` | 流程設定 | 低（業務邏輯，非機密） | host 檔案系統 | 否 |
| `templates.json` | 回覆範本 | 低 | host 檔案系統 | 否 |
| `Chat History/session.db` (sessions 表) | 使用者對話狀態 | 中（含 user_id） | host 檔案系統 | 否 |
| `Chat History/session.db` (messages 表) | 使用者留言內容 | **中–高（可能含個資）** | host 檔案系統 | 否 |
| `.env` | LINE 金鑰 | **高（憑證）** | host 檔案系統 | 否（不入 image） |
| `static/img/rich-menu.jpg` | UI 圖片 | 低 | host 檔案系統 | 否 |
| Source code | 程式碼 | 低（無秘密硬編碼） | git / host | 否 |

### 5.1 個人資料盤點（依個資法分類）

留言 `content` 欄位**可能**含個人資料，因使用者在自然語言留言中可能寫入：
- 姓名、聯絡電話、Email
- 病史、健檢結果（敏感個人資料）
- 身分證字號、出生年月日

目前**無**自動偵測或遮罩機制；管理員肉眼看到什麼就是什麼。

`user_id` 在 LINE 模式下是 LINE 平台給的 hashed UID（非個人識別字串本身），網頁模擬模式則是固定字串 `web-simulator-user`。

---

## 6. 第三方相依

### 6.1 軟體依賴（`requirements.txt`）

| 套件 | 版本 | 授權 | 用途 |
|---|---|---|---|
| Flask | ≥3.0 | BSD-3 | Web 框架 |
| line-bot-sdk | ≥3.0 | Apache-2.0 | LINE Messaging API SDK |
| python-dotenv | ≥1.0 | BSD-3 | 環境變數載入 |
| gunicorn | ≥21.0 | MIT | Production WSGI server |

依賴未做 supply chain 鎖版本（沒有 `requirements.lock`）。

### 6.2 容器基礎映像

- `python:3.11-slim` — Python Software Foundation 維護的官方映像
- 未做映像簽章驗證
- 未掃描 CVE（建議商業化前接上 Trivy / Snyk）

### 6.3 前端 CDN

- D3.js v7（編輯器樹狀圖預覽）—— 直接從 `d3js.org` CDN 載入
- 商業化時應改為自託管以降低供應鏈攻擊面

### 6.4 外部服務

- LINE Messaging API（僅 LINE 模式）
- ngrok（僅開發測試用）

---

## 7. 已實作的控制

下列項目雖非為合規而做，但客觀上已具備類似 ISMS 控制的雛形：

| 主題 | 已做 |
|---|---|
| **存取分層** | 模擬器使用者 ≠ 管理員（不同 URL，但無認證機制） |
| **二段確認** | 留言刪除採「鎖定 → 解鎖 → 二重確認 modal」防誤刪 |
| **輸入驗證** | menu.json 寫入時驗證 action 欄位合法性（`menu_engine._validate_actions`） |
| **路由白名單** | 對外 API 僅開放固定 endpoint，不接受任意 SQL/檔案路徑 |
| **金鑰外置** | LINE 金鑰透過 `.env` 注入，`.dockerignore` 排除進 image |
| **日誌** | Flask 預設 access log（stdout）；gunicorn 同 |
| **時區一致性** | 後端與顯示層皆以 UTC 儲存、台灣時區顯示 |
| **資料持久化** | menu/templates/SQLite 透過 docker volume 對應 host，避免容器消失帶走資料 |
| **基本 XSS 防護** | viewer.js 使用 `textContent`／DOM API 拼接、非 `innerHTML`；URL 渲染用程序拆解非 regex 替換 |
| **Webhook 簽章驗證** | LINE 模式下使用 `WebhookHandler` 內建 `InvalidSignatureError` 檢查 |

---

## 8. 商業化前需補強事項

下表是若決定對外銷售或對外提供服務時，**必須**或**強烈建議**補上的項目。
參考 ISO 27001:2022 Annex A 控制條款編號（A.x.y）。

### 8.1 高優先（無此項目無法上線）

| 編號 | 對應 ISO 27001 | 項目 | 現況 | 商業化前 |
|---|---|---|---|---|
| C-01 | A.5.15, A.8.3 | **管理頁面身分認證** | `/editor` 與 `/admin/messages` 完全無認證，任何人連到 IP 都能修改選單、看留言、刪資料 | 需加入帳號密碼 + Session / Token / SSO 機制；多人時要 RBAC |
| C-02 | A.8.24 | **傳輸加密 (TLS)** | 本機 HTTP；LINE 模式靠 ngrok 提供 HTTPS | Production 部署需自簽或正式憑證（Let's Encrypt / 公司 CA），強制 HTTPS |
| C-03 | A.8.11 | **資料隱碼／靜態加密** | SQLite 為明文，包含可能的個資留言 | 評估 SQLCipher 或將 SQLite 換成 PostgreSQL + at-rest encryption |
| C-04 | A.5.34 | **個資告知與同意** | 使用者送出留言前無任何告知 | 需於 `collect_message` 進入時顯示告知條款 + 同意紀錄 |
| C-05 | A.5.33, A.8.10 | **個資保留期限／刪除** | 留言永久保留（除非管理員手動刪） | 需訂保留政策（例：6 個月）+ 自動排程刪除 |
| C-06 | A.8.15 | **存取與變更稽核紀錄 (Audit Log)** | 僅 access log（誰存取過哪個 URL），無「誰刪了誰的留言」 | 需 audit trail：誰於何時對哪筆留言做了什麼操作 |

### 8.2 中優先

| 編號 | 對應 ISO 27001 | 項目 | 現況 | 商業化前 |
|---|---|---|---|---|
| C-07 | A.8.8 | 漏洞管理 | 無 | 接上 Trivy/Snyk/Dependabot 自動掃描依賴與映像 |
| C-08 | A.8.16 | 監控告警 | 無 | 接 Sentry / CloudWatch / Datadog 等 |
| C-09 | A.8.13 | 備份 | 無自動備份 | SQLite 定期 dump + 離站備份 |
| C-10 | A.5.30 | 業務持續 | 單機部署、無 HA | 評估容器編排（Kubernetes / ECS）多副本 |
| C-11 | A.8.32 | 變更管理 | 無 PR review 強制 | Git workflow + Code Review + CI 必過 |
| C-12 | A.5.7 | 威脅情資 | 無 | 訂閱 LINE Platform Security advisories |
| C-13 | A.5.24, A.5.26 | 資安事件處理流程 | 無 | 訂事件分類、聯絡窗口、SLA |

### 8.3 低優先（建議性）

| 編號 | 對應 ISO 27001 | 項目 | 商業化前建議 |
|---|---|---|---|
| C-14 | A.5.23 | 雲端服務使用評估 | 若部署到雲端需做雲端安全評估 |
| C-15 | A.5.19, A.5.22 | 供應商管理 | 對 LINE Corp、雲端供應商簽訂 DPA |
| C-16 | A.8.28 | 安全編碼準則 | 訂程式碼風格、Linter、SAST 工具 |
| C-17 | A.6.3 | 員工資安意識訓練 | 開發者上線前訓練 |

---

## 9. 對應 QMS（ISO 9001）的補強

| 條款 | 現況 | 商業化前 |
|---|---|---|
| 7.1.5 監控與量測資源 | 無正式測試框架 | 加入 pytest + 覆蓋率追蹤 |
| 7.5 文件化資訊 | 有 README / DOCKER / COMPLIANCE | 加入 SRS / SDD / Test Plan / Release Notes |
| 8.3 設計開發 | 無正式 design review | 採 Design Review 文件化 |
| 8.5.1 生產與服務提供管控 | 無 SOP | 訂部署 SOP、操作手冊 |
| 8.7 不符合輸出之管控 | 無 bug tracking 流程 | 接 GitHub Issues / Jira + 處理流程 |
| 9.1.2 顧客滿意度 | 無 | 收集模擬器使用回饋 |
| 9.2 內部稽核 | 無 | 定期內稽 |
| 10.2 不符合與矯正措施 | 無 CAPA 流程 | 訂 CAPA SOP |

---

## 10. 風險登錄（截至文件日）

| 風險 ID | 描述 | 影響 | 可能性 | 現有控制 | 殘餘風險 |
|---|---|---|---|---|---|
| R-01 | 管理介面無認證 → 任何能連到本機的人可改選單/讀留言/刪資料 | 高 | 低（僅本機） | 僅 listen 127.0.0.1（debug mode） | **中**（若改 0.0.0.0 暴露則高）|
| R-02 | 留言可能含個資、明文儲存 | 高 | 中 | 無 | 高 |
| R-03 | SQLite 易受網路檔案系統相容性影響（lock 不穩） | 中 | 中 | 文件中已說明限制 | 中 |
| R-04 | 第三方套件 CVE | 中 | 中 | 無 | 中 |
| R-05 | LINE 金鑰外洩 | 高 | 低 | .env 排除進 image / git | 低 |
| R-06 | 容器映像供應鏈攻擊 | 中 | 低 | 用官方 python:3.11-slim | 中 |

---

## 11. 變更歷程

| 日期 | 版本 | 變更摘要 |
|---|---|---|
| 2026-05-08 | 1.0 | 初版建立。對應 commit hash：（請於入版控時補上）|

---

## 12. 結論與建議

1. **本系統目前為原型**，無對外提供服務，**不適用** QMS / ISMS 強制要求。
2. 本文件作為**工程留存記錄**，證明開發階段已對未來合規議題有所盤點。
3. 若未來公司決定**商業化**或**對外提供服務**，本文件第 8 節列出**最少**需補強的 17 項；建議優先處理 **C-01 ~ C-06** 六項高優先項目。
4. 本文件應與專案 source code 一同進入版本控制，並於每次重大變更（如新增 API、改動資料結構、改變部署方式）時更新。
5. 真正進入商業階段後，本文件應移交資安／品保部門評估，並接續做：差距分析（Gap Analysis）→ 風險評估（Risk Assessment）→ 控制實作（Treatment）→ 內外部稽核。

---

## 附錄 A：對應法規／標準清單

| 標準/法規 | 全名 | 適用情境 |
|---|---|---|
| ISO 9001:2015 | 品質管理系統 | 對外銷售/服務之系統 |
| ISO 27001:2022 | 資訊安全管理系統 | 處理個資或客戶資料之系統 |
| ISO 27701 | 隱私資訊管理系統（PIMS）擴充 | 大量處理個資時建議 |
| 個資法 | 個人資料保護法 | 處理我國公民個資 |
| 個資法施行細則 | — | 同上 |
| 醫療機構電子病歷製作及管理辦法 | — | 若涉醫療資料 |
| GDPR | 歐盟一般資料保護規範 | 若服務歐盟用戶 |
| OWASP Top 10 | — | Web 應用程式安全參考 |
| OWASP ASVS | Application Security Verification Standard | 上線前 web 安全自評 |

---

## 附錄 B：本文件作者承諾

本文件之內容係依專案 2026-05-08 當下版本之原始碼與架構撰寫，反映**該時點**之實作真實狀態。
作者承諾：

- 不誇大已實作之控制
- 不隱瞞已知之風險與不足
- 不主張本系統「合規」於任何標準

本文件僅為內部留存，不對外發布。
