# Docker 啟動備忘

## 在新電腦初次設定

確保已安裝 Docker Desktop（Windows / Mac）或 Docker Engine（Linux）。

```bash
cd line-bot-simulator
docker compose up -d --build
```

第一次跑會花約 1–2 分鐘下載 python:3.11-slim、安裝 pip 套件。
跑完後 image 約 150MB，容器在 background 跑。

開啟瀏覽器：
- <http://localhost:5000/>                — LINE 風格手機模擬器
- <http://localhost:5000/editor>          — 選單編輯器
- <http://localhost:5000/admin/messages>  — 留言管理

## 日常使用

```bash
docker compose logs -f       # 看執行 log
docker compose stop          # 暫停（保留容器與資料）
docker compose start         # 啟動已存在的容器
docker compose down          # 停止並刪除容器（資料會留在 host 的 menu.json / Chat History/）
docker compose up -d --build # 修改 Python 程式後重建（HTML/CSS/JS 改動不必重建）
```

## 資料持久化

下面這些 host 端的檔案會被掛進 container；你在編輯器存檔、使用者留言、換 rich menu 圖，
全部會落地到 host：

- `menu.json` — 選單樹
- `templates.json` — 公版回覆
- `Chat History/session.db` — SQLite 留言
- `static/img/rich-menu.jpg` — Rich menu 圖

容器砍掉重建，這些都還在。

## 帶到另一台電腦

把整個 `line-bot-simulator/` 資料夾整包帶過去（USB / Git / 雲端硬碟）即可。
新電腦上同樣跑 `docker compose up -d --build` 就能起。

不想每次新電腦都 rebuild？可以在原電腦：

```bash
docker save line-bot-simulator:latest -o line-bot-simulator.tar
```

把 tar 檔帶到新電腦：

```bash
docker load -i line-bot-simulator.tar
docker compose up -d        # 不加 --build，直接用 image
```

## 接 LINE 真機

複製 `.env.example` 為 `.env` 並填入金鑰：

```
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
```

`docker compose up -d` 重新啟動，container 會把這兩個變數注入。
之後用 ngrok 把 `localhost:5000` 公開到 HTTPS，把 webhook 設定到
`https://你的網址/callback` 即可。
