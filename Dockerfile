# ─────────────────────────────────────────────────────────────
# LINE Bot 本地模擬器
# 基於 BOT 專案，外加 LINE 風格手機殼 + 聊天列表 landing
# python:3.11-slim → 最終 image 約 150MB
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

# 時區設為台北，讓 admin/messages 留言時間顯示正確
ENV TZ=Asia/Taipei \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 先複製 requirements.txt 利用 Docker layer cache（之後改程式不用重裝套件）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製整個專案
COPY . .

# 確保 Chat History 資料夾存在（給 SQLite 用）
RUN mkdir -p "Chat History"

EXPOSE 5000

# 用 gunicorn 跑 production server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "app:app"]
