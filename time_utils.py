"""
time_utils — 時區換算與日期區間計算（utility 層）

定位:
    純函式工具模組，不依賴 Flask / DB / 任何 I/O。
    集中處理「台灣時區 ↔ UTC」轉換與 admin 頁的「8:30 切日」邏輯。

包含單元 (units):
    TW                       台灣時區常數 (UTC+8)
    default_date_range_tw    依目前時間決定 admin 頁面預設的查詢區間
    tw_date_to_utc_iso       台灣日期 (YYYY-MM-DD) → 該日 08:30 對應的 UTC ISO 字串
    utc_iso_to_tw_display    UTC ISO 字串 → 台灣時區的人類可讀格式
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple


TW = timezone(timedelta(hours=8))


def default_date_range_tw(now_tw: datetime = None) -> Tuple[str, str]:
    """
    回傳 (start_date, end_date) 字串 (YYYY-MM-DD, 台灣時區)
    規則: 以 08:30 為一日切點。
      - 現在時間 >= 08:30: end=今天, start=昨天
      - 現在時間 <  08:30: end=昨天, start=前天
    """
    if now_tw is None:
        now_tw = datetime.now(TW)
    cutoff = now_tw.replace(hour=8, minute=30, second=0, microsecond=0)
    if now_tw >= cutoff:
        end = now_tw
        start = now_tw - timedelta(days=1)
    else:
        end = now_tw - timedelta(days=1)
        start = now_tw - timedelta(days=2)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def tw_date_to_utc_iso(date_str: str) -> str:
    """
    將 'YYYY-MM-DD' (視為台灣時區) 那天 08:30 的時間點轉成 UTC ISO 字串
    (供 SQLite 查詢用，例如 '2026-05-05T00:30:00Z')
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TW)
    cutoff = dt.replace(hour=8, minute=30, second=0)
    return cutoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_iso_to_tw_display(iso_str: str) -> str:
    """
    UTC ISO 字串 → '2026-05-05 14:30' (台灣時區，無秒)
    解析失敗時原樣回傳。
    """
    try:
        utc_dt = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        return utc_dt.astimezone(TW).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso_str or ""
