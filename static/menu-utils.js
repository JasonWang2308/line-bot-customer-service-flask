/*
 * static/menu-utils.js — 跨頁共用的選單樹工具
 *
 * 定位:
 *   把 viewer 與 editor 都會用到的純函式集中。所有函式 stateless，
 *   menuData 由呼叫端傳入；不依賴任何全域狀態，可獨立 unit test。
 *
 * 行為對齊 (與 menu_engine.py 相同邏輯):
 *   findNodeByPath  ↔  menu_engine.get_node
 *   findPathByLabel ↔  menu_engine.find_path_by_label
 *   nodeKind        ↔  menu_engine.node_kind
 *
 * 包含單元 (units):
 *   findNodeByPath(menu, path)    依路徑取節點 (路徑無效回 null)
 *   findPathByLabel(menu, label)  全棵樹搜尋 label 完全相符的節點路徑
 *   nodeKind(node)                'branch' | 'leaf' | 'empty'
 *   samePath(a, b)                兩個路徑陣列是否相同
 *   pathKey(path)                 路徑 → 字串 key (給 Set/Map 用)
 *   truncate(s, n)                字串截斷
 */

function findNodeByPath(menu, path) {
  let node = menu;
  for (const idx of path) {
    if (!node || !node.children || idx < 0 || idx >= node.children.length) return null;
    node = node.children[idx];
  }
  return node;
}

function findPathByLabel(menu, label) {
  const target = (label || "").trim();
  if (!target) return null;

  function _search(node, path) {
    if (node.label === target) return path;
    if (Array.isArray(node.children)) {
      for (let i = 0; i < node.children.length; i++) {
        const found = _search(node.children[i], [...path, i]);
        if (found) return found;
      }
    }
    return null;
  }
  return _search(menu, []);
}

function nodeKind(node) {
  if (Array.isArray(node.children) && node.children.length > 0) return "branch";
  if ("text" in node) return "leaf";
  return "empty";
}

function samePath(a, b) {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function pathKey(path) {
  return path.join("/");
}

function truncate(s, n) {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}
