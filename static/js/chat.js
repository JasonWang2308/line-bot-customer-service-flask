/* ----------------------------------------------------------
   chat.js — 手機外殼互動
   - 切換 list / chat view
   - 「+」popup 開合
   - 「重新開始聊天」（外部 sim-footer）
   - Rich menu 圖片：使用者送出文字後自動隱藏；reset 後再顯示
   - 自動同步 menu.json：進入聊天 / 重新開始 / 切回分頁時 reload
   ---------------------------------------------------------- */

const phoneScreen = document.getElementById("phoneScreen");
const enterChatBtn = document.getElementById("enterChatBtn");
const backBtn = document.getElementById("backBtn");
const plusBtn = document.getElementById("plusBtn");
const plusMenu = document.getElementById("plusMenu");
const restartChatBtn = document.getElementById("restartChatBtn");
const richMenu = document.getElementById("richMenu");
const msgInput = document.getElementById("msg-input");
const sendBtn = document.getElementById("send-btn");
const menuToggleBtn = document.getElementById("menuToggleBtn");

// 從 viewer.js 拿到的 loadMenu 函式（top-level function 自動掛在 window）
async function refreshMenu() {
  if (typeof window.loadMenu === "function") {
    try { await window.loadMenu(); } catch (e) { console.warn("refreshMenu failed", e); }
  }
}

function showView(name) {
  phoneScreen.dataset.view = name;
  if (name !== "chat") closePlusMenu();
}

// 進入聊天 → 先 reload menu 再切換 view（在 click 上不 await，讓動畫先跑，背景 refresh）
enterChatBtn.addEventListener("click", () => {
  refreshMenu();        // 不 await，背景刷新；下一次操作時 menuData 已是新的
  showView("chat");
});
backBtn.addEventListener("click", () => showView("list"));

// 切回分頁（從編輯器 tab 切回模擬器 tab）→ reload menu
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshMenu();
});
window.addEventListener("focus", refreshMenu);

function openPlusMenu() {
  plusMenu.hidden = false;
  plusBtn.classList.add("is-open");
  plusBtn.setAttribute("aria-expanded", "true");
}
function closePlusMenu() {
  plusMenu.hidden = true;
  plusBtn.classList.remove("is-open");
  plusBtn.setAttribute("aria-expanded", "false");
}

plusBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  if (plusMenu.hidden) openPlusMenu(); else closePlusMenu();
});
plusMenu.addEventListener("click", () => setTimeout(closePlusMenu, 50));
document.addEventListener("click", (e) => {
  if (plusMenu.hidden) return;
  if (plusBtn.contains(e.target)) return;
  if (plusMenu.contains(e.target)) return;
  closePlusMenu();
});

// ── Rich menu show/hide ────────────────────────────────────
function hideRichMenu() {
  if (!richMenu) return;
  richMenu.hidden = true;
  richMenu.style.display = "none";
  if (menuToggleBtn) menuToggleBtn.classList.remove("is-on");
}
function showRichMenu() {
  if (!richMenu) return;
  richMenu.hidden = false;
  richMenu.style.display = "";
  if (menuToggleBtn) menuToggleBtn.classList.add("is-on");
}

msgInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    closePlusMenu();
    if (msgInput.value.trim()) hideRichMenu();
  }
});
sendBtn.addEventListener("click", () => {
  closePlusMenu();
  if (msgInput.value.trim()) hideRichMenu();
});

// ── 重新開始聊天 ────────────────────────────────────────────
if (restartChatBtn) {
  restartChatBtn.addEventListener("click", async () => {
    await refreshMenu();   // 重新開始時必拉最新 menu
    document.getElementById("reset-btn").click();
    closePlusMenu();
    showRichMenu();
    showView("list");
  });
}

// ── 狀態列時鐘：每分鐘對齊本機時間 ────────────────────────
function updateClock() {
  const el = document.getElementById("sbTime");
  if (!el) return;
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  el.textContent = `${hh}:${mm}`;
}
updateClock();
setInterval(updateClock, 30000);  // 每 30 秒同步一次（保證跨越分鐘時很快更新）

// 主選單切換鈕：模擬 LINE 的「鍵盤 ↔ 選單」切換
if (menuToggleBtn) {
  menuToggleBtn.addEventListener("click", () => {
    if (richMenu && (richMenu.hidden || richMenu.style.display === "none")) {
      showRichMenu();
    } else {
      hideRichMenu();
    }
  });
}
