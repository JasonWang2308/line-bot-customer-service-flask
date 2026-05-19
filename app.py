"""
Flask 入口：LINE Bot 本地模擬器
================================
三個入口：
  /                    LINE 風格手機殼 — 聊天列表 → 點擊客服 → 對話畫面
  /editor              選單編輯器 (BOT 原樣)
  /admin/messages      留言管理頁 (BOT 原樣)

舊的 /viewer 已整合進 /，因此被移除。
"""
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request

import db
import line_bot
import messages
from menu_engine import load_menu, save_menu, valid_actions
from messages_constants import frontend_constants
from templates_engine import delete_template, load_templates, upsert_template


load_dotenv()

BASE_DIR = Path(__file__).parent
MENU_FILE = BASE_DIR / "menu.json"
TEMPLATES_FILE = BASE_DIR / "templates.json"

app = Flask(__name__, static_folder="static", template_folder="templates")

db.init_db()
line_bot.setup(app, MENU_FILE)


# ── Landing：手機殼 + 聊天列表 + 內嵌對話 ─────────────────
@app.route("/")
def landing():
    menu = load_menu(MENU_FILE)
    return render_template(
        "index.html",
        bot_title=menu.get("label", "Customer Service Bot"),
        bot_description=menu.get("description", ""),
        chat_title="SaaS Customer Bot — Demo",
        constants=frontend_constants(),
    )


# /viewer 早期版本的對話模擬，現已整合進 /；保留路由以免外部連結爆掉
@app.route("/viewer")
def viewer_redirect():
    return redirect("/", code=302)


@app.route("/editor")
def editor():
    return render_template("editor.html")


# ── BOT 既有 API ─────────────────────────────────────────
@app.route("/api/menu", methods=["GET"])
def api_get_menu():
    return jsonify(load_menu(MENU_FILE))


@app.route("/api/menu", methods=["POST"])
def api_save_menu():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "label" not in data:
        abort(400, "Invalid menu format")
    try:
        save_menu(MENU_FILE, data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})


@app.route("/api/actions", methods=["GET"])
def api_get_actions():
    return jsonify(valid_actions())


@app.route("/api/templates", methods=["GET"])
def api_get_templates():
    return jsonify(load_templates(TEMPLATES_FILE))


@app.route("/api/templates", methods=["POST"])
def api_save_template():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Body must be a JSON object")
    try:
        result = upsert_template(TEMPLATES_FILE, data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "result": result})


@app.route("/api/templates/<tpl_id>", methods=["DELETE"])
def api_delete_template(tpl_id):
    deleted = delete_template(TEMPLATES_FILE, tpl_id)
    return jsonify({"ok": deleted})


# ── 留言管理 ─────────────────────────────────────────────
@app.route("/admin/messages")
def admin_messages():
    ctx = messages.list_with_stats(
        start_date=request.args.get("start"),
        end_date=request.args.get("end"),
    )
    return render_template("admin_messages.html", **ctx)


@app.route("/admin/messages/<int:msg_id>/handle", methods=["POST"])
def handle_message(msg_id):
    data = request.get_json(silent=True) or {}
    db.mark_handled(msg_id, int(data.get("handled", 1)))
    return jsonify({"ok": True})


# ── 模擬器留言寫入：collect_message 流程結束時由 viewer.js 呼叫 ──
@app.route("/api/messages", methods=["POST"])
def api_save_message():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty text"}), 400
    user_id = data.get("user_id") or "web-simulator-user"
    display_name = data.get("display_name") or "網頁模擬使用者"
    db.save_message(user_id, display_name, text)
    return jsonify({"ok": True})


# ── 刪除留言（含二重確認，由前端強制） ──────────────────
@app.route("/admin/messages/<int:msg_id>", methods=["DELETE"])
def api_delete_message(msg_id):
    deleted = db.delete_message(msg_id)
    return jsonify({"ok": deleted})



if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
