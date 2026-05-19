"""
messages_constants — 跨子系統共用的文案與限制常數

定位:
    LINE bot 的固定回覆字串、使用者互動的導航按鈕標籤、以及 LINE 平台限制
    集中於此。讓:
      - line_bot.py 從這裡 import (Python 原生)
      - viewer.html 透過 frontend_constants() 經 Jinja 注入到 window.APP_CONSTANTS
        前端 viewer.js 直接讀，避免兩邊文案不同步。

修改流程:
    動文案 → 改本檔 → 重啟 Flask → LINE 與網頁 viewer 同步生效
    動 LINE 平台限制 (QUICK_REPLY_MAX 之類) → 只動本檔, line_bot 自動拿到
"""


# ── 導航按鈕 ─────────────────────────────────────
BACK_LABEL = "← 上一層"
HOME_LABEL = "回主選單"


# ── Bot 預設訊息 ────────────────────────────────
FALLBACK_MSG = "請透過下方選項按鈕進行操作哦!"
NON_TEXT_HINT = "請以文字描述您的問題，或點選下方選項。"
COLLECT_MSG_PROMPT = "請輸入您想留言的內容，我們將於上班時間由真人客服回覆您。"
MESSAGE_RECEIVED = "我們已收到您的問題，等上班時間會由真人客服為您回復，感謝您的配合！"
EMPTY_NODE_MSG = "(此項目尚未設定內容)"


# ── Session / LINE 平台限制 ──────────────────────
TIMEOUT_SECS = 90               # session 多久沒互動視為過期 (秒)
QUICK_REPLY_MAX = 13            # LINE Quick Reply 一次最多 13 顆按鈕
QUICK_REPLY_LABEL_MAX = 20      # 每顆按鈕 label 最多 20 字


def frontend_constants() -> dict:
    """前端需要的文案子集；透過 Jinja 注入 window.APP_CONSTANTS。"""
    return {
        "back_label":         BACK_LABEL,
        "home_label":         HOME_LABEL,
        "fallback_msg":       FALLBACK_MSG,
        "non_text_hint":      NON_TEXT_HINT,
        "empty_node_msg":     EMPTY_NODE_MSG,
        "collect_msg_prompt": COLLECT_MSG_PROMPT,
        "message_received":   MESSAGE_RECEIVED,
    }
