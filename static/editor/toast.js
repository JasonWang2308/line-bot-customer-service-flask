/*
 * editor/toast.js — 浮動提示
 *
 * 定位:
 *   被多個模組共用的 toast 提示元件。延遲 3 秒自動淡出。
 *
 * 包含單元 (units):
 *   showToast(message, type)   type: 'success' | 'error'
 */

let _toastTimer = null;

function showToast(message, type) {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.className = `toast ${type}`;
  toast.innerHTML = "";

  const icon = document.createElement("span");
  icon.className = "toast-icon";
  icon.textContent = type === "success" ? "✓" : "!";

  const text = document.createElement("span");
  text.textContent = message;

  toast.appendChild(icon);
  toast.appendChild(text);

  // 觸發 reflow 讓 transition 生效
  void toast.offsetWidth;
  toast.classList.add("show");

  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => toast.classList.remove("show"), 3000);
}
