"""
ChatbotHandler — 樹狀選單版（與 BOT 專案 menu.json 同格式）
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional


BACK_LABEL = "← 上一層"
HOME_LABEL = "回主選單"

FALLBACK_MSG = "請透過下方選項按鈕進行操作哦!"
COLLECT_MSG_PROMPT = "請輸入您想留言的內容，我們將於上班時間由真人客服回覆您。"
MESSAGE_RECEIVED = "我們已收到您的問題，等上班時間會由真人客服為您回復，感謝您的配合！"
EMPTY_NODE_MSG = "(此項目尚未設定內容)"
WELCOME_MSG_PREFIX = "您好，歡迎使用「{title}」"

QUICK_REPLY_MAX = 13


def _get_node(data: dict, path):
    node = data
    for idx in path:
        children = node.get("children")
        if not isinstance(children, list) or not (0 <= idx < len(children)):
            return None
        node = children[idx]
    return node


def _find_path_by_label(data: dict, label: str):
    target = (label or "").strip()
    if not target:
        return None

    def search(node, path):
        if node.get("label") == target:
            return path
        for i, child in enumerate(node.get("children") or []):
            r = search(child, path + [i])
            if r is not None:
                return r
        return None

    return search(data, [])


def _node_kind(node: dict) -> str:
    children = node.get("children")
    if isinstance(children, list) and len(children) > 0:
        return "branch"
    if "text" in node:
        return "leaf"
    return "empty"


class ChatbotHandler:

    TIMEOUT_SECS = 90

    def __init__(self, menu_path: Optional[str] = None) -> None:
        if menu_path is None:
            menu_path = os.path.join(os.path.dirname(__file__), "menu.json")
        self.menu_path = menu_path
        self._sessions: dict = {}
        self._load_menu()

    def _load_menu(self) -> None:
        with open(self.menu_path, "r", encoding="utf-8") as fh:
            self.menu = json.load(fh)

    def reload(self) -> None:
        self._load_menu()

    @property
    def title(self) -> str:
        return self.menu.get("label", "客服助理")

    def _session(self, user_id: str) -> dict:
        s = self._sessions.get(user_id)
        if s is None:
            s = {"current_path": [], "state": "idle",
                 "updated_at": time.time(), "messages": []}
            self._sessions[user_id] = s
        if s["state"] == "awaiting_message" and (time.time() - s["updated_at"]) > self.TIMEOUT_SECS:
            s["state"] = "idle"
        return s

    def reset(self, user_id: str) -> None:
        self._sessions.pop(user_id, None)

    def welcome(self, user_id: str) -> dict:
        s = self._session(user_id)
        s["current_path"] = []
        s["state"] = "idle"
        s["updated_at"] = time.time()
        return self._wrap([
            {"type": "text", "text": WELCOME_MSG_PREFIX.format(title=self.title) + " 👋"},
            *self._render_node([]),
        ])

    def handle(self, user_id: str, text: Optional[str] = None, payload: Optional[str] = None) -> dict:
        s = self._session(user_id)
        s["updated_at"] = time.time()

        if payload:
            return self._handle_payload(user_id, payload)
        if not text:
            return self._wrap(self._render_node(s["current_path"]))
        return self._handle_text(user_id, text.strip())

    def _handle_payload(self, user_id: str, payload: str) -> dict:
        if payload.startswith("label:"):
            return self._handle_text(user_id, payload[6:])
        if payload == "back":
            return self._handle_text(user_id, BACK_LABEL)
        if payload == "home":
            return self._handle_text(user_id, HOME_LABEL)
        if payload == "welcome":
            return self.welcome(user_id)
        return self._wrap([
            {"type": "text", "text": FALLBACK_MSG},
            *self._render_node(self._session(user_id)["current_path"]),
        ])

    def _handle_text(self, user_id: str, text: str) -> dict:
        s = self._session(user_id)

        # 1) 留言收集中
        if s["state"] == "awaiting_message":
            s["messages"].append(text)
            s["state"] = "idle"
            s["current_path"] = []
            return self._wrap([
                {"type": "text", "text": MESSAGE_RECEIVED},
                *self._render_node([]),
            ])

        if _get_node(self.menu, s["current_path"]) is None:
            s["current_path"] = []

        # 2) 導航
        if text in (BACK_LABEL, "上一層", "← 上一層"):
            s["current_path"] = s["current_path"][:-1] if s["current_path"] else []
            return self._enter_node(user_id, s["current_path"])

        if text == HOME_LABEL:
            return self._enter_node(user_id, [])

        # 3) 全樹 label 比對
        found = _find_path_by_label(self.menu, text)
        if found is not None:
            return self._enter_node(user_id, found)

        # 4) fallback
        return self._wrap([
            {"type": "text", "text": FALLBACK_MSG},
            *self._render_node(s["current_path"]),
        ])

    def _enter_node(self, user_id: str, path) -> dict:
        s = self._session(user_id)
        node = _get_node(self.menu, path)
        if node is None:
            path = []
            node = self.menu

        action = node.get("action")
        if action == "collect_message":
            s["state"] = "awaiting_message"
            s["current_path"] = path
            return self._wrap([{"type": "text", "text": COLLECT_MSG_PROMPT}])

        if action == "call_phone":
            phone = (node.get("phone") or "").strip()
            body = node.get("text") or (
                f"真人客服專線\n{phone}\n\n手機按下方「撥打電話」可直接撥號；桌機請手動撥打。"
            )
            quick = {"items": []}
            if phone:
                quick["items"].append({
                    "type": "action",
                    "action": {"type": "uri", "label": "撥打電話", "uri": f"tel:{phone}"},
                })
            self._append_nav_items(quick["items"], path)
            s["state"] = "idle"
            s["current_path"] = path
            return {"messages": [{"type": "text", "text": body}], "quickReply": quick}

        s["state"] = "idle"
        s["current_path"] = path
        return self._wrap(self._render_node(path))

    def _render_node(self, path) -> list:
        node = _get_node(self.menu, path)
        if node is None:
            node = self.menu
            path = []
        kind = _node_kind(node)

        if kind == "branch":
            head = node.get("label", "")
            desc = node.get("description")
            body = head if not desc else f"{head}\n\n{desc}"
            quick_items = []
            for child in node["children"]:
                lbl = child.get("label", "")
                quick_items.append({
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": lbl[:20],
                        "data": f"label:{lbl}",
                        "displayText": lbl,
                    },
                })
            self._append_nav_items(quick_items, path)
            return [{"type": "text", "text": body, "_quickReply": quick_items[:QUICK_REPLY_MAX]}]

        if kind == "leaf":
            body = node.get("text") or node.get("label", "")
            quick_items = []
            self._append_nav_items(quick_items, path)
            return [{"type": "text", "text": body, "_quickReply": quick_items}]

        # empty
        quick_items = []
        self._append_nav_items(quick_items, path)
        return [{"type": "text", "text": EMPTY_NODE_MSG, "_quickReply": quick_items}]

    def _append_nav_items(self, items, path):
        if not path:
            return
        items.append({
            "type": "action",
            "action": {"type": "postback", "label": BACK_LABEL[:20], "data": "back", "displayText": BACK_LABEL},
        })
        items.append({
            "type": "action",
            "action": {"type": "postback", "label": HOME_LABEL[:20], "data": "home", "displayText": HOME_LABEL},
        })

    def _wrap(self, messages):
        out_msgs = []
        last_quick = []
        for m in messages:
            mm = {k: v for k, v in m.items() if not k.startswith("_")}
            out_msgs.append(mm)
            if m.get("_quickReply"):
                last_quick = m["_quickReply"]
        result = {"messages": out_msgs}
        if last_quick:
            result["quickReply"] = {"items": last_quick}
        return result
