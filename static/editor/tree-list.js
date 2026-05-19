/*
 * editor/tree-list.js — 左側可摺疊樹狀列表 + 結構操作
 *
 * 定位:
 *   渲染 #tree-root 的可摺疊清單，並提供新增 / 刪除 / 移動子節點的 in-memory 操作。
 *   寫入 menu.json 的動作由 api.js 的 saveMenu 完成。
 *
 * 包含單元 (units):
 *   renderTree                重建整棵列表
 *   renderTreeNode            遞迴建構單一節點 (含摺疊圖示與點擊處理)
 *   selectNode(path)          切換選取 (含 dirty 確認)
 *   addChild / deleteNode / moveNode / reload   結構操作
 */

function renderTree() {
  const root = $("#tree-root");
  root.innerHTML = "";
  root.appendChild(renderTreeNode(menuData, []));
}

function renderTreeNode(node, path) {
  const li = document.createElement("li");

  const row = document.createElement("div");
  row.className = "tree-node";
  if (samePath(path, selectedPath)) row.classList.add("selected");

  const hasChildren = Array.isArray(node.children) && node.children.length > 0;
  const collapsed = isCollapsed(path);

  const toggle = document.createElement("span");
  toggle.className = "toggle";
  if (hasChildren) {
    toggle.classList.add("clickable");
    toggle.textContent = collapsed ? "▸" : "▾";
    toggle.onclick = (e) => {
      e.stopPropagation();
      setCollapsed(path, !collapsed);
      renderTree();
    };
  } else {
    toggle.textContent = "·";
  }
  row.appendChild(toggle);

  const label = document.createElement("span");
  label.textContent = node.label || "(未命名)";
  row.appendChild(label);

  const kind = document.createElement("span");
  kind.className = "kind";
  kind.textContent = `[${kindLabel(nodeKind(node))}]`;
  row.appendChild(kind);

  row.onclick = (e) => {
    e.stopPropagation();
    selectNode(path);
  };
  li.appendChild(row);

  if (hasChildren && !collapsed) {
    const ul = document.createElement("ul");
    node.children.forEach((child, i) => {
      ul.appendChild(renderTreeNode(child, [...path, i]));
    });
    li.appendChild(ul);
  }
  return li;
}

function selectNode(path) {
  if (fieldsDirty) {
    if (!confirm("欄位有未套用變更，要捨棄嗎?")) return;
  }
  selectedPath = path;
  renderTree();
  renderForm();
}

function addChild() {
  const parent = getNode(selectedPath);
  const label = prompt("新節點標題:");
  if (!label) return;
  const trimmed = label.trim();
  if (!trimmed) return;

  const hasChildren = Array.isArray(parent.children) && parent.children.length > 0;
  if ("text" in parent && !hasChildren) {
    if (!confirm(`「${parent.label}」目前是答覆類型，新增子節點會清除它的回覆內容。確定?`)) return;
    delete parent.text;
  }
  if (!Array.isArray(parent.children)) parent.children = [];

  parent.children.push({ label: trimmed });
  setCollapsed(selectedPath, false);
  selectedPath = [...selectedPath, parent.children.length - 1];
  treeDirty = true;
  renderTree();
  renderForm();
  setStatus(`已新增「${trimmed}」（記得儲存）`);
}

function deleteNode() {
  if (selectedPath.length === 0) {
    alert("不能刪除根節點。");
    return;
  }
  const node = getNode(selectedPath);
  if (!confirm(`確定刪除「${node.label}」及其所有子節點?`)) return;

  const parent = getParent(selectedPath);
  const idx = selectedPath[selectedPath.length - 1];
  parent.children.splice(idx, 1);

  selectedPath = selectedPath.slice(0, -1);
  treeDirty = true;
  renderTree();
  renderForm();
  setStatus("已刪除（記得儲存）");
}

function moveNode(delta) {
  if (selectedPath.length === 0) return;
  const parent = getParent(selectedPath);
  const idx = selectedPath[selectedPath.length - 1];
  const newIdx = idx + delta;
  if (newIdx < 0 || newIdx >= parent.children.length) return;

  [parent.children[idx], parent.children[newIdx]] =
    [parent.children[newIdx], parent.children[idx]];
  selectedPath = [...selectedPath.slice(0, -1), newIdx];
  treeDirty = true;
  renderTree();
  renderForm();
}

async function reload() {
  if (treeDirty || fieldsDirty) {
    if (!confirm("有未儲存的變更，確定重新載入?")) return;
  }
  await loadMenu();
  await loadTemplates();
}
