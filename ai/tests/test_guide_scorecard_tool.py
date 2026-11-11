from app.schemas.manifest import Manifest
from tools import guide_scorecard

BROW_S8 = {
    "foundRatio": 1.0,
    "shiftRatio": 0.033,
    "cover": 0.84,
    "overflow": 0.191,
    "outsideRatio": 0.105,
    "keepRatio": 0.949,
    "t50": 0.419,
    "strongShare": 0.774,
}
LIP_S27 = {
    "foundRatio": 1.0,
    "shiftRatio": 0.044,
    "cover": 0.999,
    "overflow": 0.155,
    "outsideRatio": 0.018,
    "keepRatio": 0.815,
    "t50": 0.815,
    "strongShare": 0.758,
}


def by_name(checks):
    return {c["name"]: c for c in checks}


def test_check_compares_upper_and_lower_lines_and_reports_how_far_the_value_is():
    upper = guide_scorecard.Line("x", "x", 0.05, True, ("brow",))
    lower = guide_scorecard.Line("y", "y", 0.7, False, ("brow",))

    assert guide_scorecard.check(upper, 0.27) | {"value": None} == {
        "name": "x",
        "limit": 0.05,
        "value": None,
        "passed": False,
        "gap": 5.4,
    }
    assert (
        guide_scorecard.check(upper, -0.1)["passed"]
        and guide_scorecard.check(upper, -0.1)["gap"] == 0.0
    )
    assert guide_scorecard.check(lower, 0.35)["gap"] == 2.0
    assert not guide_scorecard.check(lower, None)["passed"]


def test_reference_cases_pass_every_line_with_some_room():
    for part, values in (("brow", BROW_S8), ("lip", LIP_S27)):
        passed, checks = guide_scorecard.judge(part, values, guide_scorecard.STEP_LINES)

        assert passed
        assert all(c["name"] == "foundRatio" or c["gap"] is None or c["gap"] < 1 for c in checks)


def test_a_moment_only_eyeliner_area_fails_on_how_long_the_change_stays():
    values = {
        "foundRatio": 1.0,
        "shiftRatio": 0.058,
        "intrude": 0.069,
        "outsideRatio": 0.0,
        "keepRatio": 0.333,
        "t50": 1.065,
    }

    passed, checks = guide_scorecard.judge("eyeliner", values, guide_scorecard.STEP_LINES)

    names = by_name(checks)
    assert not passed
    assert not names["keepRatio"]["passed"] and names["keepRatio"]["gap"] == 2.1
    assert "t50Max" not in names and "cover" not in names


def test_lines_apply_only_to_parts_that_have_the_metric():
    _, blush = guide_scorecard.judge("blush", {}, guide_scorecard.STEP_LINES)
    _, shadow = guide_scorecard.judge("eyeshadow", {}, guide_scorecard.STEP_LINES)

    assert {"cover", "overflow", "intrude"}.isdisjoint(by_name(blush))
    assert "t50Min" in by_name(blush)
    assert "intrude" in by_name(shadow) and "t50Min" not in by_name(shadow)
    _, liner = guide_scorecard.judge("eyeliner", {}, guide_scorecard.STEP_LINES)
    assert "strongShare" in by_name(shadow) and "strongShare" not in by_name(liner)


def test_an_area_mostly_made_of_faint_cells_fails_as_too_wide():
    values = BROW_S8 | {"strongShare": 0.415}

    passed, checks = guide_scorecard.judge("blush", values, guide_scorecard.STEP_LINES)

    assert not passed
    assert [c["name"] for c in checks if not c["passed"]] == ["strongShare"]


def test_noise_rates_add_up_every_gap_for_each_side():
    doc = {
        "summary": [
            {"part": "brow", "side": "leftBrow", "pairs": 100, "falsePositives": 1},
            {"part": "brow", "side": "leftBrow", "pairs": 100, "falsePositives": 3},
            {"part": "lip", "side": "lipsOuter", "pairs": 0, "falsePositives": 0},
        ]
    }

    rates = guide_scorecard.noise_rates(doc)

    assert rates[("brow", "leftBrow")] == 0.02
    assert rates[("lip", "lipsOuter")] is None


def test_score_counts_not_found_steps_apart_and_needs_every_step_and_noise_to_pass():
    def stability(step_id, base_found, shift):
        return {
            "part": "brow",
            "stepId": step_id,
            "side": "leftBrow",
            "found": 9,
            "total": 9,
            "baseFound": base_found,
            "shiftRatio": shift,
        }

    timing = {k: BROW_S8[k] for k in ("outsideRatio", "keepRatio", "t50", "strongShare")}
    docs = {
        "noise.json": {
            "summary": [{"part": "brow", "side": "leftBrow", "pairs": 100, "falsePositives": 2}]
        },
        "stability.json": {"steps": [stability("s8", True, 0.033), stability("s23", False, None)]},
        "boundary.json": {
            "steps": [
                {
                    "part": "brow",
                    "stepId": "s8",
                    "side": "leftBrow",
                    "cover": 0.84,
                    "overflow": 0.19,
                }
            ]
        },
        "timing.json": {"steps": [{"part": "brow", "stepId": "s8", "side": "leftBrow", **timing}]},
    }

    result = guide_scorecard.score(docs)

    assert [r["status"] for r in result["steps"]] == ["passed", "notFound"]
    brow = next(p for p in result["parts"] if p["part"] == "brow")
    assert brow["noisePassed"] is True
    assert brow["steps"] == {"passed": 1, "failed": 0, "notFound": 1, "reused": 0}
    assert brow["passed"] is False
    lip = next(p for p in result["parts"] if p["part"] == "lip")
    assert lip["noisePassed"] is False and lip["passed"] is False


def test_score_counts_steps_that_reuse_the_earlier_brow_area_apart_without_lines():
    """못 찾아 앞 눈썹 단계 영역을 그대로 보낸 단계(나가는 영역 reusedArea)는 reused로 세고
    선은 재지 않는다. 찾은 것이 아니라서 부위 합격으로는 치지 않는다.

    쪽마다 찾은 영역 판정은 못 찾음 그대로다.
    """
    timing = {k: BROW_S8[k] for k in ("outsideRatio", "keepRatio", "t50", "strongShare")}
    side = {"part": "brow", "side": "leftBrow", "found": 0, "total": 9, "baseFound": False}
    output = {"found": 9, "total": 9, "baseFound": True, "shiftRatio": 0.0, "reusedArea": True}
    docs = {
        "noise.json": {
            "summary": [{"part": "brow", "side": "leftBrow", "pairs": 100, "falsePositives": 2}]
        },
        "stability.json": {"steps": [{"stepId": "s23", **side, "output": output}]},
        "boundary.json": {"steps": []},
        "timing.json": {
            "steps": [
                {"part": "brow", "stepId": "s23", "side": "leftBrow", "output": timing},
            ]
        },
    }

    result = guide_scorecard.score(docs)

    row = result["steps"][0]
    assert (row["status"], row["checks"], row["sideStatus"]) == ("reused", [], "notFound")
    brow = next(p for p in result["parts"] if p["part"] == "brow")
    assert brow["steps"] == {"passed": 0, "failed": 0, "notFound": 0, "reused": 1}
    assert brow["passed"] is False


def test_score_judges_the_drawn_area_and_keeps_the_side_result_for_reference():
    """사용자는 나가는 영역을 보므로 판정은 output 값으로 하고, 쪽마다 판정은 참고로 남긴다.

    쪽마다는 못 찾았지만 반대쪽을 뒤집어 그린 쪽(섀도 s10, 아이라인 s13에서 실제로 있던 경우)과,
    쪽마다는 헛것이 없지만 화면에는 헛것이 나간 잡음 줄을 골랐다.
    """
    timing = {k: BROW_S8[k] for k in ("outsideRatio", "keepRatio", "t50", "strongShare")}
    stability = {
        "part": "brow",
        "stepId": "s8",
        "side": "rightBrow",
        "found": 0,
        "total": 9,
        "baseFound": False,
        "shiftRatio": None,
        "output": {"found": 9, "total": 9, "baseFound": True, "shiftRatio": 0.033},
    }
    docs = {
        "noise.json": {
            "summary": [
                {
                    "part": "brow",
                    "side": "rightBrow",
                    "pairs": 100,
                    "falsePositives": 0,
                    "outputFalsePositives": 20,
                }
            ]
        },
        "stability.json": {"steps": [stability]},
        "boundary.json": {
            "steps": [
                {
                    "part": "brow",
                    "stepId": "s8",
                    "side": "rightBrow",
                    "found": False,
                    "output": {"found": True, "cover": 0.84, "overflow": 0.19},
                }
            ]
        },
        "timing.json": {
            "steps": [
                {
                    "part": "brow",
                    "stepId": "s8",
                    "side": "rightBrow",
                    "found": False,
                    "output": {"found": True, **timing},
                }
            ]
        },
    }

    result = guide_scorecard.score(docs)

    (noise,) = result["noise"]
    assert noise["passed"] is False and noise["sidePassed"] is True
    (step,) = result["steps"]
    assert (step["status"], step["sideStatus"]) == ("passed", "notFound")
    assert step["sideChecks"] == []


def test_a_line_that_could_not_be_measured_is_left_out_but_a_missing_value_still_fails():
    """조심할 구간 때문에 잴 시각이 없던 유지 비는 못 잼으로 두고 판정에서 뺀다(시험 영상 립 s27).

    같은 빈 값이라도 못 잼으로 적히지 않았으면 지금처럼 불합격이어야 찾기 실패 같은 진짜 문제를
    놓치지 않는다. 시간 결과의 notMeasured가 판정까지 이어지는지 step_status로 본다.
    """
    stability = {"found": 9, "total": 9, "baseFound": True, "shiftRatio": 0.044}
    boundary = {"cover": 0.999, "overflow": 0.155}
    timing = {"outsideRatio": 0.018, "keepRatio": None, "t50": 0.815, "strongShare": 0.758}

    status, checks = guide_scorecard.step_status(
        "lip", stability, boundary, timing | {"notMeasured": ["keepRatio"]}
    )

    assert status == "passed"
    assert by_name(checks)["keepRatio"]["passed"] is None
    assert "keepRatio 못 잼" in guide_scorecard.describe(checks)
    assert guide_scorecard.step_status("lip", stability, boundary, timing)[0] == "failed"


def test_every_analysed_step_of_the_test_video_has_a_zone():
    """시험 영상의 섀도·아이라인·블러셔·립 단계는 모두 자리 이름표가 있다.

    단계표를 다시 나누면서 이름표를 빠뜨리면 그 단계가 자리 요약에서 조용히 빠지므로 막는다.
    """
    manifest = Manifest.model_validate_json(
        (guide_scorecard.AI_ROOT / "samples" / "local_03_seq" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    zoned = {"eyeshadow", "eyeliner", "blush", "lip"}
    steps = {step.step_id for step in manifest.steps if step.makeup in zoned}

    assert steps and steps == set(guide_scorecard.STEP_ZONES)


def test_score_judges_noise_and_counts_steps_for_each_zone():
    """섀도가 불합격이어도 윗눈두덩·눈 밑 중 어디가 문제인지 자리마다 보이는지 본다.

    헛것 10% 중 9%가 선 위에 난 잡음 줄과, 윗눈두덩 단계는 합격·눈 밑 단계는 못 찾음인 경우를
    골랐다.
    """
    stability = {"found": 9, "total": 9, "baseFound": True, "shiftRatio": 0.03}
    timing = {"outsideRatio": 0.1, "keepRatio": 0.9, "strongShare": 0.8}

    def step(step_id, base_found):
        key = {"part": "eyeshadow", "stepId": step_id, "side": "leftEye"}
        return key | stability | {"baseFound": base_found}

    docs = {
        "noise.json": {
            "summary": [
                {
                    "part": "eyeshadow",
                    "side": "leftEye",
                    "pairs": 100,
                    "falsePositives": 10,
                    "outputFalsePositives": 10,
                    "outputUpperFalsePositives": 9,
                    "outputUnderFalsePositives": 1,
                },
                {"part": "brow", "side": "leftBrow", "pairs": 100, "falsePositives": 0},
            ]
        },
        "stability.json": {"steps": [step("s10a", True), step("s10b", False)]},
        "boundary.json": {
            "steps": [{"part": "eyeshadow", "stepId": "s10a", "side": "leftEye", "intrude": 0.01}]
        },
        "timing.json": {
            "steps": [{"part": "eyeshadow", "stepId": "s10a", "side": "leftEye", **timing}]
        },
    }

    result = guide_scorecard.score(docs)

    shadow_noise = next(r for r in result["noise"] if r["part"] == "eyeshadow")
    assert shadow_noise["passed"] is False
    assert [(z["zone"], z["passed"]) for z in shadow_noise["zones"]] == [
        ("upper", False),
        ("under", True),
    ]
    assert "zones" not in next(r for r in result["noise"] if r["part"] == "brow")
    assert [(r["stepId"], r["zone"], r["status"]) for r in result["steps"]] == [
        ("s10a", "upper", "passed"),
        ("s10b", "under", "notFound"),
    ]
    shadow = next(p for p in result["parts"] if p["part"] == "eyeshadow")
    assert shadow["zones"] == [
        {
            "zone": "upper",
            "noisePassed": False,
            "steps": {"passed": 1, "failed": 0, "notFound": 0, "reused": 0},
        },
        {
            "zone": "under",
            "noisePassed": True,
            "steps": {"passed": 0, "failed": 0, "notFound": 1, "reused": 0},
        },
    ]
    assert next(p for p in result["parts"] if p["part"] == "brow")["zones"] == []
