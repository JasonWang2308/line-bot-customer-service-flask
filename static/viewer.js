/*
 * viewer.js — 聊天介面前端模組（呈現層）
 *
 * 定位:
 *   把 menu.json 渲染成累積式聊天 UI，並對齊 line_bot.py 的行為，
 *   讓 admin 在本機 /viewer 看到的效果與實際 LINE bot 一致。
 *   資料來源是 /api/menu。
 *
 * 包含單元 (units):
 *   loadMenu                       向後端取得 menu 資料
 *   getNode / nodeKind             路徑取節點 / 判斷類型
 *   findNodeByLabel                依完整 label 搜尋節點
 *   buildBotBubble / showNode      bot bubble 組裝與插入
 *   appendUser / appendBotText     追加訊息泡泡
 *   handleTextSubmit               處理使用者輸入
 *   handleUpload                   貼圖/圖片/影片/聲音模擬
 *   reset                          清空對話從頭
 *
 * Action 對齊:
 *   進入節點時若 node.action === "collect_message" → 顯示 COLLECT_MSG_PROMPT
 *   並切換 state="awaiting_message"；下一則使用者輸入會被視為留言內容，
 *   bot 回 MESSAGE_RECEIVED + FOLLOW_UP_MSG（預覽模式不寫 DB）。
 */

let menuData = null;
let currentPath = [];
let viewerState = "idle";   // 'idle' | 'awaiting_message'
let _initialMenuShown = false;  // 模擬器：首次輸入文字才彈出主選單

// 從 viewer.html 注入的 window.APP_CONSTANTS 取常數；fallback 是 hardcoded 預設
// (避免後端常數沒注入時整個前端壞掉)
const C = window.APP_CONSTANTS || {};
const BACK_LABEL = C.back_label || "← 上一層";
const HOME_LABEL = C.home_label || "回主選單";
const FALLBACK_MSG = C.fallback_msg || "請透過下方選項按鈕進行操作哦!";
const NON_TEXT_HINT = C.non_text_hint || "請以文字描述您的問題，或點選下方選項。";
const EMPTY_NODE_MSG = C.empty_node_msg || "(此項目尚未設定內容)";
const COLLECT_MSG_PROMPT = C.collect_msg_prompt || "請輸入您想留言的內容，我們將於上班時間由真人客服回覆您。";
const MESSAGE_RECEIVED = C.message_received || "我們已收到您的問題，等上班時間會由真人客服為您回復，感謝您的配合！";

const $log = () => document.getElementById("chat-log");

/**
 * 把 text 寫進 el；其中的 http(s) URL 轉成可點擊的 <a>，其餘保留為純文字。
 * 用 DOM API 拼接（不用 innerHTML）→ 自動防 XSS。
 *
 * 與 LINE 行為對齊：實機 LINE 也會把 http(s):// 自動變成可點連結。
 * 這個函式讓網頁預覽 /viewer 視覺也一致。
 */
function setTextWithLinks(el, text) {
  el.textContent = "";
  if (!text) return;
  const urlRe = /(https?:\/\/[^\s<>"']+)/g;
  let lastIdx = 0;
  let match;
  while ((match = urlRe.exec(text)) !== null) {
    if (match.index > lastIdx) {
      el.appendChild(document.createTextNode(text.slice(lastIdx, match.index)));
    }
    const a = document.createElement("a");
    a.href = match[1];
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = match[1];
    el.appendChild(a);
    lastIdx = urlRe.lastIndex;
  }
  if (lastIdx < text.length) {
    el.appendChild(document.createTextNode(text.slice(lastIdx)));
  }
}

async function loadMenu() {
  const res = await fetch("/api/menu");
  menuData = await res.json();
}

// findNodeByPath / nodeKind 來自 menu-utils.js (跨頁共用)
function getNode(path) {
  return findNodeByPath(menuData, path);
}

function buildBotBubble(path) {
  const node = getNode(path);
  if (!node) return null;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const title = document.createElement("div");
  title.className = "bubble-title";
  title.textContent = node.label;
  bubble.appendChild(title);

  const kind = nodeKind(node);

  if (kind === "branch") {
    if (node.description) {
      const desc = document.createElement("div");
      desc.className = "bubble-desc";
      setTextWithLinks(desc, node.description);
      bubble.appendChild(desc);
    }

    const btnGroup = document.createElement("div");
    btnGroup.className = "bubble-buttons";

    node.children.forEach((child, i) => {
      const btn = makeBtn(child.label, "option", () => {
        disableBubble(bubble);
        appendUser(child.label);
        showNode([...path, i]);
      });
      btnGroup.appendChild(btn);
    });

    appendNavButtons(btnGroup, bubble, path);
    bubble.appendChild(btnGroup);
  } else if (kind === "leaf") {
    const text = document.createElement("div");
    text.className = "bubble-text";
    setTextWithLinks(text, node.text);
    bubble.appendChild(text);

    const btnGroup = document.createElement("div");
    btnGroup.className = "bubble-buttons";
    appendNavButtons(btnGroup, bubble, path);
    bubble.appendChild(btnGroup);
  } else {
    const text = document.createElement("div");
    text.className = "placeholder";
    text.textContent = EMPTY_NODE_MSG;
    bubble.appendChild(text);

    const btnGroup = document.createElement("div");
    btnGroup.className = "bubble-buttons";
    appendNavButtons(btnGroup, bubble, path);
    bubble.appendChild(btnGroup);
  }

  return bubble;
}

function makeBtn(label, kind, onClick) {
  const btn = document.createElement("button");
  btn.className = kind === "nav" ? "bubble-btn nav" : "bubble-btn";
  btn.textContent = label;
  btn.onclick = onClick;
  return btn;
}

function appendNavButtons(btnGroup, bubble, path) {
  if (path.length === 0) return;

  const div = document.createElement("div");
  div.className = "bubble-divider";
  btnGroup.appendChild(div);

  const back = makeBtn(BACK_LABEL, "nav", () => {
    disableBubble(bubble);
    appendUser("上一層");
    showNode(path.slice(0, -1));
  });
  btnGroup.appendChild(back);

  const home = makeBtn(HOME_LABEL, "nav", () => {
    disableBubble(bubble);
    appendUser(HOME_LABEL);
    showNode([]);
  });
  btnGroup.appendChild(home);
}

function disableBubble(bubble) {
  bubble.querySelectorAll("button").forEach(b => (b.disabled = true));
}

function showNode(path) {
  _initialMenuShown = true;
  // ── 先看節點是否綁定 action（與 line_bot._enter_node 對齊）─────
  const node = getNode(path);
  if (node && node.action === "collect_message") {
    currentPath = path;
    viewerState = "awaiting_message";
    appendBotText(COLLECT_MSG_PROMPT);
    return;
  }

  if (node && node.action === "call_phone") {
    currentPath = path;
    viewerState = "idle";
    appendCallPhoneBubble(node.phone || "", path);
    return;
  }

  // ── 預設渲染 ──────────────────────────────────────────────
  const bubble = buildBotBubble(path);
  if (!bubble) return;
  currentPath = path;
  viewerState = "idle";

  const row = document.createElement("div");
  row.className = "row bot";
  const avatar = document.createElement("div");
  avatar.className = "row-avatar";
  avatar.textContent = "客";
  row.appendChild(avatar);
  row.appendChild(bubble);
  $log().appendChild(row);
  scrollToBottom();
}

function appendUser(text) {
  const row = document.createElement("div");
  row.className = "row user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  row.appendChild(bubble);
  $log().appendChild(row);
  scrollToBottom();
}

function scrollToBottom() {
  const log = $log();
  setTimeout(() => { log.scrollTop = log.scrollHeight; }, 0);
}

function reset() {
  $log().innerHTML = "";
  viewerState = "idle";
  currentPath = [];
  _initialMenuShown = false;  // 模擬器：reset 後等下一次輸入才重新顯示主選單
  // showNode([]);
}

// findPathByLabel 來自 menu-utils.js (跨頁共用)

function appendCallPhoneBubble(phoneRaw, path) {
  const phoneDial = (phoneRaw || "").replace(/[^\d+]/g, "");

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const title = document.createElement("div");
  title.className = "bubble-title";
  title.textContent = "真人客服專線";
  bubble.appendChild(title);

  const text = document.createElement("div");
  text.className = "bubble-text";
  text.textContent = phoneRaw || "(尚未設定電話號碼)";
  bubble.appendChild(text);

  const btnGroup = document.createElement("div");
  btnGroup.className = "bubble-buttons";

  // 撥打電話: 用 <a href="tel:..."> 包裝, 仿 button 外觀
  if (phoneDial) {
    const callBtn = document.createElement("a");
    callBtn.className = "bubble-btn";
    callBtn.href = `tel:${phoneDial}`;
    callBtn.textContent = "撥打電話";
    btnGroup.appendChild(callBtn);
  }

  appendNavButtons(btnGroup, bubble, path);
  bubble.appendChild(btnGroup);

  const row = document.createElement("div");
  row.className = "row bot";
  const avatar = document.createElement("div");
  avatar.className = "row-avatar";
  avatar.textContent = "客";
  row.appendChild(avatar);
  row.appendChild(bubble);
  $log().appendChild(row);
  scrollToBottom();
}

function appendBotText(text) {
  const row = document.createElement("div");
  row.className = "row bot";
  const avatar = document.createElement("div");
  avatar.className = "row-avatar";
  avatar.textContent = "客";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const t = document.createElement("div");
  t.className = "bubble-text";
  setTextWithLinks(t, text);
  bubble.appendChild(t);
  row.appendChild(avatar);
  row.appendChild(bubble);
  $log().appendChild(row);
  scrollToBottom();
}

function handleTextSubmit() {
  const input = document.getElementById("msg-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  appendUser(text);

  // 模擬器：首次輸入 → 若文字完全符合某個 label 直接跳該節點；否則顯示主選單
  if (!_initialMenuShown) {
    const _matched = findPathByLabel(menuData, text);
    if (_matched) {
      showNode(_matched);
    } else {
      showNode([]);
    }
    return;  // showNode 已把 _initialMenuShown 設 true
  }

  // ── 留言收集中：訊息視為留言內容（預覽不寫 DB），完成後回主選單 ────
  if (viewerState === "awaiting_message") {
    viewerState = "idle";
    // 模擬器：實際把留言寫入 SQLite（讓 /admin/messages 看得到）
    fetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).catch((e) => console.warn("save message failed", e));
    appendBotText(MESSAGE_RECEIVED);
    showNode([]);   // 直接帶出主選單對話框
    return;
  }

  // ── 上一層 / 回主選單 ──────────────────────────────────
  if (text === "上一層" || text === BACK_LABEL) {
    showNode(currentPath.length > 0 ? currentPath.slice(0, -1) : []);
    return;
  }
  if (text === HOME_LABEL) {
    showNode([]);
    return;
  }

  // ── 全域 label 比對 ─────────────────────────────────────
  const path = findPathByLabel(menuData, text);
  if (path) {
    showNode(path);
  } else {
    appendBotText(FALLBACK_MSG);
    showNode(currentPath);
  }
}

function handleUpload(type) {
  const labels = { sticker: "貼圖", image: "圖片", video: "影片", audio: "聲音" };
  appendUser(`[${labels[type] || type}]`);

  // 留言收集中收到非文字 → 提示要打字輸入留言內容（保持留言模式）
  if (viewerState === "awaiting_message") {
    appendBotText(COLLECT_MSG_PROMPT);
    return;
  }

  // 一般情況：提示 + 同步顯示當前節點選項，使用者不必再輸入文字
  appendBotText(NON_TEXT_HINT);
  showNode(currentPath);
}

(async () => {
  await loadMenu();
  // showNode([]);  // 模擬器：等使用者輸入任意文字才顯示主選單
  document.getElementById("reset-btn").onclick = reset;
  document.getElementById("send-btn").onclick = handleTextSubmit;
  document.getElementById("msg-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleTextSubmit();
    }
  });
  document.querySelectorAll(".upload-btn").forEach((b) => {
    b.onclick = () => handleUpload(b.dataset.type);
  });
})();
