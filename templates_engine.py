"""
templates_engine — 回覆公版資料層

定位:
    管理「回覆公版」(templates)：admin 預先建立的可重複使用回覆內容範本，
    建立節點時可一鍵套用到節點的「回覆內容」欄位再修改。
    與 menu_engine 完全分離：公版只是 admin 工具，不影響 LINE bot 行為。

資料結構:
    templates.json:
      {
        "templates": [
          { "id": str, "name": str, "description": str, "text": str },
          ...
        ]
      }

包含單元 (units):
    load_templates           讀取整個檔案
    save_templates           覆寫整個檔案（含基本驗證）
    upsert_template          依 id 新增或更新單一公版
    delete_template          依 id 刪除
"""

import json
import re
from pathlib import Path
from typing import Optional


_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def load_templates(file: Path) -> dict:
    """讀取公版檔；不存在時回傳空結構。"""
    if not file.exists():
        return {"templates": []}
    with file.open(encoding="utf-8") as f:
        return json.load(f)


def save_templates(file: Path, data: dict) -> None:
    """覆寫公版檔；驗證每個公版都有合法 id 與 name。"""
    if not isinstance(data, dict) or not isinstance(data.get("templates"), list):
        raise ValueError("公版資料必須是 {templates: [...]} 結構")

    seen_ids = set()
    for i, t in enumerate(data["templates"]):
        if not isinstance(t, dict):
            raise ValueError(f"templates[{i}] 必須是物件")
        tid = t.get("id", "")
        name = t.get("name", "")
        if not tid or not name:
            raise ValueError(f"templates[{i}] 必須含 id 與 name")
        if not _ID_RE.match(tid):
            raise ValueError(f"templates[{i}] 的 id='{tid}' 只能含英數、底線、連字號")
        if tid in seen_ids:
            raise ValueError(f"templates[{i}] 的 id='{tid}' 重複")
        seen_ids.add(tid)

    with file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def upsert_template(file: Path, tpl: dict) -> str:
    """依 id 新增或更新；回傳 'created' 或 'updated'"""
    if not isinstance(tpl, dict):
        raise ValueError("公版必須是物件")
    tid = tpl.get("id", "")
    if not tid or not _ID_RE.match(tid):
        raise ValueError("id 必須是英數/底線/連字號組合")
    if not tpl.get("name"):
        raise ValueError("name 不可為空")

    data = load_templates(file)
    templates = data.get("templates", [])
    for i, t in enumerate(templates):
        if t.get("id") == tid:
            templates[i] = tpl
            data["templates"] = templates
            save_templates(file, data)
            return "updated"

    templates.append(tpl)
    data["templates"] = templates
    save_templates(file, data)
    return "created"


def delete_template(file: Path, tpl_id: str) -> bool:
    """刪除指定 id；回傳是否真的有刪到。"""
    data = load_templates(file)
    before = len(data.get("templates", []))
    data["templates"] = [t for t in data.get("templates", []) if t.get("id") != tpl_id]
    if len(data["templates"]) == before:
        return False
    save_templates(file, data)
    return True
