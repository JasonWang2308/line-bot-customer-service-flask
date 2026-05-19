"""
line_bot — LINE Messaging API 整合（介接層）

定位:
    LINE webhook 與 menu_engine 的整合點。
    不直接讀寫 menu.json（透過 menu_engine）；不直接讀寫 SQLite（透過 db）。

包含單元 (units):
    setup                  把 /callback 路由與 webhook handler 註冊到 Flask app
    handle_text            處理使用者輸入
    _enter_node            進入節點：先看 action 再決定是否走預設渲染
    _render_node           依節點類型組 LINE 訊息
    _resolve_display_name  從 LINE Profile API 取顯示名稱

    ACTION_HANDLERS 註冊表 — menu 節點的 action 對應到 handler
        新增 action 流程:
          1. menu_engine.VALID_ACTIONS 登記
          2. 這裡寫一個 handler 並加進 ACTION_HANDLERS
          3. 編輯器下拉自動透過 /api/actions 出現新選項

互動模型 (handle_text 比對優先序):
    1. 留言收集中 (state==awaiting_message) → 視為留言內容存檔，回主選單
    2. 上一層 / 回主選單 → 路徑導航
    3. 整棵樹 label 完全比對 (與 viewer.js 行為一致)
    4. 都不符 → 提示訊息 + 重新顯示目前節點 Quick Reply

進入節點 (_enter_node):
    若 node.action 有值且註冊在 ACTION_HANDLERS → 跑 handler
    否則 → 走預設渲染

非文字輸入 (image/sticker/video/audio):
    回提示訊息 + 重新顯示目前節點 Quick Reply（不需使用者再輸入文字）
"""

import os
import re
from pathlib import Path

from flask import abort, request

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessageAction,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
    URIAction,
)
from linebot.v3.webhooks import (
    AudioMessageContent,
    ImageMessageContent,
    MessageEvent,
    StickerMessageContent,
    TextMessageContent,
    VideoMessageContent,
)

import db
from menu_engine import find_path_by_label, get_node, load_menu, node_kind
from messages_constants import (
    BACK_LABEL,
    COLLECT_MSG_PROMPT,
    EMPTY_NODE_MSG,
    FALLBACK_MSG,
    HOME_LABEL,
    MESSAGE_RECEIVED,
    NON_TEXT_HINT,
    QUICK_REPLY_LABEL_MAX,
    QUICK_REPLY_MAX,
    TIMEOUT_SECS,
)


def setup(app, menu_file: Path) -> bool:
    """在 Flask app 上註冊 /callback。缺 LINE 環境變數時回 False。"""
    secret = os.environ.get("LINE_CHANNEL_SECRET")
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not secret or not token:
        print("[line_bot] LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN 未設定；"
              "/callback 不會註冊（僅 web 介面可用）。")
        return False

    configuration = Configuration(access_token=token)
    handler = WebhookHandler(secret)

    @app.route("/callback", methods=["POST"])
    def callback():
        signature = request.headers.get("X-Line-Signature", "")
        body = request.get_data(as_text=True)
        try:
            handler.handle(body, signature)
        except InvalidSignatureError:
            abort(400)
        return "OK"

    @handler.add(MessageEvent, message=TextMessageContent)
    def on_text(event):
        text = (event.message.text or "").strip()
        user_id = event.source.user_id
        menu = load_menu(menu_file)
        session = db.get_session(user_id)

        if session["state"] == "awaiting_message" and db.is_expired(session, TIMEOUT_SECS):
            db.reset_session(user_id)
            session = db.get_session(user_id)

        messages = handle_text(text, session, menu, user_id, configuration)
        db.save_session(session)

        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=messages)
            )

    def reply_non_text(event):
        """非文字訊息（image/sticker/video/audio）統一處理：提示 + 顯示當前節點選項"""
        user_id = event.source.user_id
        session = db.get_session(user_id)

        # 留言收集中 → 提示要打字輸入留言內容（保持留言模式）
        if session["state"] == "awaiting_message":
            messages = [TextMessage(text=COLLECT_MSG_PROMPT)]
        else:
            menu = load_menu(menu_file)
            current_path = session.get("current_path", []) or []
            if get_node(menu, current_path) is None:
                current_path = []
                session["current_path"] = []
                db.save_session(session)
            messages = [TextMessage(text=NON_TEXT_HINT)] + _render_node(current_path, menu)

        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=messages)
            )

    @handler.add(MessageEvent, message=ImageMessageContent)
    def on_image(event):
        reply_non_text(event)

    @handler.add(MessageEvent, message=StickerMessageContent)
    def on_sticker(event):
        reply_non_text(event)

    @handler.add(MessageEvent, message=VideoMessageContent)
    def on_video(event):
        reply_non_text(event)

    @handler.add(MessageEvent, message=AudioMessageContent)
    def on_audio(event):
        reply_non_text(event)

    return True


def handle_text(text: str, session: dict, menu: dict, user_id: str, configuration) -> list:
    """處理使用者文字並回傳 LINE 訊息列表；會 in-place 修改 session。"""

    # 1) 留言收集中：把使用者輸入存為留言，然後回主選單
    if session["state"] == "awaiting_message":
        display_name = _resolve_display_name(user_id, configuration)
        db.save_message(user_id, display_name, text)
        session["state"] = "idle"
        session["current_path"] = []
        return [TextMessage(text=MESSAGE_RECEIVED)] + _render_node([], menu)

    # 確保 current_path 仍在 menu 結構內
    current_path = session.get("current_path", []) or []
    if get_node(menu, current_path) is None:
        current_path = []
    session["current_path"] = current_path

    # 2) 導航 label
    if text in (BACK_LABEL, "上一層"):
        new_path = current_path[:-1] if current_path else []
        return _enter_node(new_path, menu, session)

    if text == HOME_LABEL:
        return _enter_node([], menu, session)

    # 3) 全域 label 比對
    found = find_path_by_label(menu, text)
    if found is not None:
        return _enter_node(found, menu, session)

    # 4) 都不符 → 提示 + 重新顯示當前節點
    msgs = [TextMessage(text=FALLBACK_MSG)]
    msgs.extend(_render_node(current_path, menu))
    return msgs


def _enter_node(path: list, menu: dict, session: dict) -> list:
    node = get_node(menu, path)
    if node is None:
        path = []
        node = menu

    action = node.get("action")
    if action and action in ACTION_HANDLERS:
        return ACTION_HANDLERS[action](path, menu, session, node)

    session["state"] = "idle"
    session["current_path"] = path
    return _render_node(path, menu)


def _render_node(path: list, menu: dict) -> list:
    node = get_node(menu, path)
    if node is None:
        node = menu
        path = []

    kind = node_kind(node)
    has_parent = len(path) > 0

    nav_items = []
    if has_parent:
        nav_items.append(QuickReplyItem(action=MessageAction(label=BACK_LABEL[:QUICK_REPLY_LABEL_MAX], text=BACK_LABEL)))
        nav_items.append(QuickReplyItem(action=MessageAction(label=HOME_LABEL[:QUICK_REPLY_LABEL_MAX], text=HOME_LABEL)))

    if kind == "branch":
        body_lines = [node.get("label", "")]
        if node.get("description"):
            body_lines.append("")
            body_lines.append(node["description"])

        items = []
        for child in node["children"]:
            label = child.get("label", "")
            items.append(QuickReplyItem(
                action=MessageAction(label=label[:QUICK_REPLY_LABEL_MAX], text=label)
            ))
        items.extend(nav_items)
        items = items[:QUICK_REPLY_MAX]
        return [TextMessage(text="\n".join(body_lines), quick_reply=QuickReply(items=items))]

    if kind == "leaf":
        body = node.get("text", node.get("label", ""))
        if nav_items:
            return [TextMessage(text=body, quick_reply=QuickReply(items=nav_items))]
        return [TextMessage(text=body)]

    # empty
    if nav_items:
        return [TextMessage(text=EMPTY_NODE_MSG, quick_reply=QuickReply(items=nav_items))]
    return [TextMessage(text=EMPTY_NODE_MSG)]


# ── Action handlers ───────────────────────────────────────

def _action_collect_message(path: list, menu: dict, session: dict, node: dict) -> list:
    """進入此節點 → 提示輸入留言；下一則訊息會由 handle_text 開頭的分支處理"""
    session["state"] = "awaiting_message"
    session["current_path"] = path
    return [TextMessage(text=COLLECT_MSG_PROMPT)]


def _action_call_phone(path: list, menu: dict, session: dict, node: dict) -> list:
    """進入此節點 → 顯示電話 + Quick Reply 撥打按鈕 (URIAction tel:)"""
    phone_raw = (node.get("phone") or "").strip()
    # tel: URI 只保留數字與 + (常見 dialer 都接受)
    phone_dial = re.sub(r"[^\d+]", "", phone_raw)

    body = (
        "真人客服專線\n"
        f"{phone_raw}\n\n"
        "手機按下方「撥打電話」可直接撥號；桌機請手動撥打。"
    )

    items = [
        QuickReplyItem(action=URIAction(
            label="撥打電話"[:QUICK_REPLY_LABEL_MAX],
            uri=f"tel:{phone_dial}",
        ))
    ]
    if path:
        items.append(QuickReplyItem(action=MessageAction(
            label=BACK_LABEL[:QUICK_REPLY_LABEL_MAX], text=BACK_LABEL,
        )))
        items.append(QuickReplyItem(action=MessageAction(
            label=HOME_LABEL[:QUICK_REPLY_LABEL_MAX], text=HOME_LABEL,
        )))

    session["state"] = "idle"
    session["current_path"] = path
    return [TextMessage(text=body, quick_reply=QuickReply(items=items))]


ACTION_HANDLERS = {
    "collect_message": _action_collect_message,
    "call_phone":      _action_call_phone,
}


def _resolve_display_name(user_id: str, configuration) -> str:
    try:
        with ApiClient(configuration) as api_client:
            profile = MessagingApi(api_client).get_profile(user_id)
        return profile.display_name
    except Exception:
        return user_id
