import os
import time
from flask import Flask, request, jsonify, render_template_string, abort
from dotenv import load_dotenv
import db
import matcher
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    StickerMessageContent,
)

load_dotenv()

app = Flask(__name__)

# ── LINE 設定 ─────────────────────────────────────────────────

configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

# ── 共用常數 ──────────────────────────────────────────────────

FOLLOW_UP_MSG      = "若還有其他問題可以直接輸入進行詢問。"
COLLECT_MSG_PROMPT = "請輸入您想留言的內容，我們將於上班時間由真人客服回覆您。"
MESSAGE_RECEIVED   = "我們已收到您的問題，等上班時間會由真人客服為您回復，感謝您的配合！"
TIMEOUT_SECS       = 90
WEB_USER_ID        = "web_admin"

# ── Web 記憶體 session（單用戶，省去 SQLite I/O）────────────
_WEB_SESSION: dict = {}

def _web_get() -> dict:
    if not _WEB_SESSION:
        _WEB_SESSION.update({
            "user_id": WEB_USER_ID, "state": "idle",
            "resolved_ids": [], "pending_dims": [],
            "current_dim": None, "raw_input": None,
            "turn_count": 0, "updated_at": None,
        })
    return _WEB_SESSION

def _web_save():
    _WEB_SESSION["updated_at"] = time.time()

def _web_reset():
    _WEB_SESSION.clear()

def _web_expired() -> bool:
    ts = _WEB_SESSION.get("updated_at")
    return bool(ts and (time.time() - ts) > TIMEOUT_SECS)


# ── LINE routes ───────────────────────────────────────────────

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
def handle_line_message(event):
    user_id = event.source.user_id
    text    = event.message.text.strip()

    session = db.get_session(user_id)

    # 逾時重置
    timed_out_feedback = False
    if session["state"] in ("collecting", "awaiting_feedback") and db.is_expired(session, TIMEOUT_SECS):
        if session["state"] == "awaiting_feedback":
            timed_out_feedback = True
        db.reset_session(user_id)
        session = db.get_session(user_id)

    result = matcher.process(text, session)

    if result["status"] in ("resolved", "message_received", "conflict"):
        if result["status"] != "conflict":
            db.log_conversation(session, result["status"])
        db.reset_session(user_id)
    else:
        db.save_session(session)

    # 留言存入資料庫
    if result["status"] == "message_received":
        try:
            with ApiClient(configuration) as api_client:
                profile = MessagingApi(api_client).get_profile(user_id)
            display_name = profile.display_name
        except Exception:
            display_name = user_id
        db.save_message(user_id, display_name, result["content"])

    messages = _build_line_messages(result)
    if timed_out_feedback:
        messages = [TextMessage(text=FOLLOW_UP_MSG)] + messages

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages,
            )
        )


def _reply_non_text(event, hint: str):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=hint)],
            )
        )


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_line_image(event):
    _reply_non_text(event, "請以文字描述您的問題，例如：「How do I reset my password?」")


@handler.add(MessageEvent, message=StickerMessageContent)
def handle_line_sticker(event):
    _reply_non_text(event, "請以文字描述您的問題，例如：「How do I reset my password?」")


def _build_line_messages(result: dict) -> list:
    status = result["status"]

    if status == "answer":
        quick_reply_items = [
            QuickReplyItem(action=MessageAction(label=opt["label"], text=opt["label"]))
            for opt in result["feedback_options"]
        ]
        return [
            TextMessage(text=result["answer"]),
            TextMessage(
                text=result["feedback_question"],
                quick_reply=QuickReply(items=quick_reply_items),
            ),
        ]

    if status == "resolved":
        return [TextMessage(text=FOLLOW_UP_MSG)]

    if status == "collect_message":
        return [TextMessage(text=COLLECT_MSG_PROMPT)]

    if status == "message_received":
        return [TextMessage(text=MESSAGE_RECEIVED), TextMessage(text=FOLLOW_UP_MSG)]

    if status == "escalate":
        return [
            TextMessage(text=result["message"]),
            TextMessage(text=FOLLOW_UP_MSG),
        ]

    if status == "feedback":
        quick_reply_items = [
            QuickReplyItem(action=MessageAction(label=opt["label"], text=opt["label"]))
            for opt in result["options"]
        ]
        return [
            TextMessage(
                text=result["question"],
                quick_reply=QuickReply(items=quick_reply_items),
            )
        ]

    if status == "clarify":
        quick_reply_items = [
            QuickReplyItem(action=MessageAction(label=opt["label"], text=opt["label"]))
            for opt in result["options"]
        ]
        return [
            TextMessage(
                text=result["question"],
                quick_reply=QuickReply(items=quick_reply_items),
            )
        ]

    if status == "conflict":
        label = result["conflict_label"]
        return [
            TextMessage(text=f"您的問題包含多個{label}，請一次詢問一種{label}。"),
            TextMessage(text=FOLLOW_UP_MSG),
        ]

    return []


# ── Web routes ────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


NON_TEXT_REPLY = "目前僅支援文字輸入，請以文字描述您的問題，例如：「How do I reset my password?」"

@app.route("/chat", methods=["POST"])
def chat():
    data  = request.get_json()
    text  = (data.get("message") or "").strip()
    reset = data.get("reset", False)
    msg_type = data.get("type", "text")

    if reset:
        _web_reset()
        return jsonify({"status": "reset"})

    if msg_type == "image":
        return jsonify({"status": "non_text", "message": NON_TEXT_REPLY})

    if not text:
        return jsonify({"error": "empty"}), 400

    session = _web_get()

    timed_out_feedback = False
    if session["state"] in ("collecting", "awaiting_feedback") and _web_expired():
        if session["state"] == "awaiting_feedback":
            timed_out_feedback = True
        _web_reset()
        session = _web_get()

    result = matcher.process(text, session)

    if result["status"] in ("resolved", "message_received", "conflict"):
        if result["status"] != "conflict":
            db.log_conversation(session, result["status"])
        _web_reset()
    else:
        _web_save()

    if result["status"] == "message_received":
        db.save_message(WEB_USER_ID, "Web 用戶", result["content"])
        result = {**result, "reply": MESSAGE_RECEIVED}

    if result["status"] == "collect_message":
        result = {**result, "prompt": COLLECT_MSG_PROMPT}

    return jsonify({
        **result,
        "resolved_ids":       session.get("resolved_ids", []),
        "timed_out_feedback": timed_out_feedback,
    })


@app.route("/admin/messages")
def admin_messages():
    from datetime import datetime, timedelta, timezone
    TW = timezone(timedelta(hours=8))
    now_tw = datetime.now(TW)
    cutoff_today = now_tw.replace(hour=8, minute=30, second=0, microsecond=0)

    # 預設批次
    if now_tw >= cutoff_today:
        default_end_date = now_tw.strftime("%Y-%m-%d")
        default_start_date = (now_tw - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        default_end_date = (now_tw - timedelta(days=1)).strftime("%Y-%m-%d")
        default_start_date = (now_tw - timedelta(days=2)).strftime("%Y-%m-%d")

    # 讀取 query parameter
    from flask import request as req
    q_start = req.args.get("start", default_start_date)  # 格式 YYYY-MM-DD
    q_end   = req.args.get("end",   default_end_date)    # 格式 YYYY-MM-DD（含當天至 08:30）

    # start date 08:30 TW ~ end date 08:30 TW
    start_dt = datetime.strptime(q_start, "%Y-%m-%d").replace(tzinfo=TW)
    start_utc = start_dt.replace(hour=8, minute=30, second=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_dt = datetime.strptime(q_end, "%Y-%m-%d").replace(tzinfo=TW)
    end_utc = end_dt.replace(hour=8, minute=30, second=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    messages = db.get_messages(start=start_utc, end=end_utc)
    for m in messages:
        try:
            utc_dt = datetime.strptime(m["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            m["created_at_tw"] = utc_dt.astimezone(TW).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            m["created_at_tw"] = m.get("created_at", "")
    return render_template_string(ADMIN_HTML, messages=messages,
                                  q_start=q_start, q_end=q_end,
                                  default_start=default_start_date,
                                  default_end=default_end_date)


@app.route("/admin/messages/<int:msg_id>/handle", methods=["POST"])
def handle_message(msg_id):
    data = request.get_json()
    db.mark_handled(msg_id, data.get("handled", 1))
    return jsonify({"ok": True})



# ── HTML ──────────────────────────────────────────────────────

ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>客服留言管理</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f0f2f5; padding: 24px; }
h1 { font-size: 20px; font-weight: 600; margin-bottom: 20px; color: #1a1a1a; }
.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tab { padding: 7px 20px; border-radius: 20px; border: 1.5px solid #1a73e8;
       color: #1a73e8; cursor: pointer; font-size: 13px; background: white; }
.tab.active { background: #1a73e8; color: white; }
table { width: 100%; border-collapse: collapse; background: white;
        border-radius: 10px; overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,.1); }
th { background: #1a73e8; color: white; padding: 12px 16px;
     text-align: left; font-size: 13px; font-weight: 500; }
td { padding: 12px 16px; font-size: 14px; border-bottom: 1px solid #f0f0f0;
     vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr.handled td { color: #aaa; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px;
         font-size: 11px; font-weight: 600; }
.badge.pending  { background: #fce8e6; color: #c5221f; }
.badge.done     { background: #e6f4ea; color: #137333; }
.btn { padding: 5px 14px; border-radius: 14px; border: none; cursor: pointer;
       font-size: 12px; }
.btn-done   { background: #1a73e8; color: white; }
.btn-undo   { background: #e0e0e0; color: #555; }
.empty { text-align: center; padding: 40px; color: #aaa; font-size: 14px; }
</style>
</head>
<body>
<div style="display:flex;align-items:center;gap:16px;margin-bottom:20px;flex-wrap:wrap">
  <h1 style="margin:0">客服留言管理</h1>
  <form method="get" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
    <label style="font-size:13px;color:#555">日期：</label>
    <input type="date" name="start" value="{{ q_start }}" style="border:1.5px solid #ddd;border-radius:8px;padding:5px 10px;font-size:13px">
    <span style="font-size:13px;color:#555">至</span>
    <input type="date" name="end" value="{{ q_end }}" style="border:1.5px solid #ddd;border-radius:8px;padding:5px 10px;font-size:13px">
    <button type="submit" style="background:#1a73e8;color:white;border:none;border-radius:8px;padding:6px 16px;font-size:13px;cursor:pointer">查詢</button>
    <a href="/admin/messages" style="font-size:13px;color:#1a73e8;text-decoration:none">回今日批次</a>
  </form>
</div>
<div class="tabs" style="margin-bottom:16px">
  <button class="tab active" onclick="filter(0, this)">待處理</button>
  <button class="tab" onclick="filter(1, this)">已處理</button>
  <button class="tab" onclick="filter(null, this)">全部</button>
</div>
<table>
  <thead>
    <tr>
      <th style="width:220px">LINE User ID</th>
      <th style="width:130px">姓名</th>
      <th style="width:150px">時間（台灣）</th>
      <th>留言內容</th>
      <th style="width:80px">狀態</th>
      <th style="width:110px" id="action-th">操作</th>

    </tr>
  </thead>
  <tbody id="tbody">
  {% for m in messages %}
  <tr id="row-{{ m.id }}" class="{{ 'handled' if m.handled else '' }}">
    <td style="font-size:12px;color:#888;word-break:break-all">
      {{ m.user_id }}

    </td>
    <td>{{ m.display_name }}</td>
    <td style="white-space:nowrap">{{ m.created_at_tw }}</td>
    <td style="max-width:400px;white-space:pre-wrap">{{ m.content }}</td>
    <td><span class="badge {{ 'done' if m.handled else 'pending' }}">
      {{ '已處理' if m.handled else '待處理' }}</span></td>
    <td class="action-col">
      {% if m.handled %}
      <button class="btn btn-undo" onclick="toggle({{ m.id }}, 0)">取消</button>
      {% else %}
      <button class="btn btn-done" onclick="toggle({{ m.id }}, 1)">標記已處理</button>
      {% endif %}
    </td>
  </tr>
  {% else %}
  <tr><td colspan="6" class="empty">目前沒有留言</td></tr>
  {% endfor %}
  </tbody>
</table>
<script>
let currentFilter = 0;
function filter(val, btn) {
  currentFilter = val;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('#tbody tr[id]').forEach(row => {
    const isHandled = row.classList.contains('handled');
    if (val === null) row.style.display = '';
    else if (val === 0) row.style.display = isHandled ? 'none' : '';
    else row.style.display = isHandled ? '' : 'none';
  });
  // 全部 tab 隱藏操作欄
  // 全部 tab 隱藏操作欄，待處理/已處理顯示
  const showAction = (val === null) ? false : true;
  document.querySelectorAll('.action-col').forEach(td => {
    td.style.display = showAction ? 'table-cell' : 'none';
  });
  const th = document.getElementById('action-th');
  if (th) th.style.display = showAction ? 'table-cell' : 'none';
}
async function toggle(id, handled) {
  await fetch(`/admin/messages/${id}/handle`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ handled }),
  });
  location.reload();
}
filter(0, document.querySelector('.tab.active'));
</script>
</body>
</html>"""

HTML = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Customer Service QA Bot</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f0f2f5;
       height: 100vh; display: flex; flex-direction: column; }

header { background: #1a73e8; color: white; padding: 14px 20px;
         display: flex; justify-content: space-between; align-items: center; }
header h1 { font-size: 17px; font-weight: 600; }
#resetBtn { background: rgba(255,255,255,.2); border: none; color: white;
            padding: 6px 16px; border-radius: 20px; cursor: pointer; font-size: 13px; }
#resetBtn:hover { background: rgba(255,255,255,.35); }

#chat { flex: 1; overflow-y: auto; padding: 20px 16px;
        display: flex; flex-direction: column; gap: 14px; }

.row { display: flex; align-items: flex-end; gap: 8px; }
.row.user { flex-direction: row-reverse; }

.avatar { width: 32px; height: 32px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-size: 17px; flex-shrink: 0; background: #e8e8e8; }

.bubble { max-width: 72%; padding: 11px 15px; border-radius: 18px;
          line-height: 1.65; font-size: 14px; word-break: break-word;
          white-space: pre-wrap; }
.row.bot  .bubble { background: white; color: #1a1a1a;
                    border-bottom-left-radius: 4px;
                    box-shadow: 0 1px 3px rgba(0,0,0,.12); }
.row.user .bubble { background: #1a73e8; color: white;
                    border-bottom-right-radius: 4px; }

.row.bot.answer    .bubble { border-left: 4px solid #34a853; }
.row.bot.clarify   .bubble { border-left: 4px solid #fbbc04; }
.row.bot.no_match  .bubble { border-left: 4px solid #ea4335; }
.row.bot.follow_up .bubble { color: #888; font-size: 13px; }

.tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; padding-left: 40px; }
.tag  { background: #e8f0fe; color: #1a73e8; font-size: 11px;
        padding: 2px 9px; border-radius: 10px; }

#optArea { padding: 0 16px 10px; display: flex; flex-wrap: wrap; gap: 8px; }
#optArea:empty { display: none; }
.opt-btn { background: white; border: 1.5px solid #1a73e8; color: #1a73e8;
           padding: 7px 16px; border-radius: 20px; cursor: pointer;
           font-size: 13px; transition: .15s; }
.opt-btn:hover { background: #1a73e8; color: white; }

#inputArea { background: white; padding: 12px 16px;
             border-top: 1px solid #e0e0e0;
             display: flex; gap: 10px; align-items: flex-end; }
#msgInput { flex: 1; border: 1.5px solid #ddd; border-radius: 22px;
            padding: 9px 15px; font-size: 14px; resize: none; outline: none;
            min-height: 40px; max-height: 120px; line-height: 1.5; }
#msgInput:focus { border-color: #1a73e8; }
#sendBtn { background: #1a73e8; color: white; border: none; border-radius: 50%;
           width: 40px; height: 40px; cursor: pointer; flex-shrink: 0;
           display: flex; align-items: center; justify-content: center; }
#sendBtn:hover { background: #1557b0; }
#imgBtn { background: none; border: none; cursor: pointer; padding: 4px;
          color: #888; flex-shrink: 0; display: flex; align-items: center; }
#imgBtn:hover { color: #1a73e8; }
#imgInput { display: none; }
.img-bubble { max-width: 220px; border-radius: 12px; display: block; }
</style>
</head>
<body>

<header>
  <h1>Customer Service QA Bot</h1>
  <button id="resetBtn">↺ 重新開始</button>
</header>

<div id="chat">
  <div class="row bot">
    <div class="avatar">🤖</div>
    <div class="bubble">您好！請描述您遇到的問題，例如：「How do I reset my password?」</div>
  </div>
</div>

<div id="optArea"></div>

<div id="inputArea">
  <input type="file" id="imgInput" accept="image/*">
  <button id="imgBtn" title="傳送圖片">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
    </svg>
  </button>
  <textarea id="msgInput" placeholder="輸入問題…" rows="1"></textarea>
  <button id="sendBtn">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
      <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
    </svg>
  </button>
</div>

<script>
const chatEl  = document.getElementById('chat');
const optArea = document.getElementById('optArea');
const input   = document.getElementById('msgInput');

const FOLLOW_UP = '若還有其他問題可以直接輸入進行詢問。';
const TIMEOUT_MS = 90_000;
let timeoutTimer = null;

function clearTimer() {
  if (timeoutTimer) { clearTimeout(timeoutTimer); timeoutTimer = null; }
}

function startTimer() {
  clearTimer();
  timeoutTimer = setTimeout(async () => {
    clearOptions();
    try {
      await fetch('/chat', {
        method:  'POST',
        headers: {'Content-Type': 'application/json'},
        body:    JSON.stringify({ reset: true }),
      });
    } catch (_) {}
    addBubble('bot', '回應逾時，對話已自動結束。' + FOLLOW_UP, 'follow_up');
  }, TIMEOUT_MS);
}

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
}

function addBubble(role, text, status='', tags=[]) {
  const row = document.createElement('div');
  row.className = `row ${role} ${status}`.trim();

  const av   = role === 'bot' ? '🤖' : '👤';
  const bub  = `<div class="bubble">${esc(text)}</div>`;
  const avEl = `<div class="avatar">${av}</div>`;

  row.innerHTML = role === 'bot' ? avEl + bub : bub + avEl;
  chatEl.appendChild(row);

  if (tags.length) {
    const tagRow = document.createElement('div');
    tagRow.className = 'tags';
    tagRow.innerHTML = tags.map(t => `<span class="tag">${esc(t)}</span>`).join('');
    chatEl.appendChild(tagRow);
  }

  chatEl.scrollTop = chatEl.scrollHeight;
}

function clearOptions() {
  optArea.innerHTML = '';
}

function setOptions(options) {
  clearOptions();
  options.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'opt-btn';
    btn.textContent = opt.label;
    btn.onclick = () => doSend(opt.label);
    optArea.appendChild(btn);
  });
}

async function doSend(text) {
  text = text || input.value.trim();
  if (!text) return;
  input.value = '';
  autoResize();
  clearOptions();
  clearTimer();

  addBubble('user', text);

  const res  = await fetch('/chat', {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify({ message: text }),
  });
  const data = await res.json();

  if (data.timed_out_feedback) {
    addBubble('bot', FOLLOW_UP, 'follow_up');
  }

  if (data.status === 'answer') {
    addBubble('bot', data.answer, 'answer', data.resolved_ids || []);
    addBubble('bot', data.feedback_question, 'clarify');
    setOptions(data.feedback_options);
    startTimer();
  } else if (data.status === 'resolved') {
    clearOptions();
    addBubble('bot', FOLLOW_UP, 'follow_up');
  } else if (data.status === 'collect_message') {
    clearOptions();
    clearTimer();
    addBubble('bot', data.prompt, 'clarify');
  } else if (data.status === 'message_received') {
    clearOptions();
    addBubble('bot', data.reply, 'follow_up');
    addBubble('bot', FOLLOW_UP, 'follow_up');
  } else if (data.status === 'escalate') {
    clearOptions();
    addBubble('bot', data.message, 'no_match');
    addBubble('bot', FOLLOW_UP, 'follow_up');
  } else if (data.status === 'feedback') {
    addBubble('bot', data.question, 'clarify');
    setOptions(data.options);
  } else if (data.status === 'non_text') {
    addBubble('bot', data.message, 'no_match');
  } else if (data.status === 'clarify') {

    addBubble('bot', data.question, 'clarify', data.resolved_ids || []);
    setOptions(data.options);
    startTimer();
  } else if (data.status === 'conflict') {
    addBubble('bot', `您的問題包含多個${data.conflict_label}，請一次詢問一種${data.conflict_label}。`, 'no_match');
    addBubble('bot', FOLLOW_UP, 'follow_up');
  }
}

document.getElementById('resetBtn').onclick = async () => {
  clearTimer();
  clearOptions();
  await fetch('/chat', {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify({ reset: true }),
  });
  chatEl.innerHTML = `
    <div class="row bot">
      <div class="avatar">🤖</div>
      <div class="bubble">已重置。請描述您遇到的問題。</div>
    </div>`;
};

document.getElementById('sendBtn').onclick = () => doSend();

// ── 圖片上傳 ──────────────────────────────────────────────────
const imgInput = document.getElementById('imgInput');
document.getElementById('imgBtn').onclick = () => imgInput.click();

imgInput.addEventListener('change', async () => {
  const file = imgInput.files[0];
  if (!file) return;
  imgInput.value = '';

  // 顯示圖片預覽泡泡（使用者端）
  const dataUrl = await new Promise(resolve => {
    const reader = new FileReader();
    reader.onload = e => resolve(e.target.result);
    reader.readAsDataURL(file);
  });
  const row = document.createElement('div');
  row.className = 'row user';
  row.innerHTML = `<img class="img-bubble" src="${dataUrl}" alt="圖片"><div class="avatar">👤</div>`;
  chatEl.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;

  // 通知後端並顯示引導訊息
  const res  = await fetch('/chat', {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify({ type: 'image' }),
  });
  const data = await res.json();
  addBubble('bot', data.message, 'no_match');
});

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); }
});

function autoResize() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
}
input.addEventListener('input', autoResize);
</script>
</body>
</html>"""


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
