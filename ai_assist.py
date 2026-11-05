
"""AI 輔助層：問診文字整理與照片外觀描述（可選功能）。

- 未設定 OPENAI_API_KEY 時自動停用，改用規則式檢查，Demo 在任何環境都能跑。
- AI 只能「提高」提醒等級，不能降低 triage.py 的規則結果。
- 不儲存上傳的照片，所有輸出僅供獸醫參考，不構成診斷。
"""
from __future__ import annotations

from dotenv import load_dotenv
from pathlib import Path as _Path
load_dotenv(_Path(__file__).with_name('.env'), override=False)

import base64
import json
import os
from dataclasses import dataclass, field

from triage import GREEN, RED, YELLOW

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png"}
MODEL = os.getenv("AI_ASSIST_MODEL", "gpt-4o-mini")

# 規則式安全關鍵字：即使 AI 未啟用，也會被標記
RED_KEYWORDS = [
    "呼吸困難", "喘不過氣", "抽搐", "昏倒", "不醒", "無法排尿", "尿不出來",
    "血便", "黑便", "大量出血", "誤食", "中毒",
]

SEVERITY = {GREEN: 0, YELLOW: 1, RED: 2}

SYSTEM_TEXT = (
    "你是寵物照護資料整理助手。請把飼主的描述整理成 JSON，欄位如下：\n"
    '{"summary": "150 字內繁體中文摘要，只陳述飼主提到的事實，不做診斷，不建議藥物或劑量", '
    '"red_flags": ["描述中出現、需盡快就醫的徵兆原文，沒有則為空陣列"]}'
)

SYSTEM_IMAGE = (
    "你是寵物照護照片的外觀描述助手。只描述可見的外觀特徵（顏色、質地、範圍、形狀），"
    "不做疾病判定，不提供疾病名稱或用藥建議。請輸出 JSON：\n"
    '{"description": "外觀描述", "urgent_look": true 或 false（外觀看起來需儘快就醫時為 true）, '
    '"reason": "簡短理由"}。若無法判讀，請在 description 說明原因並將 urgent_look 設為 false。'
)


@dataclass
class AIResult:
    enabled: bool
    summary: str
    flags: list[str] = field(default_factory=list)
    level: str | None = None   # 建議提高到的等級；None 表示不調整
    note: str = ""


def ai_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def merge_level(rule_level: str, ai_level: str | None) -> str:
    """取較嚴重的等級，確保 AI 只能提高、不能降低規則結果。"""
    if ai_level and SEVERITY[ai_level] > SEVERITY[rule_level]:
        return ai_level
    return rule_level


def keyword_flags(text: str) -> list[str]:
    return [k for k in RED_KEYWORDS if k in text]


def _client():
    from openai import OpenAI  # 延後匯入，未安裝或未啟用時不影響其他功能

    return OpenAI()


def organize_owner_text(text: str) -> AIResult:
    """把飼主的自由文字整理成摘要，並標記需優先留意的徵兆。"""
    text = (text or "").strip()
    if not text:
        return AIResult(ai_enabled(), "尚未輸入描述。")

    rule_flags = keyword_flags(text)
    if not ai_enabled():
        return AIResult(
            False,
            text,
            rule_flags,
            RED if rule_flags else None,
            "未設定 OPENAI_API_KEY，目前僅顯示原文並以關鍵字檢查。",
        )

    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_TEXT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content)
        summary = str(data.get("summary", "")).strip() or text
        ai_flags = [str(x) for x in data.get("red_flags", [])]
    except Exception as exc:  # 任何 API 錯誤都退回規則式，不讓頁面當掉
        return AIResult(
            True,
            text,
            rule_flags,
            RED if rule_flags else None,
            f"AI 暫時無法使用（{type(exc).__name__}），已改用規則式檢查。",
        )

    flags = sorted(set(rule_flags + ai_flags))
    return AIResult(
        True,
        summary,
        flags,
        RED if flags else None,
        "AI 整理結果僅供獸醫參考，請以原始描述為準。",
    )


def validate_image(data: bytes, mime: str) -> list[str]:
    errors: list[str] = []
    if not data:
        errors.append("檔案是空的")
    if mime not in ALLOWED_MIME:
        errors.append("僅支援 JPG 或 PNG 格式")
    if len(data) > MAX_IMAGE_BYTES:
        errors.append("檔案需小於 5 MB")
    return errors


def describe_photo(data: bytes, mime: str, kind: str) -> AIResult:
    """照片外觀描述。影像只在記憶體中傳送，不寫入磁碟。"""
    errors = validate_image(data, mime)
    if errors:
        return AIResult(ai_enabled(), "；".join(errors))
    if not ai_enabled():
        return AIResult(False, "未啟用影像判讀。請先設定 OPENAI_API_KEY 再試。")

    b64 = base64.b64encode(data).decode("ascii")
    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_IMAGE},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"照片類型：{kind}"},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
        data_json = json.loads(resp.choices[0].message.content)
    except Exception as exc:
        return AIResult(True, "", [], None, f"影像判讀暫時無法使用（{type(exc).__name__}）。")

    urgent = bool(data_json.get("urgent_look"))
    return AIResult(
        True,
        str(data_json.get("description", "")).strip(),
        [],
        YELLOW if urgent else None,
        str(data_json.get("reason", "")).strip()
        or "影像判讀僅描述外觀，不構成診斷，請由獸醫確認。",
    )


# 補充：圖片內容優先於所選類型
SYSTEM_IMAGE += (
    "\n補充規則：先描述圖片中實際可見的內容（顏色、質地、形狀、數量）。"
    "所選類型僅供參考；若圖片內容與類型不符，以圖片為準並明確說明。"
    "只描述外觀，不做疾病判定。"
)
