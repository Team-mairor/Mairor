from tools import guide_scorecard
from tools.guide_area_training import compare_methods


def scored(found: dict[str, float], noise: dict[str, float], upper_noise: float = 0.0) -> dict:
    """부위마다 단계 하나(s1, 섀도는 윗자리 s1·아랫자리 s2)와 잡음 줄 하나인 판정 결과."""
    steps, noise_rows = [], []
    for part in guide_scorecard.PARTS:
        ids = ("s1", "s2") if part in compare_methods.ZONED_PARTS else ("s1",)
        for step_id in ids:
            ratio = found.get(f"{part}.{step_id}", found.get(part, 0.0))
            steps.append(
                {
                    "part": part,
                    "stepId": f"{part}-{step_id}",
                    "side": "left",
                    "status": "found" if ratio else "notFound",
                    "foundRatio": ratio,
                    "values": {"shiftRatio": 0.1} if ratio else {},
                }
            )
        row = {"part": part, "side": "left", "falsePositiveRatio": noise.get(part, 0.0)}
        if part in compare_methods.ZONED_PARTS:
            row["zones"] = [
                {"zone": "upper", "falsePositiveRatio": upper_noise},
                {"zone": "under", "falsePositiveRatio": noise.get(part, 0.0)},
            ]
        noise_rows.append(row)
    parts = []
    for part in guide_scorecard.PARTS:
        mine = [r for r in steps if r["part"] == part]
        rows = [r for r in noise_rows if r["part"] == part]
        parts.append(
            {
                "part": part,
                "steps": guide_scorecard.status_counts(mine),
                **guide_scorecard.separation(mine, rows),
            }
        )
    return {"noise": noise_rows, "steps": steps, "parts": parts}


ZONES = {
    "eyeshadow-s1": ("upper",),
    "eyeshadow-s2": ("under",),
    "eyeliner-s1": ("upper",),
    "eyeliner-s2": ("under",),
}


def test_region_score_splits_eyeshadow_steps_and_noise_by_zone():
    """섀도 자리별 가름은 그 자리 단계의 찾은 비율에서 그 자리 헛것을 뺀 값이다."""
    result = scored({"eyeshadow.s1": 1.0, "eyeshadow.s2": 0.5}, {"eyeshadow": 0.2}, 0.1)

    upper = compare_methods.region_score(result, "eyeshadow", "upper", ZONES)
    under = compare_methods.region_score(result, "eyeshadow", "under", ZONES)

    assert upper == {"foundShare": 1.0, "falsePositiveRatio": 0.1, "separation": 0.9}
    assert under == {"foundShare": 0.5, "falsePositiveRatio": 0.2, "separation": 0.3}


def test_zone_steps_counts_a_step_without_zone_in_both_zones():
    result = scored({"eyeshadow": 1.0}, {})

    upper = compare_methods.zone_steps(result, "eyeshadow", "upper", {})

    assert {row["stepId"] for row in upper} == {"eyeshadow-s1", "eyeshadow-s2"}


def test_rank_regions_puts_a_candidate_first_only_when_it_beats_the_rule():
    """규칙과 같은 후보는 규칙 뒤에 서고, 가름이 큰 후보만 앞에 선다."""
    rule = scored({"lip": 0.4, "blush": 0.9}, {"blush": 0.1})
    moved = scored({"lip": 0.3, "blush": 0.9}, {"blush": 0.1})
    better_lip = scored({"lip": 0.8, "blush": 0.9}, {"blush": 0.1})
    same = scored({"lip": 0.4, "blush": 0.9}, {"blush": 0.1})

    ranked = compare_methods.rank_regions(
        "rule",
        rule,
        moved,
        {},
        {"model": (better_lip, None), "same": (same, None)},
        ZONES,
    )

    assert [row["name"] for row in ranked["lip"]] == ["model", "rule", "same"]
    assert ranked["lip"][0]["gapToBase"] == 0.4
    assert ranked["lip"][0]["withinShake"] is False
    assert ranked["lip"][1]["selfShake"] == 0.1
    assert [row["name"] for row in ranked["blush"]][0] == "rule"


def test_rank_regions_puts_a_candidate_with_more_false_positives_behind_the_rule():
    """헛것이 규칙보다 는 후보는 가름이 커도 뒤로 간다(threshold_search.rank_key)."""
    rule = scored({"blush": 0.5}, {"blush": 0.0})
    noisy = scored({"blush": 1.0}, {"blush": 0.1})

    ranked = compare_methods.rank_regions("rule", rule, rule, {}, {"model": (noisy, None)}, ZONES)

    assert [row["name"] for row in ranked["blush"]] == ["rule", "model"]
    assert ranked["blush"][1]["falsePositiveRise"] == 0.1
    assert ranked["blush"][1]["beatsTemplate"] is True
