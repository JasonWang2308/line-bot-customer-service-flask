/*
 * editor/state.js — 共用狀態 + editor 專屬小工具
 *
 * 定位:
 *   全域狀態的 single source of truth；其他 editor 模組讀寫這些變數。
 *   純函式 (nodeKind / samePath / pathKey / truncate / findNodeByPath / findPathByLabel)
 *   已抽到 ../menu-utils.js, 由 viewer 與 editor 共用。
 *   本檔只放「依賴 editor 全域狀態」的薄殼。
 *
 * 包含單元 (units):
 *   --- 全域狀態 ---
 *   menuData, selectedPath, fieldsDirty, treeDirty   主編輯狀態
 *   validActions                                      action 清單 cache
 *   templates, selectedTplId, tplDirty                公版頁狀態
 *   collapsedPaths                                    左側列表摺疊狀態
 *
 *   --- 通用工具 ---
 *   $(sel)                  document.querySelector 簡寫
 *   setStatus(msg)          底部狀態列文字
 *
 *   --- 折疊狀態 ---
 *   isCollapsed(path) / setCollapsed(path, bool)
 *
 *   --- 節點工具 (薄殼, 內部呼叫 menu-utils) ---
 *   getNode(path)           findNodeByPath(menuData, path) 的薄殼
 *   getParent(path)         取父節點
 *   kindLabel(kind)         'branch' / 'leaf' / 'empty' → 中文顯示名
 */

let menuData = null;
let selectedPath = [];
let fieldsDirty = false;
let treeDirty = false;
let validActions = {};
let templates = [];
let selectedTplId = null;
let tplDirty = false;
const collapsedPaths = new Set();

const $ = (sel) => document.querySelector(sel);

function setStatus(msg) {
  $("#status").textContent = msg;
}

function isCollapsed(path) {
  return collapsedPaths.has(pathKey(path));
}

function setCollapsed(path, collapsed) {
  const k = pathKey(path);
  if (collapsed) collapsedPaths.add(k);
  else collapsedPaths.delete(k);
}

function getNode(path) {
  return findNodeByPath(menuData, path);
}

function getParent(path) {
  if (path.length === 0) return null;
  return findNodeByPath(menuData, path.slice(0, -1));
}

function kindLabel(kind) {
  return { branch: "分支", leaf: "答覆", empty: "未設定" }[kind] || kind;
}
