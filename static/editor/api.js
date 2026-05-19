/*
 * editor/api.js — 後端通訊
 *
 * 定位:
 *   集中所有 fetch 呼叫；負責把後端資料同步到 state.js 的全域變數，
 *   並觸發必要的 dropdown 重新填充。不直接動 DOM 渲染（那是 tree-list / form 的事）。
 *
 * 對外 API 端點:
 *   GET     /api/menu / POST /api/menu
 *   GET     /api/actions
 *   GET/POST /api/templates / DELETE /api/templates/<id>
 *
 * 包含單元 (units):
 *   api(method, url, body)        fetch 包裝 (拋 Error 帶 server 訊息)
 *   loadActions / loadMenu / loadTemplates  載入並更新 state
 *   saveMenu                      寫回 menu.json
 *   collapseAllBranches           載入後預設摺疊 (僅留 root 展開)
 *   populateActionDropdown / populateTemplateDropdown   下拉選單填充
 */

async function api(method, url, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j.error) msg = j.error;
    } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

async function loadActions() {
  try {
    validActions = await api("GET", "/api/actions");
  } catch (e) {
    validActions = {};
  }
  populateActionDropdown();
}

function populateActionDropdown() {
  const sel = $("#f-action");
  if (!sel) return;
  while (sel.options.length > 1) sel.remove(1);
  Object.entries(validActions).forEach(([id, label]) => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = `${label} (${id})`;
    sel.appendChild(opt);
  });
}

async function loadMenu() {
  menuData = await api("GET", "/api/menu");
  selectedPath = [];
  treeDirty = false;
  collapsedPaths.clear();
  collapseAllBranches(menuData, []);
  renderTree();
  renderForm();
  setStatus("已載入");
}

function collapseAllBranches(node, path) {
  if (!Array.isArray(node.children) || node.children.length === 0) return;
  // root 不摺；其餘所有有子節點的節點預設摺疊
  if (path.length > 0) collapsedPaths.add(pathKey(path));
  node.children.forEach((child, i) => collapseAllBranches(child, [...path, i]));
}

async function saveMenu() {
  try {
    await api("POST", "/api/menu", menuData);
    treeDirty = false;
    setStatus("已儲存到 menu.json");
    showToast("本次修改儲存成功!", "success");
  } catch (e) {
    setStatus(`儲存失敗：${e.message}`);
    showToast(`儲存失敗：${e.message}`, "error");
  }
}

async function loadTemplates() {
  try {
    const data = await api("GET", "/api/templates");
    templates = data.templates || [];
  } catch (e) {
    templates = [];
  }
  populateTemplateDropdown();
  renderTplList();
}

function populateTemplateDropdown() {
  const sel = $("#f-template");
  if (!sel) return;
  while (sel.options.length > 1) sel.remove(1);
  templates.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = `${t.name} (${t.id})`;
    sel.appendChild(opt);
  });
}
