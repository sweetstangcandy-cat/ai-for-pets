"""照護提醒分級規則（純 Python，不含 UI，方便測試）。

定位：資訊整理與照護提醒工具，不做疾病診斷，不取代獸醫師判斷。
"""
from __future__ import annotations

from dataclasses import dataclass, field

APPETITE_OPTIONS = ["正常", "減少", "完全不吃"]
WATER_OPTIONS = ["正常", "增加", "減少"]
STOOL_OPTIONS = ["正常", "軟便或腹瀉", "便秘或未排便", "血便或黑便"]
ENERGY_OPTIONS = ["活潑", "稍微沒精神", "很嗜睡或無法起身"]
SYMPTOM_OPTIONS = [
    "嘔吐",
    "呼吸急促或困難",
    "抽搐或意識不清",
    "無法排尿",
    "明顯疼痛或躲藏",
    "眼睛或皮膚異常",
]

RED = "red"
YELLOW = "yellow"
GREEN = "green"

# 出現即列為紅燈（建議盡快聯繫獸醫）的症狀
RED_SYMPTOMS = {"呼吸急促或困難", "抽搐或意識不清", "無法排尿"}


@dataclass
class CheckIn:
    appetite: str = "正常"
    water: str = "正常"
    stool: str = "正常"
    energy: str = "活潑"
    symptoms: list[str] = field(default_factory=list)
    missed_doses: int = 0


@dataclass
class TriageResult:
    level: str
    title: str
    reasons: list[str]
    action: str


def triage_checkin(c: CheckIn) -> TriageResult:
    red: list[str] = []
    yellow: list[str] = []

    if c.energy == "很嗜睡或無法起身":
        red.append("精神明顯變差，無法正常起身或活動")
    if c.appetite == "完全不吃":
        red.append("完全不吃東西")
    if c.stool == "血便或黑便":
        red.append("出現血便或黑便")
    for s in c.symptoms:
        if s in RED_SYMPTOMS:
            red.append(f"出現「{s}」")

    if c.appetite == "減少":
        yellow.append("食慾減少")
    if c.water != "正常":
        yellow.append(f"飲水{c.water}")
    if c.stool in ("軟便或腹瀉", "便秘或未排便"):
        yellow.append(f"排便異常：{c.stool}")
    if c.energy == "稍微沒精神":
        yellow.append("精神稍微變差")
    for s in c.symptoms:
        if s not in RED_SYMPTOMS:
            yellow.append(f"出現「{s}」")
    if c.missed_doses > 0:
        yellow.append(f"今日漏服用藥 {c.missed_doses} 次")

    if red:
        return TriageResult(
            RED,
            "🔴 建議盡快聯繫獸醫",
            red,
            "請盡快聯繫獸醫或前往急診評估，不要等到下次回診，也請勿自行用藥。",
        )
    if yellow:
        return TriageResult(
            YELLOW,
            "🟡 建議今天內聯繫獸醫",
            yellow,
            "請持續留意狀況。若情況沒有改善或持續惡化，請儘早就醫。",
        )
    return TriageResult(
        GREEN,
        "🟢 目前狀況穩定",
        [],
        "請依獸醫指示持續照護，並每日記錄，有變化時隨時記錄。",
    )


def build_soap_draft(c: CheckIn, result: TriageResult, vet_exam: str) -> dict[str, str]:
    """產生 SOAP 草稿。A 欄一律標註為規則式參考，不是診斷。"""
    symptom_text = "、".join(c.symptoms) if c.symptoms else "無其他症狀"
    s = (
        f"居家觀察（飼主填寫）：食慾{c.appetite}，飲水{c.water}，排便{c.stool}，"
        f"精神{c.energy}；其他症狀：{symptom_text}。"
    )
    if c.missed_doses:
        s += f" 漏服用藥 {c.missed_doses} 次。"

    o = vet_exam.strip() or "（待獸醫填寫）"
    reasons = "；".join(result.reasons) if result.reasons else "無明顯異常訊號"
    a = f"【AI 規則式分級參考，非診斷】{result.title}。訊號：{reasons}。（最終評估請由獸醫師判斷）"
    p = "（待獸醫填寫）"
    return {"S": s, "O": o, "A": a, "P": p}


def owner_care_plan(c: CheckIn, result: TriageResult) -> list[str]:
    """飼主白話版照護步驟，不含任何飲食調整或用藥變更建議。"""
    steps: list[str] = []
    if result.level == RED:
        steps.append("現在請先聯繫獸醫或前往急診，不要自行用藥或等待觀察。")
    elif result.level == YELLOW:
        steps.append("今天內請聯繫獸醫，詢問是否需要就診。")

    steps.extend(
        [
            "依獸醫指示按時用藥；若漏服，請聯繫診所確認處理方式。",
            "每日記錄食慾、飲水、排便與精神狀態，就診時一併帶給獸醫。",
            "提供安靜、乾淨、溫暖的休息環境，避免過度打擾。",
            "飲食如需調整，請先諮詢獸醫，不要自行更換或增減食物。",
        ]
    )
    if c.water == "增加":
        steps.append("飲水明顯增加時，請記錄大約的飲水量與持續天數，就診時提供給獸醫。")
    if c.missed_doses:
        steps.append("有漏服用藥時，請勿自行補服或加倍，請先聯繫診所確認。")
    return steps
