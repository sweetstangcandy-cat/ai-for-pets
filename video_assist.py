"""短影片外觀判讀：抽取數個畫面，逐張交給 describe_photo 判讀。

- 影片只暫存於系統暫存資料夾，處理完成後立即刪除。
- 輸出仍只描述外觀，不做疾病判定。
"""
from __future__ import annotations

import os
import tempfile

import cv2

from ai_assist import AIResult, ai_enabled, describe_photo
from triage import RED, YELLOW

MAX_VIDEO_BYTES = 20 * 1024 * 1024
MAX_SECONDS = 30
FRAMES_TO_SAMPLE = 4
ALLOWED_VIDEO = {"video/mp4", "video/quicktime"}
SUFFIX = {"video/mp4": ".mp4", "video/quicktime": ".mov"}


def validate_video(data: bytes, mime: str) -> list[str]:
    errors: list[str] = []
    if not data:
        errors.append("檔案是空的")
    if mime not in ALLOWED_VIDEO:
        errors.append("影片僅支援 MP4 或 MOV 格式")
    if len(data) > MAX_VIDEO_BYTES:
        errors.append("影片需小於 20 MB")
    return errors


def extract_frames(data: bytes, suffix: str = ".mp4", n: int = FRAMES_TO_SAMPLE) -> list[bytes]:
    """從影片平均抽取 n 個畫面，回傳 JPEG 位元組。無法讀取時回傳空清單。"""
    fd, path = tempfile.mkstemp(suffix=suffix)
    cap = None
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        if total <= 0 or fps <= 0:
            return []
        if total / fps > MAX_SECONDS:
            raise ValueError(f"影片長度需在 {MAX_SECONDS} 秒以內")
        frames: list[bytes] = []
        for i in range(n):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int((i + 0.5) * total / n))
            ok, frame = cap.read()
            if ok:
                ok_enc, buf = cv2.imencode(".jpg", frame)
                if ok_enc:
                    frames.append(buf.tobytes())
        return frames
    finally:
        if cap is not None:
            cap.release()
        os.remove(path)


def describe_video(data: bytes, mime: str, kind: str) -> AIResult:
    errors = validate_video(data, mime)
    if errors:
        return AIResult(ai_enabled(), "；".join(errors))
    if not ai_enabled():
        return AIResult(False, "未啟用影像判讀。請先設定 OPENAI_API_KEY 再試。")

    try:
        frames = extract_frames(data, SUFFIX[mime])
    except ValueError as exc:
        return AIResult(True, str(exc))
    if not frames:
        return AIResult(True, "無法讀取此影片，請確認格式或改用較短的檔案。")

    results = [describe_photo(fr, "image/jpeg", kind) for fr in frames]
    lines = [f"畫面 {i + 1}：{r.summary}" for i, r in enumerate(results) if r.summary]
    levels = [r.level for r in results]
    level = RED if RED in levels else YELLOW if YELLOW in levels else None
    notes = sorted({r.note for r in results if r.note})
    return AIResult(
        True,
        "\n\n".join(lines) or "（無結果）",
        [],
        level,
        "；".join(notes) or "影像判讀僅描述外觀，不構成診斷，請由獸醫確認。",
    )
