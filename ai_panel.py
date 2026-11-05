"""把 AI 功能嵌入主流程的 UI 元件（飼主端與獸醫端共用）。"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import date

import streamlit as st

from ai_assist import organize_owner_text
from cf_vision import describe_image, describe_video as describe_video_file, summarize_text
from triage import RED, YELLOW

PHOTO_KINDS = ["嘔吐物", "糞便", "皮膚或傷口", "眼睛或耳朵", "口腔或牙齦", "其他"]
MAX_VIDEO_MB = 20
AI_NOTE = "AI 判讀僅供參考，只描述外觀，不做疾病診斷。"


@dataclass
class AIResult:
    summary: str | None = None
    flags: list[str] = field(default_factory=list)
    note: str = ""
    level: str | None = None


def owner_note() -> str | None:
    """取得已儲存的診前 AI 摘要，供 SOAP 草稿使用。"""
    r = st.session_state.get("pre_saved_ai_result")
    return r.summary if r and r.summary else None


def _organize_text(text: str) -> AIResult:
    """規則式旗標（安全優先）＋ Cloudflare 摘要；AI 失敗時退回規則式摘要。"""
    rule = organize_owner_text(text)
    flags = list(getattr(rule, "flags", []) or [])
    try:
        summary = summarize_text(text)
        note = AI_NOTE
    except Exception as e:
        summary = getattr(rule, "summary", "") or "（無法整理）"
        note = f"AI 暫時無法使用，已改用規則式整理（{type(e).__name__}）。"
    return AIResult(summary=summary, flags=flags, note=note)


def _describe_photo_bytes(data: bytes, kind: str) -> AIResult:
    try:
        text = describe_image(data, kind)
        return AIResult(summary=text, note=AI_NOTE)
    except Exception as e:
        return AIResult(summary="判讀暫時失敗，請稍後再試。", note=f"錯誤：{e}")


def _describe_video_bytes(data: bytes, name: str, kind: str) -> AIResult:
    suffix = os.path.splitext(name)[1].lower() or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        text = describe_video_file(path, kind)
        return AIResult(summary=text, note=AI_NOTE + "（影片抽取數個畫面分析）")
    except Exception as e:
        return AIResult(summary="影片判讀暫時失敗，請稍後再試。", note=f"錯誤：{e}")
    finally:
        try:
            os.remove(path)  # 分析完即刪除暫存影片
        except OSError:
            pass


def render_owner_text_ai(prefix: str) -> None:
    with st.expander("🤖 AI 協助整理近況描述（選填）", expanded=False):
        st.caption("用自己的話描述近況，AI 會整理成摘要，並附在給獸醫的紀錄中。")
        st.text_area(
            "近況描述",
            key=f"{prefix}_ai_text",
            height=120,
            placeholder="例：昨晚開始一直嘔吐兩次，今天早上不太想吃飯，但還有喝水…",
        )
        if st.button("整理描述", key=f"{prefix}_ai_btn"):
            text = st.session_state.get(f"{prefix}_ai_text", "")
            if not text.strip():
                st.warning("請先輸入描述。")
            else:
                with st.spinner("整理中…"):
                    st.session_state[f"{prefix}_ai_result"] = _organize_text(text)
        r = st.session_state.get(f"{prefix}_ai_result")
        if r is not None:
            if r.flags:
                st.error("偵測到需優先留意的描述：" + "、".join(r.flags))
            st.markdown("**整理摘要**")
            st.write(r.summary)
            st.caption(r.note)


def _show_photo_result(n: dict) -> None:
    r = n["result"]
    st.markdown(f"**{n['date']}｜{n['kind']}**")
    media = n.get("media")
    if media:
        if n.get("is_video"):
            fmt = "video/quicktime" if n.get("name", "").lower().endswith(".mov") else "video/mp4"
            st.video(media, format=fmt)
        else:
            st.image(media, width=280)
    if r.level == RED:
        st.error("外觀描述提示：建議盡快聯繫獸醫")
    elif r.level == YELLOW:
        st.warning("外觀描述提示：建議今天內聯繫獸醫")
    st.write(r.summary or "（無結果）")
    st.caption(r.note)


def render_photo_ai(prefix: str) -> None:
    with st.expander("📷 AI 影像外觀描述（選填，支援照片或短影片）", expanded=False):
        st.caption(
            "只描述可見外觀，不做疾病判定。影像會傳送至 Cloudflare Workers AI 判讀；"
            "原始檔案暫存於本次 Demo 工作階段，重置即清除。影片最長 30 秒、20 MB 以內。"
            "正式版需取得飼主同意並加密儲存。"
        )
        kind = st.selectbox("類型", PHOTO_KINDS, key=f"{prefix}_photo_kind")
        f = st.file_uploader(
            "上傳照片（JPG、PNG）或短影片（MP4、MOV）",
            type=["jpg", "jpeg", "png", "mp4", "mov"],
            key=f"{prefix}_photo",
        )
        if f is not None:
            is_video = f.name.lower().endswith((".mp4", ".mov"))
            data = f.getvalue()
            if is_video:
                st.video(data)
            else:
                st.image(data, width=280)
            if st.button("判讀外觀", key=f"{prefix}_photo_btn"):
                if is_video and len(data) > MAX_VIDEO_MB * 1024 * 1024:
                    st.error(f"影片超過 {MAX_VIDEO_MB} MB，請壓縮後再上傳。")
                else:
                    with st.spinner("判讀中，影片會抽取數個畫面分析…"):
                        if is_video:
                            r = _describe_video_bytes(data, f.name, kind)
                        else:
                            r = _describe_photo_bytes(data, kind)
                    notes = st.session_state.setdefault(f"{prefix}_photo_notes", [])
                    notes.insert(0, {
                        "date": date.today().isoformat(),
                        "kind": kind,
                        "result": r,
                        "media": data,
                        "is_video": is_video,
                        "name": f.name,
                    })
        for n in st.session_state.get(f"{prefix}_photo_notes", [])[:3]:
            _show_photo_result(n)


def render_vet_ai_summary() -> None:
    st.markdown("#### 診前｜AI 整理的飼主描述")
    r = st.session_state.get("pre_saved_ai_result")
    if r is None:
        st.caption("此診前紀錄沒有已儲存的 AI 文字摘要。")
    else:
        if r.flags:
            st.error("需優先留意：" + "、".join(r.flags))
        st.info(r.summary or "（無摘要）")

    st.markdown("#### 診前｜照片與影片外觀描述")
    photos = st.session_state.get("pre_saved_photo_notes", [])
    if not photos:
        st.caption("此診前紀錄沒有已綁定的影像。")
    for photo in photos:
        _show_photo_result(photo)
