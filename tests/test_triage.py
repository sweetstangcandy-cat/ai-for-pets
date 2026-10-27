from triage import (
    GREEN,
    RED,
    YELLOW,
    CheckIn,
    build_soap_draft,
    owner_care_plan,
    triage_checkin,
    validate_profile,
    weight_change_note,
)


def test_normal_is_green():
    assert triage_checkin(CheckIn()).level == GREEN


def test_blood_stool_is_red():
    assert triage_checkin(CheckIn(stool="血便或黑便")).level == RED


def test_breathing_difficulty_is_red():
    assert triage_checkin(CheckIn(symptoms=["呼吸急促或困難"])).level == RED


def test_reduced_appetite_is_yellow():
    assert triage_checkin(CheckIn(appetite="減少")).level == YELLOW


def test_missed_dose_is_yellow():
    assert triage_checkin(CheckIn(missed_doses=1)).level == YELLOW


def test_red_overrides_yellow():
    c = CheckIn(appetite="減少", stool="血便或黑便")
    assert triage_checkin(c).level == RED


def test_red_wording_avoids_diagnosis():
    r = triage_checkin(CheckIn(stool="血便或黑便"))
    for banned in ["診斷為", "確定", "疑似"]:
        assert banned not in r.title
        assert banned not in r.action


def test_soap_assessment_marked_non_diagnostic():
    c = CheckIn(appetite="減少")
    draft = build_soap_draft(c, triage_checkin(c), "")
    assert "非診斷" in draft["A"]
    assert draft["O"] == "（待獸醫填寫）"


def test_red_plan_starts_with_urgent_action():
    c = CheckIn(energy="很嗜睡或無法起身")
    steps = owner_care_plan(c, triage_checkin(c))
    assert "聯繫獸醫" in steps[0]


def test_plan_never_changes_diet_without_vet():
    steps = owner_care_plan(CheckIn(), triage_checkin(CheckIn()))
    assert any("諮詢獸醫" in s for s in steps)


def test_weight_drop_over_threshold_is_yellow():
    c = CheckIn(weight_kg=4.0, previous_weight_kg=4.5)
    assert triage_checkin(c).level == YELLOW


def test_small_weight_change_is_ignored():
    c = CheckIn(weight_kg=4.3, previous_weight_kg=4.5)
    assert triage_checkin(c).level == GREEN


def test_missing_weight_gives_no_note():
    assert weight_change_note(None, 4.5) is None
    assert weight_change_note(4.0, None) is None


def test_profile_validation_rejects_out_of_range():
    assert validate_profile(weight_kg=500.0, age_years=3) != []
    assert validate_profile(weight_kg=4.2, age_years=-1) != []
    assert validate_profile(weight_kg=4.2, age_years=3) == []


def test_soap_subjective_includes_profile():
    c = CheckIn(species="貓", age_years=3, weight_kg=4.2)
    draft = build_soap_draft(c, triage_checkin(c), "")
    assert "4.2 公斤" in draft["S"]
    assert "3 歲" in draft["S"]
