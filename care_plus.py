"""照護追蹤、飲食提示與跨日趨勢（純 Python，不含 UI，方便測試）。

原則：不做劑量或熱量計算；飲食相關內容一律標示「需獸醫確認」。
紅燈時不提供任何飲食調整建議，只引導就醫。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from triage import RED, CheckIn, TriageResult

TREND_STREAK_ALERT = 3          # 連續幾筆打卡出現同一異常即提醒
WEIGHT_TREND_THRESHOLD = 0.05   # 首尾體重變化達 5% 即提醒
MISSING_CHECKIN_DAYS = 2        # 連續幾天未打卡即提醒


@dataclass
class VetPlan:
    """獸醫發布時設定的內容，飼主端會讀取這些欄位。"""

    diet: str = ""
    follow_up: date | None = None
    medications: list[str] = field(default_factory=list)


def parse_follow_up(text: str) -> tuple[date | None, str | None]:
    """解析回診日期（YYYY-MM-DD）。空白回傳 (None, None)，格式錯誤回傳錯誤訊息。"""
    text = (text or "").strip()
    if not text:
        return None, None
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, "回診日期格式需為 YYYY-MM-DD，例如 2026-11-15"


def follow_up_message(follow_up: date | None, today: date) -> str | None:
    """回診倒數提醒。"""
    if follow_up is None:
        return None
    days = (follow_up - today).days
    if days > 0:
        return f"距離回診還有 {days} 天（{follow_up.isoformat()}），請提前準備近期打卡紀錄。"
    if days == 0:
        return "今天是回診日，請準時就診，並攜帶打卡紀錄與用藥狀況。"
    return f"回診日已過 {-days} 天，請儘快與診所確認是否需要重新預約。"


def missing_checkin_message(last_date: date | None, today: date) -> str | None:
    """連續未打卡提醒。"""
    if last_date is None:
        return "尚未有打卡紀錄，建議從今天開始每日記錄。"
    gap = (today - last_date).days
    if gap >= MISSING_CHECKIN_DAYS:
        return f"已 {gap} 天未打卡，請補記近況，讓獸醫掌握連續變化。"
    return None


def trailing_streak(checkins: list[CheckIn], predicate: Callable[[CheckIn], bool]) -> int:
    """從最新一筆往回計算，連續符合條件的筆數。"""
    count = 0
    for c in reversed(checkins):
        if not predicate(c):
            break
        count += 1
    return count


def trend_alerts(records: list[tuple[date, CheckIn]]) -> list[str]:
    """跨日趨勢提醒。records 需依日期由舊到新排序。"""
    alerts: list[str] = []
    if not records:
        return alerts

    weighted = [(d, c.weight_kg) for d, c in records if c.weight_kg]
    if len(weighted) >= 2:
        (d0, w0), (d1, w1) = weighted[0], weighted[-1]
        change = (w1 - w0) / w0
        if abs(change) >= WEIGHT_TREND_THRESHOLD:
            direction = "上升" if change > 0 else "下降"
            alerts.append(
                f"{d0:%m/%d} 至 {d1:%m/%d} 體重{direction}約 {abs(change) * 100:.1f}%"
                f"（{w0:.1f} → {w1:.1f} 公斤），請告知獸醫"
            )

    checkins = [c for _, c in records]
    rules: list[tuple[Callable[[CheckIn], bool], str]] = [
        (lambda c: c.appetite in ("減少", "完全不吃"), "食慾減少或不吃"),
        (lambda c: c.water == "增加", "飲水增加"),
        (lambda c: c.water == "減少", "飲水減少"),
        (lambda c: c.stool != "正常", "排便異常"),
        (lambda c: c.energy != "活潑", "精神不如平常"),
    ]
    for predicate, label in rules:
        n = trailing_streak(checkins, predicate)
        if n >= TREND_STREAK_ALERT:
            alerts.append(f"連續 {n} 筆打卡「{label}」，建議今天內聯繫獸醫評估")
    return alerts


def nutrition_notes(
    c: CheckIn,
    result: TriageResult,
    plan: VetPlan | None,
    weight_note: str | None,
) -> list[str]:
    """飲食與營養提示。所有內容皆需獸醫確認，不做熱量或份量計算。"""
    if result.level == RED:
        return ["目前有紅燈訊號，請先聯繫獸醫。飲食暫不調整，也請勿自行改變食物或餵食量。"]

    notes: list[str] = []
    if plan and plan.diet.strip():
        notes.append(f"獸醫目前設定的飲食：{plan.diet.strip()}。請依獸醫指示餵食，不要自行更換。")
    else:
        notes.append("獸醫尚未設定目前飲食，請於下次就診時請獸醫說明飲食內容與餵食方式。")

    if c.appetite != "正常":
        notes.append("食慾改變時，請記錄每餐實際吃掉的大約比例，就診時提供給獸醫參考。")
    if c.water == "增加":
        notes.append("飲水增加時，請記錄每日大約飲水量與持續天數，飲食或飲水相關調整請先與獸醫討論。")
    if c.stool != "正常":
        notes.append("排便異常時，請記錄次數與型態，並請先諮詢獸醫再調整食物。")
    if weight_note:
        notes.append("體重有變化，請獸醫評估目前餵食量與飲食是否需要調整。")

    notes.append("本提示不含熱量或份量計算，所有飲食調整請經獸醫確認。")
    return notes
