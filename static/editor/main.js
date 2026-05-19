/*
 * editor/main.js — 啟動入口 + 分頁切換 + 事件接線
 *
 * 定位:
 *   最後載入的模組。負責綁定 DOM 事件到各功能函式、處理分頁切換。
 *
 * 包含單元 (units):
 *   switchTab(tab)        切換 [編輯 | 樹狀圖預覽 | 公版管理] 三個分頁
 *   DOMContentLoaded      綁定所有按鈕 / 表單事件，啟動載入流程
 */

function switchTab(tab) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === tab)
  );
  $("#edit-pane").classList.toggle("hidden", tab !== "edit");
  $("#tree-pane").classList.toggle("hidden", tab !== "tree");
  $("#templates-pane").classList.toggle("hidden", tab !== "templates");
  $("#edit-actions").classList.toggle("hidden", tab !== "edit");

  if (tab === "tree") drawTreeViz();
  if (tab === "templates") loadTemplates();
}

document.addEventListener("DOMContentLoaded", () => {
  // 分頁切換
  document.querySelectorAll(".tab").forEach((t) => {
    t.onclick = () => switchTab(t.dataset.tab);
  });

  // 編輯工具列
  $("#btn-add").onclick = addChild;
  $("#btn-del").onclick = deleteNode;
  $("#btn-up").onclick = () => moveNode(-1);
  $("#btn-down").onclick = () => moveNode(1);
  $("#btn-reload").onclick = reload;
  $("#btn-save").onclick = saveMenu;
  $("#btn-apply").onclick = applyChanges;
  $("#btn-apply-tpl").onclick = applyTemplateToForm;

  // 公版頁工具列
  $("#btn-tpl-new").onclick = newTemplate;
  $("#btn-tpl-save").onclick = saveTemplate;
  $("#btn-tpl-delete").onclick = deleteTemplate;

  // 表單欄位 dirty 追蹤
  ["#f-label", "#f-desc", "#f-text", "#f-phone"].forEach((s) => {
    $(s).addEventListener("input", () => { fieldsDirty = true; });
  });
  $("#f-action").addEventListener("change", () => {
    updateFieldStates();
    fieldsDirty = true;
  });
  document.querySelectorAll('input[name="type"]').forEach((r) => {
    r.addEventListener("change", () => {
      updateFieldStates();
      fieldsDirty = true;
    });
  });

  // 公版表單 dirty 追蹤
  ["#tpl-id", "#tpl-name", "#tpl-description", "#tpl-text"].forEach((s) => {
    $(s).addEventListener("input", () => { tplDirty = true; });
  });

  // 離開頁面前確認
  window.addEventListener("beforeunload", (e) => {
    if (treeDirty || fieldsDirty || tplDirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  // 初始載入：actions + templates 平行，完成後再載 menu
  Promise.all([loadActions(), loadTemplates()]).then(loadMenu);
});
