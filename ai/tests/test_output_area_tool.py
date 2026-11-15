from pathlib import Path

import numpy as np
import pytest

from app.schemas.manifest import Step
from app.tasks.area import guide_area_builder
from app.tasks.area.common.face_map import MAP_SIZE, map_points, points_to_anchors
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.guide_area_builder import build_guide_area, eyeshadow_sub_steps
from app.tasks.area.parts.blush_area import BlushArea, cheek_range
from app.tasks.area.parts.brow_area import BrowArea, brow_range
from app.tasks.area.parts.eyeliner_area import EyelinerArea
from app.tasks.area.parts.eyeshadow_area import EyeshadowArea, ZoneArea, eyeshadow_range
from app.tasks.area.parts.lip_area import LipArea
from tests.test_eyeliner_area import lash_line, with_gap
from tests.test_guide_area_builder import RESULT, never
from tools import output_area


def iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / (a | b).sum())


def lips() -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)


def test_anchor_points_undo_points_to_anchors():
    """얼굴 주소는 비율을 넷째 자리에서 반올림하므로, 되돌린 좌표가 0.05칸 안에 들면 같은 자리다."""
    points = [(100.0, 200.0), (512.3, 400.7), (700.0, 650.0)]

    back = output_area.anchor_points(points_to_anchors(points))

    assert np.allclose(back, points, atol=0.05)


def test_lip_mask_comes_back_almost_the_same_through_the_service_outline():
    """서비스는 바깥선을 펴서 보내므로 둘레 한 줄 안팎만 달라지고, 입 안은 exclude 구멍으로 빠진다.

    입술 넓이(약 16,000칸)에서 둘레 한 줄은 3% 남짓이라, 입 안을 뺀 입술과 겹침 0.95 이상이면
    같은 모양으로 본다.
    """
    masks, sub_step, _ = output_area.output_area("lip", {"lipsOuter": LipArea(mask=lips())})
    without_inside = lips() & ~output_area.region_outline("lipsInner")

    assert sub_step.status == "extracted"
    assert sub_step.guide_sets[0].exclude == ["lipsInner"]
    assert iou(masks["lipsOuter"], without_inside) >= 0.95


def test_one_brow_found_is_drawn_on_both_brows():
    """서비스는 한쪽 눈썹만 찾으면 그쪽을 뒤집어 양쪽에 쓰므로, 못 찾은 쪽에도 나가는 영역이 있다.

    쪽마다 재면 못 찾음인 쪽이 화면에서는 그려지는 차이를 이 도구가 잡아야 해서 고른 경우다.
    """
    areas = {
        "leftBrow": BrowArea(mask=brow_range("leftBrow"), darkening=3.0),
        "rightBrow": BrowArea(mask=None, reason="browColorNotFound"),
    }

    masks, sub_step, _ = output_area.output_area("brow", areas)

    assert sub_step.status == "extracted"
    assert output_area.found_side(masks, "rightBrow") is not None
    assert iou(masks["rightBrow"], brow_range("leftBrow")[:, ::-1]) >= 0.8


def test_one_cheek_found_draws_no_blush():
    """블러셔는 두 볼 모두 찾아야 그리므로(paired_blush), 한쪽만 찾으면 나가는 영역이 없다."""
    areas = {
        "leftCheek": BlushArea(mask=np.array(cheek_range("leftCheek")), peak=5.0),
        "rightCheek": BlushArea(mask=None, reason="blushColorNotFound"),
    }

    masks, sub_step, _ = output_area.output_area("blush", areas)

    assert (sub_step.status, sub_step.reasons) == ("template", ["blushColorNotFound"])
    assert masks == {}


def test_each_cheek_keeps_its_own_shape_in_the_output():
    """두 볼 모두 찾으면 볼마다 찾은 모양을 그대로 그린다. 한쪽을 뒤집어 쓰지 않는다."""
    left = np.array(cheek_range("leftCheek"))
    right = np.array(cheek_range("rightCheek"))
    right[: np.nonzero(right.any(axis=1))[0].mean().astype(int)] = False
    areas = {
        "leftCheek": BlushArea(mask=left, peak=5.0),
        "rightCheek": BlushArea(mask=right, peak=4.0),
    }

    masks, _, _ = output_area.output_area("blush", areas)

    assert iou(masks["leftCheek"], left) >= 0.95
    assert iou(masks["rightCheek"], right) >= 0.95
    assert iou(masks["rightCheek"], left[:, ::-1]) < 0.8


def shadow(eye: str, zones: dict[str, float]) -> EyeshadowArea:
    """zones의 자리마다 그 세기로 자리 전체를 찾고 나머지 자리는 못 찾은 눈 하나의 결과."""
    found = {
        zone: ZoneArea(mask=eyeshadow_range(eye, zone), strength=zones[zone])
        if zone in zones
        else ZoneArea(mask=None, strength=0.5, reason="eyeshadowColorNotFound")
        for zone in ("upper", "under")
    }
    masks = [area.mask for area in found.values() if area.mask is not None]
    if not masks:
        return EyeshadowArea(mask=None, reason="eyeshadowColorNotFound", zones=found)
    return EyeshadowArea(mask=np.any(masks, axis=0), zones=found)


def test_eyeshadow_output_leaves_out_the_eye_hole():
    """섀도는 눈 구멍을 exclude로 보내므로 나가는 영역에 눈 점 테두리 안 칸이 없어야 한다."""
    areas = {eye: shadow(eye, {"upper": 5.0, "under": 5.0}) for eye in ("leftEye", "rightEye")}

    masks, _, _ = output_area.output_area("eyeshadow", areas)

    for eye in ("leftEye", "rightEye"):
        assert masks[eye].any()
        assert not (masks[eye] & output_area.region_outline(eye)).any()


def test_step_sent_as_default_guide_has_no_output_area():
    """두 쪽 모두 못 찾으면 template이라 FE는 기본 가이드를 그리고 찾은 영역은 나가지 않는다."""
    areas = {
        "leftBrow": BrowArea(mask=None, reason="browColorNotFound"),
        "rightBrow": BrowArea(mask=None, reason="noUsableFrame"),
    }

    masks, sub_step, _ = output_area.output_area("brow", areas)

    assert masks == {}
    assert output_area.found_side(masks, "leftBrow") is None
    assert output_area.not_found_reason(sub_step) == "template,browColorNotFound,noUsableFrame"


def test_eyeshadow_sub_steps_of_both_zones_are_measured_as_one_area():
    """윗눈두덩·눈 밑 하위 단계가 둘 다 나가면, 도구는 눈마다 두 영역을 합친 하나로 잰다."""
    areas = {eye: shadow(eye, {"upper": 5.0, "under": 5.0}) for eye in ("leftEye", "rightEye")}
    zones = ("upper", "under")

    masks, sub_step, _ = output_area.output_area("eyeshadow", areas, zones=zones)
    each = [output_area.output_masks(s) for s in eyeshadow_sub_steps("s1", areas, zones)]

    assert sub_step.status == "extracted" and len(sub_step.guide_sets) == 4
    for eye in ("leftEye", "rightEye"):
        assert np.array_equal(masks[eye], each[0][eye] | each[1][eye])


def test_eyeshadow_output_follows_the_step_zone():
    """도구도 서비스처럼 단계의 바른 자리만 낸다. 윗눈두덩만 찾았으면 눈 밑 단계는 빈 영역이다."""
    upper_only = {eye: shadow(eye, {"upper": 5.0}) for eye in ("leftEye", "rightEye")}

    masks, sub_step, _ = output_area.output_area("eyeshadow", upper_only, zones=("under",))
    upper_masks, _, _ = output_area.output_area("eyeshadow", upper_only, zones=("upper",))

    assert masks == {}
    assert (sub_step.status, sub_step.template_id) == ("template", "eyeshadowUnder")
    assert all(upper_masks[eye].any() for eye in ("leftEye", "rightEye"))


def test_step_zones_come_from_the_sample_guide_input():
    """시험 영상 가이드 입력 글로 섀도·아이라인 단계마다 자리를 정한다. 입력이 없으면 빈 dict다."""
    samples = Path(__file__).resolve().parents[1] / "samples"

    zones = output_area.step_zones(samples / "local_03_seq")

    assert zones == {
        "s10a": ("upper",),
        "s10b": ("under",),
        "s11a": ("under",),
        "s11b": ("upper",),
        "s17": ("under",),
        "s12": ("upper",),
        "s13a": ("under",),
        "s13b": ("under",),
        "s14": ("under",),
        "s15b": ("under",),
        "s16a": ("waterline",),
        "s16b": ("under",),
        "s19": ("upper",),
    }
    assert output_area.step_zones(samples / "local_01_lip_seq") == {}


def test_missing_area_is_the_service_reason_for_no_photos():
    """재지 못한 쪽은 서비스에서도 쓸 사진이 없는 경우라 같은 이유로 넘겨야 결과가 같다."""
    area = output_area.missing_area("eyeshadow")

    assert isinstance(area, EyeshadowArea)
    assert (area.mask, area.reason) == (None, "noUsableFrame")


def test_drawn_before_uses_eyeliner_steps_that_ended_before_the_start():
    """BE 단계는 앞 단계 끝과 다음 단계 시작이 같다.

    그래서 끝난 시각이 시작 시각과 같아도 앞 단계 칸을 넣어야 한다.
    """
    first, second = np.ones((2, 2), dtype=bool), np.zeros((2, 2), dtype=bool)
    timeline = [(10000, first), (20000, second)]

    assert output_area.drawn_before(timeline, 5000) is None
    assert output_area.drawn_before(timeline, 10000) is first
    assert output_area.drawn_before(timeline, 25000) is second


FIXED_AREAS = {
    "brow": lambda side: BrowArea(
        mask=brow_range(side), darkening=3.0 if side == "leftBrow" else 2.0
    ),
    "eyeshadow": lambda side: shadow(
        side, {"upper": 5.0, "under": 5.0} if side == "leftEye" else {"under": 5.0}
    ),
    "blush": lambda side: BlushArea(mask=cheek_range(side)),
    "lip": lambda side: LipArea(mask=lips()),
    "eyeliner": lambda side: EyelinerArea(mask=with_gap(lash_line(side, upper=False), 20)),
}
SIDES = {
    "brow": ("leftBrow", "rightBrow"),
    "eyeshadow": ("leftEye", "rightEye"),
    "blush": ("leftCheek", "rightCheek"),
    "lip": ("lipsOuter",),
    "eyeliner": ("leftEye", "rightEye"),
}


@pytest.fixture
def fixed_finders(monkeypatch):
    """부위 찾기를 고정된 결과로 바꿔 끼운다. 빌더와 도구가 같은 쪽별 결과에서 출발하게 한다."""

    def finder(makeup):
        def find(*args, **_):
            side = "lipsOuter" if makeup == "lip" else args[4]
            return FIXED_AREAS[makeup](side)

        return find

    for makeup in ("brow", "eyeshadow", "blush", "eyeliner"):
        monkeypatch.setattr(guide_area_builder, f"find_{makeup}_area", finder(makeup))
    monkeypatch.setattr(guide_area_builder, "find_lip_area", finder("lip"))


def test_output_sub_step_is_what_build_guide_area_sends(fixed_finders):
    """나가는 영역은 서비스가 실제로 보내는 하위 단계여야 한다.

    부위 찾기를 고정하고 build_guide_area 결과와 도구 결과를 견준다. 섀도는 한 눈만 찾은 자리가
    있는 경우, 아이라인은 두 단계 연속이라 둘째 단계가 앞 단계 안내 칸을 빼는 경우까지 넣었다.
    도구처럼 앞 단계에서 넘길 칸은 부위마다 따로 둔다.
    빌더가 쪽별 결과를 하위 단계로 바꾸는 방식을 바꾸면 이 테스트가 깨져 도구도 같이 고치게 된다.
    게이지 기준(gauge)은 색 뽑기에서 오는 칸이라 영역 도구가 내지 않아 견주지 않는다.
    """
    makeups = ["brow", "eyeshadow", "blush", "lip", "eyeliner", "eyeliner"]
    steps = [
        Step(step_id=f"s{i}", order=i, start_seconds=i, end_seconds=i + 0.5, makeup=makeup)
        for i, makeup in enumerate(makeups, start=1)
    ]

    built = build_guide_area("test_01", steps, RESULT, never)

    drawn = {}
    for step, area_step in zip(steps, built.steps, strict=True):
        areas = {side: FIXED_AREAS[step.makeup](side) for side in SIDES[step.makeup]}
        sub_step, drawn[step.makeup] = output_area.output_sub_step(
            step.makeup, areas, drawn.get(step.makeup)
        )
        expected = area_step.sub_steps[0]
        assert sub_step.model_dump(exclude={"sub_step_id", "gauge"}) == expected.model_dump(
            exclude={"sub_step_id", "gauge"}
        )
    assert built.steps[-1].sub_steps[0].status == "template"


def test_brow_not_found_after_an_earlier_brow_step_sends_that_area_like_the_service(monkeypatch):
    """두 번째 눈썹 단계를 못 찾으면 도구도 서비스처럼 첫 단계 영역을 내보내고(reused_previous),
    outlined_masks도 그 마스크를 낸다."""

    def first_only(result, step_start_ms, step_end_ms, load_photo, brow, occlusion=None):
        if step_start_ms == 1000:
            return BrowArea(mask=brow_range(brow), darkening=3.0)
        return BrowArea(mask=None, darkening=0.5, reason="browColorNotFound")

    monkeypatch.setattr(guide_area_builder, "find_brow_area", first_only)
    steps = [
        Step(step_id=f"s{i}", order=i, start_seconds=i * 2 - 1, end_seconds=i * 2, makeup="brow")
        for i in (1, 2)
    ]
    built = build_guide_area("test_01", steps, RESULT, never)

    drawn = None
    reused = []
    for step, area_step in zip(steps, built.steps, strict=True):
        start = round(step.start_seconds * 1000)
        areas = {brow: first_only(None, start, 0, None, brow) for brow in ("leftBrow", "rightBrow")}
        reused.append(output_area.reused_previous("brow", areas, drawn))
        outlined = output_area.outlined_masks("brow", areas, drawn)
        sub_step, drawn = output_area.output_sub_step("brow", areas, drawn)
        assert sub_step.model_dump(exclude={"sub_step_id", "gauge"}) == area_step.sub_steps[
            0
        ].model_dump(exclude={"sub_step_id", "gauge"})
    assert reused == [False, True]
    assert np.array_equal(outlined["leftBrow"], brow_range("leftBrow"))
