import copy
import json

from tools.gauge import check_fe_readings as cf


def expected_of(name: str, group: str = "cases") -> dict:
    spec = json.loads((cf.SHARED / f"{name}.v1.json").read_text(encoding="utf-8"))
    return {case["name"]: copy.deepcopy(case["expected"]) for case in spec[group]}


def all_expected() -> dict:
    return {
        "measure": expected_of("measure"),
        "substitute": expected_of("substitute"),
        "stability": {g: expected_of("stability", g) for g in ("frames", "windows", "sequences")},
        "pipeline": expected_of("pipeline"),
    }


def test_expected_values_themselves_pass():
    assert cf.check(all_expected()) == []


def test_small_float_differences_pass_and_larger_ones_fail():
    readings = {"measure": expected_of("measure")}
    readings["measure"]["lipSameAmount"]["ratio"] += cf.ARITHMETIC / 2

    assert cf.check(readings) == []

    readings["measure"]["lipSameAmount"]["ratio"] += cf.ARITHMETIC * 2

    got = readings["measure"]["lipSameAmount"]["ratio"]
    assert cf.check(readings) == [
        f"measure.cases.lipSameAmount.ratio: 1.0 · {got!r} (허용 {cf.ARITHMETIC:g})"
    ]


def test_pipeline_uses_its_own_tolerance_per_value():
    readings = {"pipeline": expected_of("pipeline")}
    spec = json.loads((cf.SHARED / "pipeline.v1.json").read_text(encoding="utf-8"))
    case = readings["pipeline"]["lipSame"]
    case["measure"]["ratio"] += spec["tolerance"]["ratio"] * 0.9
    case["sides"][0]["after"][0] += spec["tolerance"]["lab"] * 0.9

    assert cf.check(readings) == []

    case["measure"]["ratio"] += spec["tolerance"]["ratio"]

    assert len(cf.check(readings)) == 1


def test_missing_cases_and_flags_are_reported():
    readings = {"measure": expected_of("measure")}
    readings["measure"].pop("lipHalfAmount")
    readings["measure"]["lipSameAmount"]["hueSame"] = False

    wrong = cf.check(readings)

    assert "measure.cases.lipHalfAmount: 없음" in wrong
    assert "measure.cases.lipSameAmount.hueSame: True · False" in wrong


def test_same_flags_may_flip_only_near_the_bound():
    """hue가 「비슷」 경계 2.9도에서 허용 오차 안이면 hueSame은 어느 쪽이어도 맞고, 멀면 틀린다."""
    readings = {"measure": expected_of("measure")}
    case = readings["measure"]["lipSameAmount"]
    spec = json.loads((cf.SHARED / "measure.v1.json").read_text(encoding="utf-8"))
    bound = spec["color"]["hueSameDegrees"]
    expected = copy.deepcopy(spec)
    near = next(c for c in expected["cases"] if c["name"] == "lipSameAmount")["expected"]
    near["hue"] = bound - cf.ARITHMETIC / 2

    assert set(cf._near_same_bound(near, cf.ARITHMETIC)) == {"hueSame"}

    case["hueSame"] = not case["hueSame"]

    assert cf.check(readings) == ["measure.cases.lipSameAmount.hueSame: True · False"]
