import numpy as np
import pytest

from app.tasks.area.common.face_map import MAP_SIZE
from app.tasks.area.guide_area_builder import step_colors
from app.tasks.area.parts.area_color import AreaColor, Color, Piece, StepMaps, StepNotes
from app.tasks.area.parts.area_preparation import rgb_to_lab
from app.tasks.area.parts.makeup_effect import (
    EFFECT_METHODS,
    FULL_STRENGTH_DELTA_E,
    LIGHT_GAP_CELLS,
    SAME_LIGHTNESS,
    delta_e_2000,
    effect_base,
    effect_direction,
    effect_record,
    light_base,
    light_change,
    makeup_effect,
    strength,
)

SHARMA_PAIRS = (
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0010, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0011, -2.4900), 4.7461),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
)

SKIN = (232, 192, 172)
DIM_SKIN = (212, 172, 152)
BLUSH = (235, 150, 150)
DIM_BLUSH = (215, 130, 130)
SHADING = (190, 150, 130)
HIGHLIGHT = (250, 225, 210)


def color(rgb: tuple[int, int, int]) -> Color:
    lab = rgb_to_lab(np.array(rgb, dtype=np.uint8))
    return Color(rgb=rgb, hex="#000000", lab=(float(lab[0]), float(lab[1]), float(lab[2])))


def area(applied, before, skin=None, skin_before=None) -> AreaColor:
    return AreaColor(
        applied=color(applied),
        before=color(before),
        skin=None if skin is None else color(skin),
        skin_before=None if skin_before is None else color(skin_before),
        cells=100,
    )


@pytest.mark.parametrize(("first", "second", "expected"), SHARMA_PAIRS)
def test_delta_e_2000_matches_published_pairs(first, second, expected) -> None:
    """CIEDE2000 논문(Sharma 2005)의 시험 쌍 34개다.

    색상 각도가 갈리는 자리까지 식을 그대로 옮겼는지 본다.
    """
    assert delta_e_2000(first, second) == pytest.approx(expected, abs=5e-5)
    assert delta_e_2000(second, first) == pytest.approx(expected, abs=5e-5)


def test_delta_e_2000_is_zero_for_same_color() -> None:
    """같은 색의 거리가 0이어야 진하기 0이 「화장 없음」이 된다."""
    assert delta_e_2000((63.2, 17.5, 11.0), (63.2, 17.5, 11.0)) == 0.0


def test_delta_e_2000_between_grays_is_weighted_lightness() -> None:
    """무채색끼리는 밝기 항만 남는다. 밝기 가중치를 손으로 계산한 값과 맞춘다."""
    lightness_weight = 1 + 0.015 * (55 - 50) ** 2 / (20 + (55 - 50) ** 2) ** 0.5

    assert delta_e_2000((50.0, 0.0, 0.0), (60.0, 0.0, 0.0)) == pytest.approx(10 / lightness_weight)


def test_change_uses_color_before_applying() -> None:
    """change 방법의 기준 색이 같은 칸의 바르기 전 색인지 본다."""
    one = area(BLUSH, SKIN, SKIN, SKIN)

    assert effect_base(one, "change") == one.before.lab


def test_around_uses_skin_band_after_applying() -> None:
    """around 방법의 기준 색이 둘레 맨피부의 바른 뒤 색인지 본다."""
    one = area(BLUSH, SKIN, DIM_SKIN, SKIN)

    assert effect_base(one, "around") == one.skin.lab


def test_around_needs_skin_band() -> None:
    """둘레 띠가 없으면 기준 색을 지어내지 않고 효과를 내지 않아야 한다."""
    assert effect_base(area(BLUSH, SKIN), "around") is None
    assert makeup_effect(area(BLUSH, SKIN), "around") is None


def test_relative_adds_skin_band_shift_to_before() -> None:
    """둘레 맨피부가 어두워진 만큼 기준 색도 어두워져야 조명 변화가 효과에 섞이지 않는다."""
    one = area(DIM_BLUSH, SKIN, DIM_SKIN, SKIN)

    base = effect_base(one, "relative")

    assert base == pytest.approx(one.skin.lab)


def test_relative_cancels_dimmed_lighting() -> None:
    """같은 화장인데 조명만 어두워진 경우다.

    change보다 relative가 조명 그대로일 때의 효과에 가까워야 한다.
    """
    steady = makeup_effect(area(BLUSH, SKIN, SKIN, SKIN), "relative")
    dimmed = makeup_effect(area(DIM_BLUSH, SKIN, DIM_SKIN, SKIN), "relative")
    raw = makeup_effect(area(DIM_BLUSH, SKIN, DIM_SKIN, SKIN), "change")

    assert abs(dimmed.delta[0] - steady.delta[0]) < abs(raw.delta[0] - steady.delta[0])
    assert abs(dimmed.size - steady.size) < abs(raw.size - steady.size)


def test_relative_falls_back_to_before_without_band() -> None:
    """둘레 띠가 없으면 조명 변화를 잴 수 없어 바르기 전 색을 그대로 쓴다."""
    one = area(BLUSH, SKIN)

    assert effect_base(one, "relative") == one.before.lab


def test_no_makeup_gives_zero_effect() -> None:
    """네 색이 모두 같으면 어느 방법에서도 효과·진하기가 0이고 방향은 same이어야 한다."""
    for method in EFFECT_METHODS:
        effect = makeup_effect(area(SKIN, SKIN, SKIN, SKIN), method)

        assert effect.delta == (0.0, 0.0, 0.0)
        assert effect.size == 0.0
        assert effect.strength == 0.0
        assert effect.direction == "same"


def test_lighting_only_change_gives_zero_strength() -> None:
    """영역과 둘레가 똑같이 어두워졌으면 화장이 아니라 조명이다. 진하기가 0이어야 한다."""
    effect = makeup_effect(area(DIM_SKIN, SKIN, DIM_SKIN, SKIN), "relative")

    assert effect.strength == 0.0


def test_no_effect_without_colors() -> None:
    """색을 못 뽑은 영역(noArea·colorSpread)에서 숫자를 지어내면 안 된다."""
    assert makeup_effect(AreaColor(reason="noArea")) is None
    assert makeup_effect(AreaColor(reason="colorSpread", spread=3.0)) is None
    assert effect_record(None) is None


def test_direction_tells_darker_from_lighter() -> None:
    """쉐딩처럼 어두워지는 화장과 하이라이트처럼 밝아지는 화장을 방향으로 가른다."""
    assert makeup_effect(area(SHADING, SKIN, SKIN, SKIN)).direction == "darker"
    assert makeup_effect(area(HIGHLIGHT, SKIN, SKIN, SKIN)).direction == "lighter"


def test_direction_is_same_within_lightness_margin() -> None:
    """밝기 변화가 SAME_LIGHTNESS 안이면 색만 바뀐 화장이다. 경계 값 양쪽을 본다."""
    assert effect_direction(SAME_LIGHTNESS) == "same"
    assert effect_direction(-SAME_LIGHTNESS) == "same"
    assert effect_direction(SAME_LIGHTNESS + 0.01) == "lighter"
    assert effect_direction(-SAME_LIGHTNESS - 0.01) == "darker"


def test_darker_and_lighter_share_one_scale() -> None:
    """진하기는 방향과 상관없이 0보다 커야 게이지 하나로 두 방향을 다 그린다."""
    darker = makeup_effect(area(SHADING, SKIN, SKIN, SKIN))
    lighter = makeup_effect(area(HIGHLIGHT, SKIN, SKIN, SKIN))

    assert darker.strength > 0
    assert lighter.strength > 0


def test_strength_is_linear_and_clamped() -> None:
    """진하기가 거리에 비례하고 FULL_STRENGTH_DELTA_E를 넘어도 100에 머무는지 본다."""
    assert strength(0.0) == 0.0
    assert strength(FULL_STRENGTH_DELTA_E / 2) == 50.0
    assert strength(FULL_STRENGTH_DELTA_E) == 100.0
    assert strength(FULL_STRENGTH_DELTA_E * 3) == 100.0


def test_deeper_color_gives_larger_strength() -> None:
    """같은 피부에 더 진한 색을 올리면 진하기가 커져야 한다."""
    light = makeup_effect(area((234, 175, 165), SKIN, SKIN, SKIN))
    deep = makeup_effect(area(BLUSH, SKIN, SKIN, SKIN))

    assert deep.strength > light.strength


def test_record_has_method_and_effect_fields() -> None:
    """기록 칸 이름은 도구와 뒤 작업이 읽는 약속이다. 빠지거나 바뀌지 않았는지 본다."""
    effect = makeup_effect(area(BLUSH, SKIN, SKIN, SKIN))

    record = effect_record(effect)

    assert record == {
        "method": effect.method,
        "delta": list(effect.delta),
        "base": list(effect.base),
        "size": effect.size,
        "direction": effect.direction,
        "strength": effect.strength,
    }


BOX = (slice(600, 660), slice(300, 380))


def box_mask() -> np.ndarray:
    mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    mask[BOX] = True
    return mask


def piece(before_skin, after_skin, painted, with_after=True) -> Piece:
    before = np.full((MAP_SIZE, MAP_SIZE, 3), before_skin, dtype=np.uint8)
    after = np.full((MAP_SIZE, MAP_SIZE, 3), after_skin, dtype=np.uint8)
    after[BOX] = painted
    maps = StepMaps(
        before=before,
        after=after if with_after else None,
        unknown=np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool),
        after_rows=(),
        load_photo=None,
        occlusion=None,
    )
    return Piece(box_mask(), maps)


def test_light_change_equals_raw_change_under_steady_light() -> None:
    """둘레 피부가 안 바뀌었으면 뺄 조명 변화가 없다. 영역 칸의 전후 변화가 그대로 나와야 한다."""
    one = piece(SKIN, SKIN, BLUSH)

    change = light_change(one)

    expected = rgb_to_lab(np.array(BLUSH, dtype=np.uint8)) - rgb_to_lab(
        np.array(SKIN, dtype=np.uint8)
    )
    assert change.shape == (int(box_mask().sum()), 3)
    assert np.median(change, axis=0) == pytest.approx(expected, abs=0.05)


def test_light_change_removes_face_wide_dimming() -> None:
    """얼굴 전체가 어두워진 만큼이 빠져야 한다.

    조명 그대로일 때와의 밝기 차이가 빼지 않았을 때의 3분의 1 아래인지 본다.
    """
    steady = np.median(light_change(piece(SKIN, SKIN, BLUSH)), axis=0)
    dimmed = np.median(light_change(piece(SKIN, DIM_SKIN, DIM_BLUSH)), axis=0)

    raw = rgb_to_lab(np.array(DIM_BLUSH, dtype=np.uint8)) - rgb_to_lab(
        np.array(SKIN, dtype=np.uint8)
    )
    assert abs(dimmed[0] - steady[0]) < abs(raw[0] - steady[0]) / 3


def test_light_change_is_near_zero_without_makeup() -> None:
    """조명만 바뀐 자리의 나머지가 0에 가까워야 바르지 않은 단계가 진하기 0으로 읽힌다."""
    change = light_change(piece(SKIN, DIM_SKIN, DIM_SKIN))

    assert np.abs(np.median(change, axis=0)).max() < 0.1


def test_light_change_needs_after_map() -> None:
    """직후 지도가 없는 부위(아이라인)는 None이어야 둘레 맨피부 방법으로 넘어간다."""
    assert light_change(piece(SKIN, SKIN, BLUSH, with_after=False)) is None


def test_light_change_ignores_makeup_just_outside_area() -> None:
    """영역 바로 밖으로 번진 화장이 조명 변화로 세이면 효과가 작게 읽힌다.

    둘레 LIGHT_GAP_CELLS 안은 재지 않아야 한다.
    """
    one = piece(SKIN, SKIN, BLUSH)
    ring = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    ring[
        BOX[0].start - LIGHT_GAP_CELLS // 2 : BOX[0].stop + LIGHT_GAP_CELLS // 2,
        BOX[1].start - LIGHT_GAP_CELLS // 2 : BOX[1].stop + LIGHT_GAP_CELLS // 2,
    ] = True
    one.maps.after[ring & ~box_mask()] = BLUSH

    change = np.median(light_change(one), axis=0)

    clean = np.median(light_change(piece(SKIN, SKIN, BLUSH)), axis=0)
    assert change == pytest.approx(clean, abs=0.05)


def test_light_base_is_applied_minus_median_change() -> None:
    """기준 색 = 바른 뒤 색 − 나머지의 가운데 값이라는 정의를 그대로 확인한다."""
    one = piece(SKIN, DIM_SKIN, DIM_BLUSH)
    found = area(DIM_BLUSH, SKIN, DIM_SKIN, SKIN)
    change = light_change(one)

    base = light_base(found, [change])

    left = np.median(change, axis=0)
    assert base == pytest.approx(tuple(np.subtract(found.applied.lab, left)))


def test_light_base_is_none_when_any_piece_is_missing() -> None:
    """조각 하나라도 나머지가 없으면 섞어 내지 않는다.

    좌우 합친 줄에서 한쪽만 쓰면 기준이 달라진다.
    """
    found = area(BLUSH, SKIN, SKIN, SKIN)

    assert light_base(found, []) is None
    assert light_base(found, [None]) is None
    assert light_base(AreaColor(reason="noArea"), [np.zeros((3, 3))]) is None


def test_given_base_is_recorded_as_light() -> None:
    """기준 색을 넘기면 방법이 light로 적힌다.

    어두워진 조명에서도 효과 크기가 조명 그대로일 때와 비슷해야 한다.
    """
    found = area(DIM_BLUSH, SKIN, DIM_SKIN, SKIN)
    base = light_base(found, [light_change(piece(SKIN, DIM_SKIN, DIM_BLUSH))])

    effect = makeup_effect(found, base=base)

    steady = makeup_effect(area(BLUSH, SKIN, SKIN, SKIN), "change")
    assert effect.method == "light"
    assert effect.size == pytest.approx(steady.size, abs=0.6)


def test_method_field_tells_which_base_was_used() -> None:
    """어느 기준 색으로 낸 값인지 기록에 남아야 방법이 다른 줄끼리 섞어 읽지 않는다."""
    assert makeup_effect(area(BLUSH, SKIN, SKIN, SKIN)).method == "relative"
    assert makeup_effect(area(BLUSH, SKIN)).method == "change"
    assert makeup_effect(area(BLUSH, SKIN), "change").method == "change"


def test_step_colors_attaches_effect_to_each_color_record() -> None:
    """색 기록 세 줄(좌·우·합침)마다 효과가 붙는다.

    기준 색은 light이고, 더 진하게 바른 볼의 진하기가 더 커야 한다.
    """
    from tests.test_area_color import cheek_maps, cheek_sub_step

    records = step_colors("s1", [cheek_sub_step()], cheek_maps())

    left, right, both = (record["effect"] for record in records)
    assert {left["method"], right["method"], both["method"]} == {"light"}
    assert right["strength"] > left["strength"] > 0
    assert both["strength"] > 0


def test_step_colors_writes_no_effect_for_template_sub_step() -> None:
    """기본 가이드 단계는 색이 없다.

    효과 칸은 있되 비어 있어야 읽는 쪽이 칸 유무로 갈리지 않는다.
    """
    from tests.test_area_color import template_sub_step

    sub_step = template_sub_step("s1-1", "blush", ["blushColorNotFound"])

    records = step_colors("s1", [sub_step], StepNotes())

    assert records[0]["reason"] == "noArea"
    assert records[0]["effect"] is None
