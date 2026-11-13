import json

import pytest

from tools import guide_scorecard

TIMING = {"outsideRatio": 0.105, "keepRatio": 0.949, "t50": 0.419, "strongShare": 0.774}


def stability(part, step_id, side, base_found, shift=0.03, found=9, **more):
    return {
        "part": part,
        "stepId": step_id,
        "side": side,
        "found": found,
        "total": 9,
        "baseFound": base_found,
        "shiftRatio": shift,
        **more,
    }


def brow_docs(false_positives=2, steps=None, boundary=None, timing=None):
    """눈썹 왼쪽 한 쪽짜리 결과 파일 네 개. 잡음은 100쌍이다."""
    return {
        "noise.json": {
            "summary": [
                {
                    "part": "brow",
                    "side": "leftBrow",
                    "pairs": 100,
                    "falsePositives": false_positives,
                }
            ]
        },
        "stability.json": {"steps": steps or []},
        "boundary.json": {"steps": boundary or []},
        "timing.json": {"steps": timing or []},
    }


def part(result, name):
    return next(p for p in result["parts"] if p["part"] == name)


def test_no_fixed_pass_line_is_left_in_the_tool():
    """사람이 정한 합격선과 단계마다 눈으로 적은 자리 표는 두지 않는다."""
    for name in ("NOISE_LINE", "STEP_LINES", "STEP_ZONES", "Line", "judge"):
        assert not hasattr(guide_scorecard, name)


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


def test_step_values_keep_only_the_metrics_of_the_part():
    """경계 지표는 분할 모델이 있는 눈썹·립에만, 눈 침범은 섀도·아이라인에만 적는다.

    아이라인 색 값은 바뀜/안 바뀜 두 값이라 진한 칸 비율을 적지 않는다.
    """
    row = stability("x", "s1", "side", True)
    names = {
        name: set(guide_scorecard.step_values(name, row, {}, {})) for name in guide_scorecard.PARTS
    }

    assert {"cover", "overflow"} <= names["brow"] and {"cover", "overflow"} <= names["lip"]
    assert "cover" not in names["blush"] and "intrude" not in names["blush"]
    assert "intrude" in names["eyeshadow"] and "intrude" in names["eyeliner"]
    assert "strongShare" in names["eyeshadow"] and "strongShare" not in names["eyeliner"]


def test_a_metric_that_could_not_be_measured_has_no_value():
    """조심할 구간이라 잴 시각이 없던 유지 비(notMeasured)는 값을 적지 않는다."""
    timing = {**TIMING, "keepRatio": 0.1, "notMeasured": ["keepRatio"]}

    values = guide_scorecard.step_values("blush", stability("blush", "s22", "c", True), {}, timing)

    assert values["keepRatio"] is None and values["outsideRatio"] == 0.105


def test_score_separates_found_not_found_and_reused_steps():
    """못 찾은 쪽은 notFound, 앞 눈썹 단계 영역을 그대로 보낸 쪽은 reused이고 둘 다 값이 없다."""
    reused = stability(
        "brow",
        "s23",
        "leftBrow",
        False,
        found=0,
        output={"found": 9, "total": 9, "baseFound": True, "shiftRatio": 0.0, "reusedArea": True},
    )
    docs = brow_docs(
        steps=[
            stability("brow", "s8", "leftBrow", True),
            stability("brow", "s9", "leftBrow", False, None),
            reused,
        ],
        boundary=[
            {"part": "brow", "stepId": "s8", "side": "leftBrow", "cover": 0.84, "overflow": 0.19}
        ],
        timing=[{"part": "brow", "stepId": "s8", "side": "leftBrow", **TIMING}],
    )

    result = guide_scorecard.score(docs)

    assert [r["status"] for r in result["steps"]] == ["found", "notFound", "reused"]
    assert result["steps"][0]["values"]["cover"] == 0.84
    assert result["steps"][1]["values"] == {} and result["steps"][2]["values"] == {}
    assert result["steps"][2]["sideStatus"] == "notFound"
    assert part(result, "brow")["steps"] == {"found": 1, "notFound": 1, "reused": 1}


def test_separation_is_found_share_minus_false_positive_ratio():
    """가름 = 단계·쪽마다 창 조합 중 찾은 비율의 평균 − 안 바른 쌍 중 영역이 나간 비율."""
    docs = brow_docs(
        false_positives=10,
        steps=[
            stability("brow", "s8", "leftBrow", True, found=9),
            stability("brow", "s9", "leftBrow", False, None, found=3),
        ],
    )

    brow = part(guide_scorecard.score(docs), "brow")

    assert brow["foundShare"] == pytest.approx((1 + 3 / 9) / 2, abs=1e-4)
    assert brow["falsePositiveRatio"] == 0.1
    assert brow["separation"] == pytest.approx((1 + 3 / 9) / 2 - 0.1, abs=1e-4)


def test_separation_counts_a_step_found_in_only_some_windows_as_partly_found():
    """서비스 그대로의 창에서는 찾아도 창을 옮긴 조합 절반에서 못 찾으면 찾은 비율은 절반이다."""
    steps = [{"status": "found", "foundRatio": 4 / 9}]

    result = guide_scorecard.separation(steps, [{"falsePositiveRatio": 0.0}])

    assert result["foundShare"] == pytest.approx(0.4444)


def test_separation_takes_the_worse_side_and_leaves_out_reused_and_not_analyzed_steps():
    """앞 단계 영역을 다시 쓴 단계와 서비스가 색으로 찾지 않는 단계(코 블러셔)는 세지 않는다."""
    steps = [
        {"status": "found", "foundRatio": 1.0},
        {"status": "reused", "foundRatio": 1.0},
        {"status": "notFound", "foundRatio": 0.2, "notAnalyzed": True},
    ]
    noise = [{"falsePositiveRatio": 0.02}, {"falsePositiveRatio": 0.2}]

    result = guide_scorecard.separation(steps, noise)

    assert result == {"foundShare": 1.0, "falsePositiveRatio": 0.2, "separation": 0.8}


def test_score_marks_a_step_the_service_does_not_analyze():
    row = {**stability("blush", "s22b", "leftCheek", False, None, found=2), "notAnalyzed": True}
    docs = brow_docs(steps=[row])

    step = guide_scorecard.score(docs)["steps"][0]

    assert step["notAnalyzed"] is True and step["foundRatio"] == pytest.approx(0.2222)


def test_separation_is_empty_for_a_part_with_no_rows():
    assert guide_scorecard.separation([], [])["separation"] is None


def test_score_reads_the_drawn_area_and_keeps_the_side_result_for_reference():
    """사용자는 나가는 영역을 보므로 값은 output 것이고, 쪽마다 값은 참고로 남긴다."""
    row = stability(
        "brow",
        "s8",
        "rightBrow",
        False,
        None,
        found=0,
        output={"found": 9, "total": 9, "baseFound": True, "shiftRatio": 0.033},
    )
    docs = {
        "noise.json": {
            "summary": [
                {
                    "part": "brow",
                    "side": "rightBrow",
                    "pairs": 100,
                    "falsePositives": 0,
                    "outputFalsePositives": 7,
                }
            ]
        },
        "stability.json": {"steps": [row]},
        "boundary.json": {"steps": []},
        "timing.json": {
            "steps": [{"part": "brow", "stepId": "s8", "side": "rightBrow", "output": TIMING}]
        },
    }

    result = guide_scorecard.score(docs)

    step = result["steps"][0]
    assert (step["status"], step["sideStatus"]) == ("found", "notFound")
    assert step["values"]["shiftRatio"] == 0.033 and step["sideValues"] == {}
    noise = result["noise"][0]
    assert (noise["falsePositiveRatio"], noise["sideFalsePositiveRatio"]) == (0.07, 0.0)


def test_score_lists_noise_for_each_zone_when_the_noise_rows_have_zone_counts():
    docs = brow_docs()
    docs["noise.json"]["summary"] = [
        {
            "part": "eyeshadow",
            "side": "leftEye",
            "pairs": 50,
            "falsePositives": 1,
            "outputFalsePositives": 2,
            "outputUpperFalsePositives": 5,
            "outputUnderFalsePositives": 0,
        }
    ]

    row = guide_scorecard.score(docs)["noise"][0]

    assert row["zones"] == [
        {"zone": "upper", "falsePositiveRatio": 0.1},
        {"zone": "under", "falsePositiveRatio": 0.0},
    ]


def scored(shift, cover, status="found"):
    values = {} if status != "found" else {"shiftRatio": shift, "cover": cover, "t50": 0.5}
    return {
        "steps": [
            {"part": "brow", "stepId": "s8", "side": "leftBrow", "status": status, "values": values}
        ],
        "parts": [
            {
                "part": "brow",
                "steps": {"found": int(status == "found"), "notFound": 0, "reused": 0},
                "falsePositiveRatio": 0.02,
                "separation": 0.9,
            }
        ],
    }


def test_bands_are_the_middle_gap_between_two_runs_of_the_same_code():
    """측정 흔들림은 같은 코드로 창만 옮겨 잰 두 결과의 단계·쪽 차이 가운데 값이다."""

    def rows(values):
        return {
            "steps": [
                {"part": "brow", "stepId": f"s{i}", "side": "leftBrow", "values": {"cover": v}}
                for i, v in enumerate(values)
            ]
        }

    band = guide_scorecard.bands(rows([0.80, 0.50, 0.90]), rows([0.82, 0.60, 0.89]))

    assert band["cover"] == pytest.approx(0.02)
    assert band["shiftRatio"] == 0.0


def test_compare_calls_a_change_inside_the_band_the_same():
    result = guide_scorecard.compare(
        scored(0.030, 0.80), scored(0.034, 0.90), {"shiftRatio": 0.005, "cover": 0.02}
    )

    verdicts = {c["metric"]: c["verdict"] for c in result["changes"]}
    assert verdicts == {"shiftRatio": "same", "cover": "better"}
    assert (result["parts"][0]["better"], result["parts"][0]["same"]) == (1, 1)


def test_compare_knows_which_way_is_better_for_each_metric():
    """흔들림은 작을수록, 덮음은 클수록 좋다. 좋은 방향이 없는 t50은 견주지 않는다."""
    result = guide_scorecard.compare(scored(0.03, 0.80), scored(0.09, 0.60), {})

    verdicts = {c["metric"]: c["verdict"] for c in result["changes"]}
    assert verdicts == {"shiftRatio": "worse", "cover": "worse"}
    assert result["parts"][0]["worse"] == 2


def test_compare_lists_a_step_whose_status_changed_apart():
    result = guide_scorecard.compare(scored(0.03, 0.8), scored(None, None, "notFound"), {})

    assert result["changes"] == []
    assert result["statusChanges"] == [
        {
            "part": "brow",
            "stepId": "s8",
            "side": "leftBrow",
            "before": "found",
            "after": "notFound",
        }
    ]


def test_load_score_needs_all_four_result_files(tmp_path):
    docs = brow_docs(steps=[stability("brow", "s8", "leftBrow", True)])
    for name, doc in list(docs.items())[:3]:
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")

    assert guide_scorecard.load_score(tmp_path) is None

    (tmp_path / "timing.json").write_text(json.dumps(docs["timing.json"]), encoding="utf-8")
    assert part(guide_scorecard.load_score(tmp_path), "brow")["steps"]["found"] == 1
