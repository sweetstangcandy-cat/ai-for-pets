"""毛孩智慧照護（2026 法國皇家 AI for Pets 決賽版）

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
    SPECIES_OPTIONS,
    STOOL_OPTIONS,
    SYMPTOM_OPTIONS,
    WATER_OPTIONS,
    YELLOW,
    CheckIn,
    build_soap_draft,
    owner_care_plan,
    triage_checkin,
    validate_profile,
)

from ai_panel import (
    owner_note,
    render_owner_text_ai,
    render_photo_ai,
    render_vet_ai_summary,
)

PLACEHOLDER = "請選擇"
CORE_KEYS = ["appetite", "water", "stool", "energy"]
DRAFT_PLACEHOLDER = "（待獸醫填寫）"
DISCLAIMER = (
    "本作品提供之資訊僅供輔助參考，不能取代獸醫師之診斷、治療或專業建議。"
    "貓犬之健康與營養需求可能因個體狀況而異，如有健康疑慮或需要調整飲食與照護方式，請諮詢合格獸醫師。"
)
DEMO_PATIENT = {"id": "DEMO-001", "name": "小橘（虛構示範）"}
LEVEL_LABEL = {RED: "🔴 紅燈", YELLOW: "🟡 黃燈", GREEN: "🟢 綠燈"}

st.set_page_config(page_title="毛孩智慧照護", page_icon="🐾", layout="wide")


# ---------- 狀態管理 ----------
def init_state() -> None:
    defaults = {"visit_data": None, "checkins": [], "published_plan": None}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # 舊版照片沒有綁定具體的提交紀錄。
    # 保留並標示來源，但不猜測屬於哪一次提交。
    if not st.session_state.get("_record_split_migrated", False):
        st.session_state["_legacy_pre_photos"] = list(
            st.session_state.get("pre_photo_notes", [])
        )
        st.session_state["_legacy_ci_photos"] = list(
            st.session_state.get("ci_photo_notes", [])
        )
        st.session_state["pre_photo_notes"] = []
        st.session_state["ci_photo_notes"] = []
        st.session_state["_record_split_migrated"] = True


def reset_demo() -> None:
    for key in list(st.session_state.keys()):
        if (
            key.startswith(("pre_", "ci_", "soap_", "_legacy_"))
            or key in ("vet_input", "_record_split_migrated")
        ):
            del st.session_state[key]
    st.session_state.visit_data = None
    st.session_state.checkins = []
    st.session_state.published_plan = None


def generate_soap() -> None:
    visit = st.session_state.visit_data
    if visit is None:
        return

    result = triage_checkin(visit)
    vet_exam = st.session_state.get("vet_input", "")
    draft = build_soap_draft(visit, result, vet_exam)

    note = owner_note()
    if note:
        draft["S"] += f" 飼主補充描述（AI 整理，需獸醫確認）：{note}"

    # 保留規則式分級，AI 只新增供獸醫確認的草稿。
    try:
        from cf_vision import generate_vet_assessment

        ai_assessment = generate_vet_assessment(
            subjective=draft["S"],
            objective=vet_exam,
            rule_assessment=draft["A"],
        )
        draft["A"] += (
            "\\n\\n【AI 初步鑑別草稿，非診斷，需獸醫確認】\\n"
            + ai_assessment
        )
    except Exception:
        draft["A"] += (
            "\\n\\n【AI 初步鑑別草稿】暫時無法產生，"
            "請由獸醫自行評估；以上規則式分級仍供參考。"
        )

    st.session_state["soap_S"] = draft["S"]
    st.session_state["soap_O"] = draft["O"]
    st.session_state["soap_A"] = draft["A"]
    st.session_state["soap_P"] = draft["P"]


def publish_plan() -> None:
    text = st.session_state.get("soap_P", "").strip()
    if text and text != DRAFT_PLACEHOLDER:
        st.session_state.published_plan = {"text": text, "date": date.today().isoformat()}


def latest_weight() -> float | None:
    """取得最近一次的體重：優先打卡紀錄，其次為診前紀錄。"""
    for entry in st.session_state.checkins:
        if entry["checkin"].weight_kg:
            return entry["checkin"].weight_kg
    visit = st.session_state.visit_data
    if visit is not None and visit.weight_kg:
        return visit.weight_kg
    return None


# ---------- 共用元件 ----------
def pre_completion_rate() -> int:
    total = len(CORE_KEYS) + 2  # 四項居家觀察 + 年齡 + 體重
    filled = sum(
        st.session_state.get(f"pre_{k}", PLACEHOLDER) != PLACEHOLDER for k in CORE_KEYS
    )
    filled += int(bool(st.session_state.get("pre_age", 0.0)))
    filled += int(bool(st.session_state.get("pre_weight", 0.0)))
    return round(filled / total * 100)


def collect_profile() -> dict:
    col1, col2, col3 = st.columns(3)
    with col1:
        species = st.selectbox("物種＊", SPECIES_OPTIONS, key="pre_species")
    with col2:
        age = st.number_input(
            "年齡（歲）＊", min_value=0.0, max_value=40.0, value=0.0, step=0.5, key="pre_age"
        )
    with col3:
        weight = st.number_input(
            "體重（公斤）＊",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=0.1,
            format="%.1f",
            key="pre_weight",
        )
    return {
        "species": species,
        "age": float(age) or None,
        "weight": float(weight) or None,
    }


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


def is_complete(core: dict) -> bool:
    return all(core[k] != PLACEHOLDER for k in CORE_KEYS)


def to_checkin(
    core: dict,
    *,
    missed: int = 0,
    weight: float | None = None,
    previous_weight: float | None = None,
    species: str = "貓",
    age: float | None = None,
) -> CheckIn:
    return CheckIn(
        appetite=core["appetite"],
        water=core["water"],
        stool=core["stool"],
        energy=core["energy"],
        symptoms=list(core["symptoms"]),
        missed_doses=missed,
        species=species,
        age_years=age,
        weight_kg=weight,
        previous_weight_kg=previous_weight,
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
    "基本資料由診前表單填寫。"
)
today = date.today().isoformat()
st.sidebar.metric("診前必填完成率", f"{pre_completion_rate()}%")
st.sidebar.metric(
    "今日已打卡", "是" if any(e["date"] == today for e in st.session_state.checkins) else "否"
)
st.sidebar.metric("照護計畫已發布", "是" if st.session_state.published_plan else "否")
st.sidebar.button("重置 Demo 資料", on_click=reset_demo)

# 主畫面
st.title("🐾 毛孩智慧照護")
st.caption("2026 法國皇家 AI for Pets｜決賽 Prototype｜所有資料皆為虛構示範")
st.warning(DISCLAIMER)

visit = st.session_state.visit_data

if role == "飼主":
    tab_pre, tab_checkin, tab_plan = st.tabs(["① 診前填寫", "② 每日打卡", "③ 照護計畫"])

    with tab_pre:
        st.subheader("診前居家觀察")
        st.caption("就診前填寫，系統會整理成重點摘要給獸醫參考。＊為必填欄位。")
        st.markdown("#### 寵物基本資料")
        profile = collect_profile()
        st.markdown("#### 居家觀察")
        core = collect_core("pre")
        render_owner_text_ai("pre")
        render_photo_ai("pre")
        if st.button("儲存診前紀錄", type="primary", key="pre_save"):
            errors = validate_profile(profile["weight"], profile["age"])
            if not (profile["age"] and profile["weight"]):
                st.warning("請先填寫年齡與體重。")
            elif not is_complete(core):
                st.warning("請先完成四項居家觀察的必填欄位（＊）。")
            elif errors:
                for err in errors:
                    st.error(err)
            else:
                st.session_state.visit_data = to_checkin(
                    core,
                    weight=profile["weight"],
                    species=profile["species"],
                    age=profile["age"],
                )
                pending_photos = list(
                    st.session_state.get("pre_photo_notes", [])
                )
                saved_photos = list(
                    st.session_state.get("pre_saved_photo_notes", [])
                )
                st.session_state["pre_saved_photo_notes"] = (
                    pending_photos + saved_photos
                )
                st.session_state["pre_photo_notes"] = []
                st.session_state["pre_saved_ai_result"] = (
                    st.session_state.get("pre_ai_result")
                )
                st.session_state["pre_saved_date"] = date.today().isoformat()
                st.success("已儲存，獸醫可於「診前摘要」查看。")
        if st.session_state.visit_data is not None:
            st.markdown("#### 系統初步提醒")
            show_result(triage_checkin(st.session_state.visit_data))

    with tab_checkin:
        st.subheader("每日照護打卡")
        st.caption("記錄飼主的人工觀察與體重（選填）。本版不記錄聲音或定位資料；影像判讀請使用下方 AI 區塊。")
        core = collect_core("ci")
        weight_now = st.number_input(
            "今日體重（公斤，選填，0 表示未量測）",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=0.1,
            format="%.1f",
            key="ci_weight",
        )
        missed = st.number_input(
            "今日漏服用藥次數", min_value=0, max_value=10, value=0, key="ci_missed"
        )
        render_photo_ai("ci")
        if st.button("送出今日打卡", type="primary", key="ci_submit"):
            if not is_complete(core):
                st.warning("請先完成四項必填欄位（＊）。")
            else:
                weight = float(weight_now) or None
                errors = validate_profile(weight, None)
                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    base = st.session_state.visit_data
                    checkin = to_checkin(
                        core,
                        missed=int(missed),
                        weight=weight,
                        previous_weight=latest_weight(),
                        species=base.species if base else "貓",
                        age=base.age_years if base else None,
                    )
                    result = triage_checkin(checkin)
                    pending_photos = list(
                        st.session_state.get("ci_photo_notes", [])
                    )
                    st.session_state.checkins.insert(
                        0,
                        {
                            "date": date.today().isoformat(),
                            "checkin": checkin,
                            "result": result,
                            "photos": pending_photos,
                        },
                    )
                    st.session_state["ci_photo_notes"] = []
                    show_result(result)
        if st.session_state.checkins:
            st.markdown("#### 打卡紀錄")
            rows = [
                {
                    "日期": e["date"],
                    "燈號": LEVEL_LABEL[e["result"].level],
                    "體重（公斤）": f"{e['checkin'].weight_kg:.1f}" if e["checkin"].weight_kg else "未量測",
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
        from ai_panel import _show_photo_result

        st.subheader("① 診前紀錄")
        if visit is None:
            st.info("飼主尚未提交診前紀錄。")
        else:
            saved_date = st.session_state.get("pre_saved_date")
            if saved_date:
                st.caption(f"診前紀錄儲存日期：{saved_date}")
            else:
                st.caption("舊版診前紀錄：儲存日期未記錄。")

            items = [
                ("物種", visit.species),
                (
                    "年齡",
                    f"{visit.age_years:g} 歲"
                    if visit.age_years is not None else "未填",
                ),
                (
                    "體重",
                    f"{visit.weight_kg:g} 公斤"
                    if visit.weight_kg is not None else "未填",
                ),
                ("食慾", visit.appetite),
                ("飲水", visit.water),
                ("排便", visit.stool),
                ("精神狀態", visit.energy),
                ("其他症狀", "、".join(visit.symptoms) or "未填"),
            ]
            st.dataframe(
                pd.DataFrame(items, columns=["項目", "飼主回報"]),
                hide_index=True,
            )
            show_result(triage_checkin(visit))
            render_vet_ai_summary()

        st.divider()
        st.subheader("② 每日打卡紀錄")
        st.caption(
            "每次送出打卡都是獨立紀錄；影像只顯示該次送出時綁定的內容。"
        )

        checkins = st.session_state.checkins
        if not checkins:
            st.info("目前沒有每日打卡紀錄。")

        for index, entry in enumerate(checkins):
            c = entry["checkin"]
            result = entry["result"]
            label = (
                f"{entry['date']}｜{LEVEL_LABEL.get(result.level, result.level)}"
                f"｜第 {len(checkins) - index} 筆打卡"
            )

            with st.expander(label, expanded=(index == 0)):
                checkin_items = [
                    (
                        "體重",
                        f"{c.weight_kg:g} 公斤"
                        if c.weight_kg is not None else "未量測",
                    ),
                    ("食慾", c.appetite),
                    ("飲水", c.water),
                    ("排便", c.stool),
                    ("精神狀態", c.energy),
                    ("其他症狀", "、".join(c.symptoms) or "未填"),
                    ("漏服用藥次數", str(c.missed_doses)),
                ]
                st.dataframe(
                    pd.DataFrame(checkin_items, columns=["項目", "飼主回報"]),
                    hide_index=True,
                )
                show_result(result)

                st.markdown("#### 此次打卡｜照片與影片")
                if "photos" not in entry:
                    st.caption(
                        "這是舊版打卡紀錄，當時未建立影像綁定，"
                        "無法確認哪些影像屬於本次打卡。"
                    )
                elif not entry["photos"]:
                    st.caption("此次打卡沒有已綁定的影像。")
                else:
                    for photo in entry["photos"]:
                        _show_photo_result(photo)

        legacy_pre = st.session_state.get("_legacy_pre_photos", [])
        legacy_ci = st.session_state.get("_legacy_ci_photos", [])

        if legacy_pre or legacy_ci:
            st.divider()
            st.subheader("③ 舊版影像｜未綁定提交紀錄")
            st.caption(
                "以下影像由舊版保存，可辨識入口，但無法確認屬於"
                "哪一次提交；請勿自動當成某筆紀錄的影像。"
            )

            if legacy_pre:
                st.markdown("#### 從診前入口上傳的舊影像")
                for photo in legacy_pre:
                    _show_photo_result(photo)

            if legacy_ci:
                st.markdown("#### 從打卡入口上傳的舊影像")
                for photo in legacy_ci:
                    _show_photo_result(photo)

        st.caption(
            "AI 影像與文字內容僅供參考，最終判斷請由獸醫師決定。"
        )

    with tab_draft:
        st.subheader("病歷草稿（需獸醫確認）")
        if visit is None:
            st.info("需先有飼主的診前紀錄，才能產生 SOAP 草稿。")
        st.text_area(
            "獸醫檢查紀錄（O 的來源）",
            key="vet_input",
            height=120,
            placeholder="例：觸診、檢查結果、獸醫量測的體重…",
        )
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
- 年齡與體重是獸醫評估的基本資料，本版**僅用於照護提醒與摘要**，不做任何劑量計算。
- 資料只保存在本次瀏覽器工作階段，重新整理即清空，不會上傳或寫入資料庫。
- 影像判讀時，照片或影片會傳送至所設定的 AI 服務處理，處理後即刪除，不寫入系統資料庫；本版不記錄聲音或定位資料。
- 角色切換僅供 Demo 展示，正式版將以登入與權限控管取代。
- 所有分級結果為照護提醒，不構成診斷或治療指示。
"""
    )
