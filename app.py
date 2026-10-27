"""毛孩照護閉環 Prototype（2026 法國皇家 AI for Pets 決賽版）

- 所有病患、飼主與病歷資料皆為虛構示範資料。
- 資料只存在本次瀏覽器工作階段，不上傳、不寫入資料庫。
- 角色切換僅供 Demo 展示，不具身份驗證功能。
- 所有分級與建議僅為照護提醒，不構成診斷或治療指示。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from triage import (
    APPETITE_OPTIONS,
    ENERGY_OPTIONS,
    GREEN,
    RED,
    STOOL_OPTIONS,
    SYMPTOM_OPTIONS,
    WATER_OPTIONS,
    YELLOW,
    CheckIn,
    build_soap_draft,
    owner_care_plan,
    triage_checkin,
)

PLACEHOLDER = "請選擇"
REQUIRED_KEYS = ["appetite", "water", "stool", "energy"]
DRAFT_PLACEHOLDER = "（待獸醫填寫）"
DISCLAIMER = (
    "本作品提供之資訊僅供輔助參考，不能取代獸醫師之診斷、治療或專業建議。"
    "貓犬之健康與營養需求可能因個體狀況而異，如有健康疑慮或需要調整飲食與照護方式，請諮詢合格獸醫師。"
)
DEMO_PATIENT = {
    "id": "DEMO-001",
    "name": "小橘（虛構示範）",
    "species": "貓",
    "age": "3 歲（虛構）",
}
LEVEL_LABEL = {RED: "🔴 紅燈", YELLOW: "🟡 黃燈", GREEN: "🟢 綠燈"}

st.set_page_config(page_title="毛孩照護閉環 Prototype", page_icon="🐾", layout="wide")


# ---------- 狀態管理 ----------
def init_state() -> None:
    defaults = {"visit_data": None, "checkins": [], "published_plan": None}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_demo() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(("pre_", "ci_", "soap_")) or key == "vet_input":
            del st.session_state[key]
    st.session_state.visit_data = None
    st.session_state.checkins = []
    st.session_state.published_plan = None


def generate_soap() -> None:
    visit = st.session_state.visit_data
    if visit is None:
        return
    result = triage_checkin(visit)
    draft = build_soap_draft(visit, result, st.session_state.get("vet_input", ""))
    st.session_state["soap_S"] = draft["S"]
    st.session_state["soap_O"] = draft["O"]
    st.session_state["soap_A"] = draft["A"]
    st.session_state["soap_P"] = draft["P"]


def publish_plan() -> None:
    text = st.session_state.get("soap_P", "").strip()
    if text and text != DRAFT_PLACEHOLDER:
        st.session_state.published_plan = {"text": text, "date": date.today().isoformat()}


# ---------- 共用元件 ----------
def pre_completion_rate() -> int:
    filled = sum(
        st.session_state.get(f"pre_{k}", PLACEHOLDER) != PLACEHOLDER for k in REQUIRED_KEYS
    )
    return round(filled / len(REQUIRED_KEYS) * 100)


def collect_core(prefix: str) -> dict:
    col1, col2 = st.columns(2)
    with col1:
        appetite = st.selectbox("食慾＊", [PLACEHOLDER, *APPETITE_OPTIONS], key=f"{prefix}_appetite")
        water = st.selectbox("飲水＊", [PLACEHOLDER, *WATER_OPTIONS], key=f"{prefix}_water")
    with col2:
        stool = st.selectbox("排便＊", [PLACEHOLDER, *STOOL_OPTIONS], key=f"{prefix}_stool")
        energy = st.selectbox("精神狀態＊", [PLACEHOLDER, *ENERGY_OPTIONS], key=f"{prefix}_energy")
    symptoms = st.multiselect("其他症狀（選填）", SYMPTOM_OPTIONS, key=f"{prefix}_symptoms")
    return {
        "appetite": appetite,
        "water": water,
        "stool": stool,
        "energy": energy,
        "symptoms": symptoms,
    }


def is_complete(values: dict) -> bool:
    return all(values[k] != PLACEHOLDER for k in REQUIRED_KEYS)


def to_checkin(values: dict, missed: int = 0) -> CheckIn:
    return CheckIn(
        appetite=values["appetite"],
        water=values["water"],
        stool=values["stool"],
        energy=values["energy"],
        symptoms=list(values["symptoms"]),
        missed_doses=missed,
    )


def show_result(result) -> None:
    if result.level == RED:
        st.error(f"**{result.title}**")
    elif result.level == YELLOW:
        st.warning(f"**{result.title}**")
    else:
        st.success(f"**{result.title}**")
    if result.reasons:
        st.markdown("**觀察到的訊號：**")
        for reason in result.reasons:
            st.markdown(f"- {reason}")
    st.markdown(result.action)


# ---------- 主流程 ----------
init_state()

# 側邊欄
st.sidebar.header("🐾 Demo 控制台")
role = st.sidebar.radio("檢視身份（僅供 Demo 展示）", ["飼主", "獸醫"])
st.sidebar.markdown(
    f"**病患編號**：{DEMO_PATIENT['id']}\n\n"
    f"**寵物**：{DEMO_PATIENT['name']}\n\n"
    f"**物種 / 年齡**：{DEMO_PATIENT['species']} / {DEMO_PATIENT['age']}"
)
today = date.today().isoformat()
st.sidebar.metric("診前必填完成率", f"{pre_completion_rate()}%")
st.sidebar.metric(
    "今日已打卡", "是" if any(e["date"] == today for e in st.session_state.checkins) else "否"
)
st.sidebar.metric("照護計畫已發布", "是" if st.session_state.published_plan else "否")
st.sidebar.button("重置 Demo 資料", on_click=reset_demo)

# 主畫面
st.title("🐾 毛孩照護閉環 Prototype")
st.caption("2026 法國皇家 AI for Pets｜決賽 Prototype｜所有資料皆為虛構示範")
st.warning(DISCLAIMER)

visit = st.session_state.visit_data

if role == "飼主":
    tab_pre, tab_checkin, tab_plan = st.tabs(["① 診前填寫", "② 每日打卡", "③ 照護計畫"])

    with tab_pre:
        st.subheader("診前居家觀察")
        st.caption("就診前填寫，系統會整理成重點摘要給獸醫參考。＊為必填欄位。")
        values = collect_core("pre")
        if st.button("儲存診前紀錄", type="primary", key="pre_save"):
            if is_complete(values):
                st.session_state.visit_data = to_checkin(values)
                st.success("已儲存，獸醫可於「診前摘要」查看。")
            else:
                st.warning("請先完成四項必填欄位（＊）。")
        if st.session_state.visit_data is not None:
            st.markdown("#### 系統初步提醒")
            show_result(triage_checkin(st.session_state.visit_data))

    with tab_checkin:
        st.subheader("每日照護打卡")
        st.caption("僅記錄飼主的人工觀察，本版不使用影像、聲音或定位資料。")
        values = collect_core("ci")
        missed = st.number_input(
            "今日漏服用藥次數", min_value=0, max_value=10, value=0, key="ci_missed"
        )
        if st.button("送出今日打卡", type="primary", key="ci_submit"):
            if is_complete(values):
                checkin = to_checkin(values, int(missed))
                result = triage_checkin(checkin)
                st.session_state.checkins.insert(
                    0, {"date": date.today().isoformat(), "checkin": checkin, "result": result}
                )
                show_result(result)
            else:
                st.warning("請先完成四項必填欄位（＊）。")
        if st.session_state.checkins:
            st.markdown("#### 打卡紀錄")
            rows = [
                {
                    "日期": e["date"],
                    "燈號": LEVEL_LABEL[e["result"].level],
                    "摘要": "；".join(e["result"].reasons) or "無異常",
                }
                for e in st.session_state.checkins
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True)

    with tab_plan:
        st.subheader("照護計畫（白話版）")
        latest = (
            st.session_state.checkins[0]["checkin"]
            if st.session_state.checkins
            else st.session_state.visit_data
        )
        if latest is None:
            st.info("尚無紀錄，請先完成診前填寫或每日打卡。")
        else:
            result = triage_checkin(latest)
            show_result(result)
            st.markdown("#### 建議的照護步驟")
            for step in owner_care_plan(latest, result):
                st.markdown(f"- {step}")
        if st.session_state.published_plan:
            st.markdown("#### 獸醫發布的計畫")
            st.info(st.session_state.published_plan["text"])
            st.caption(f"發布日期：{st.session_state.published_plan['date']}")
        else:
            st.caption("獸醫尚未發布病歷與照護計畫。")

else:
    tab_summary, tab_draft, tab_alert = st.tabs(["① 診前摘要", "② 病歷草稿", "③ 異常警示"])

    with tab_summary:
        st.subheader("診前摘要")
        if visit is None:
            st.info("飼主尚未提交診前紀錄。")
        else:
            items = [
                ("食慾", visit.appetite),
                ("飲水", visit.water),
                ("排便", visit.stool),
                ("精神狀態", visit.energy),
                ("其他症狀", "、".join(visit.symptoms) or "無"),
            ]
            st.dataframe(
                pd.DataFrame([{"項目": a, "飼主回報": b} for a, b in items]), hide_index=True
            )
            show_result(triage_checkin(visit))
            st.caption("摘要為規則式整理，最終判斷請由獸醫師決定。")

    with tab_draft:
        st.subheader("病歷草稿（需獸醫確認）")
        if visit is None:
            st.info("需先有飼主的診前紀錄，才能產生 SOAP 草稿。")
        st.text_area("獸醫檢查紀錄（O 的來源）", key="vet_input", height=120,
                     placeholder="例：體重、觸診、檢查結果…")
        st.button("產生 SOAP 草稿", on_click=generate_soap, key="soap_generate")
        st.text_area("S 主觀資料", key="soap_S", height=100)
        st.text_area("O 客觀資料", key="soap_O", height=100)
        st.text_area("A 評估（AI 分級僅供參考，需獸醫確認）", key="soap_A", height=100)
        st.text_area("P 計畫（發布後飼主可見白話版）", key="soap_P", height=120)
        st.button("發布照護計畫給飼主", on_click=publish_plan, type="primary", key="soap_publish")
        if st.session_state.published_plan:
            st.success("已發布，飼主可於「照護計畫」查看。")

    with tab_alert:
        st.subheader("異常警示")
        alerts = []
        if visit is not None:
            r = triage_checkin(visit)
            if r.level != GREEN:
                alerts.append(("診前填寫", r))
        for e in st.session_state.checkins:
            if e["result"].level != GREEN:
                alerts.append((f"{e['date']} 打卡", e["result"]))

        if not alerts:
            st.success("目前沒有需要處理的異常訊號。")
        for label, r in sorted(alerts, key=lambda x: x[1].level != RED):
            if r.level == RED:
                st.error(f"**{label}**：{r.title}")
            else:
                st.warning(f"**{label}**：{r.title}")
            for reason in r.reasons:
                st.markdown(f"- {reason}")
        st.caption("警示為規則式提醒，不代表診斷結果。")

st.divider()
with st.expander("資料與安全說明（Prototype）"):
    st.markdown(
        """
- 所有病患、飼主與病歷資料皆為**虛構示範**，請勿輸入真實個人或寵物資料。
- 資料只保存在本次瀏覽器工作階段，重新整理即清空，不會上傳或寫入資料庫。
- 本版不上傳寵物影像、聲音或定位資料。
- 角色切換僅供 Demo 展示，正式版將以登入與權限控管取代。
- 所有分級結果為照護提醒，不構成診斷或治療指示。
"""
    )
