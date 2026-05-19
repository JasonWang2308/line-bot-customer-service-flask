"""
menu_engine — 選單樹狀資料的核心邏輯模組（資料層）

定位:
    系統的 data layer。所有對 menu.json 的讀、寫、查詢、比對都集中在這支模組，
    不耦合 Flask / LINE bot / 任何 I/O 介面。

包含單元 (units):
    load_menu / save_menu        從/到檔案
    get_node                     依路徑取節點
    find_path_by_label           依 label 搜尋路徑
    node_kind                    branch / leaf / empty
    breadcrumb                   路徑 → label 序列
    valid_actions                目前合法 action 清單

資料結構:
    每個節點:
      label (str, 必填)
      branch: children (list[node]), description (str, optional)
      leaf:   text (str)
      empty:  只有 label
      任何節點可選 action (str): 觸發特殊行為，值必須在 VALID_ACTIONS 內

設計原則:
    - label 只是顯示文字，admin 改名不影響程式
    - 程式行為由 action 欄位決定
    - LINE bot 走到帶 action 的節點時，跑 ACTION_HANDLERS 取代預設渲染
"""

import json
from pathlib import Path
from typing import Optional


# 加新 action 時:
#   1. 在這裡登記 (action_id, 顯示名稱)
#   2. 在 line_bot.ACTION_HANDLERS 補一個 handler
#   3. 若該 action 需要額外欄位（例如 call_phone 需要 phone），
#      在 _validate_actions 加對應的必填檢查
VALID_ACTIONS = {
    "collect_message": "收集留言（轉真人客服）",
    "call_phone":      "撥打電話",
}


def valid_actions() -> dict:
    """給 /api/actions 與編輯器下拉用"""
    return dict(VALID_ACTIONS)


def load_menu(menu_file: Path) -> dict:
    with menu_file.open(encoding="utf-8") as f:
        return json.load(f)


def save_menu(menu_file: Path, data: dict) -> None:
    """寫入前先驗證所有節點 action 合法；非法時拋 ValueError"""
    _validate_actions(data)
    with menu_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _validate_actions(node: dict, path: Optional[list] = None) -> None:
    path = path or []
    action = node.get("action")
    if action is not None:
        loc = "/".join(str(p) for p in path) or "(root)"
        if action not in VALID_ACTIONS:
            valid_list = list(VALID_ACTIONS.keys())
            raise ValueError(
                f"節點 [{loc}] 的 action='{action}' 不在合法清單 {valid_list} 內"
            )
        # call_phone 必須附帶非空 phone 欄位
        if action == "call_phone":
            phone = node.get("phone")
            if not isinstance(phone, str) or not phone.strip():
                raise ValueError(
                    f"節點 [{loc}] 的 action='call_phone' 必須有非空的 phone 欄位"
                )
    for i, child in enumerate(node.get("children") or []):
        _validate_actions(child, path + [i])


def get_node(data: dict, path: list) -> Optional[dict]:
    node = data
    for idx in path:
        children = node.get("children")
        if not isinstance(children, list) or not (0 <= idx < len(children)):
            return None
        node = children[idx]
    return node


def find_path_by_label(data: dict, label: str) -> Optional[list]:
    target = (label or "").strip()
    if not target:
        return None

    def _search(node: dict, path: list) -> Optional[list]:
        if node.get("label") == target:
            return path
        for i, child in enumerate(node.get("children") or []):
            found = _search(child, path + [i])
            if found is not None:
                return found
        return None

    return _search(data, [])


def node_kind(node: dict) -> str:
    children = node.get("children")
    if isinstance(children, list) and len(children) > 0:
        return "branch"
    if "text" in node:
        return "leaf"
    return "empty"


def breadcrumb(data: dict, path: list) -> list:
    labels = [data.get("label", "")]
    node = data
    for idx in path:
        node = node["children"][idx]
        labels.append(node.get("label", ""))
    return labels
