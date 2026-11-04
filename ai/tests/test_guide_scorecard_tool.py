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
    assert brow["steps"] == {"passed": 1, "failed": 0, "notFound": 1}
    assert brow["passed"] is False
    lip = next(p for p in result["parts"] if p["part"] == "lip")
    assert lip["noisePassed"] is False and lip["passed"] is False
