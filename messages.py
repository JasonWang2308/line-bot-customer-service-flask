"""
messages — 留言查詢服務（service 層）

定位:
    位於 route ↔ db 中介，將「查詢留言 + 過濾日期 + 計算統計 + 補時區欄位」
    這些業務邏輯從 admin route 抽出，讓 route 變成薄殼。

依賴:
    db.get_messages              SQLite 查詢
    time_utils                   時區換算 / 預設日期區間

包含單元 (units):
    list_with_stats              查詢 + 補欄位 + 算統計，回傳 dict 給 template 用
"""

from typing import Optional

import db
from time_utils import (
    default_date_range_tw,
    tw_date_to_utc_iso,
    utc_iso_to_tw_display,
)


def list_with_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    查詢指定日期區間的留言並計算統計。

    參數:
        start_date / end_date: 'YYYY-MM-DD' (台灣時區), None 走 default_date_range_tw 的預設

    回傳: dict, 直接 ** 進 template:
        messages         list[dict]   原始 + 多了 created_at_tw 欄位
        q_start          str          查詢用的開始日期（回填表單）
        q_end            str          查詢用的結束日期（回填表單）
        pending_count    int
        handled_count    int
        total_count      int
    """
    default_start, default_end = default_date_range_tw()
    q_start = start_date or default_start
    q_end = end_date or default_end

    start_utc = tw_date_to_utc_iso(q_start)
    end_utc = tw_date_to_utc_iso(q_end)

    rows = db.get_messages(start=start_utc, end=end_utc)

    pending = 0
    handled = 0
    for m in rows:
        if m.get("handled"):
            handled += 1
        else:
            pending += 1
        m["created_at_tw"] = utc_iso_to_tw_display(m.get("created_at", ""))

    return {
        "messages":      rows,
        "q_start":       q_start,
        "q_end":         q_end,
        "pending_count": pending,
        "handled_count": handled,
        "total_count":   len(rows),
    }
