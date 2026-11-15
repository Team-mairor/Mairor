import numpy as np
import pytest

from app.schemas.guide_area import GaugeColor, GaugeEffect, GaugeReference
from tools.gauge import measure as ms
from tools.gauge import substitute as sb
from tools.gauge.baseline import delta_e_map
from tools.gauge.color_match import AreaSide, lab_of, linear_of_lab, linear_of_srgb

SKIN = np.array([66.0, 14.0, 16.0])
WHITE = linear_of_srgb(np.array([205.0, 186.0, 182.0]))
RED = (190, 40, 60)
ORANGE = (205, 85, 40)
BROWN = (60, 45, 38)


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(v):02X}" for v in rgb)


def _white_hex(linear: np.ndarray) -> str:
    srgb = np.where(linear > 0.0031308, 1.055 * linear ** (1 / 2.4) - 0.055, 12.92 * linear)
    return _hex(np.round(srgb * 255))


def painted(pigment, amount: float, before_lab: np.ndarray = SKIN) -> np.ndarray:
    before = np.clip(linear_of_lab(before_lab), 0, None)
    return lab_of((1 - amount) * before + amount * linear_of_srgb(np.asarray(pigment, float)))


def gauge(pigment=RED, amount: float = 0.3) -> GaugeReference:
    after = painted(pigment, amount)
    return GaugeReference(
        color=GaugeColor(hex="#B05050", lab=tuple(np.round(after, 2))),
        effect=GaugeEffect(delta=tuple(np.round(after - SKIN, 2)), size=10.0, direction="darker"),
        strength=50.0,
        reason=None,
        white=GaugeColor(hex=_white_hex(WHITE), lab=(80.0, 3.0, 3.0)),
    )


def side(pigment, amount: float, region="lipsOuter", white=WHITE):
    before = np.clip(linear_of_lab(SKIN), 0, None)
    after = np.clip(linear_of_lab(painted(pigment, amount)), 0, None)
    return region, AreaSide(before=before, after=after, skin=before, white=white), 120


def product(result="SUBSTITUTE", color=ORANGE, estimated=False, skipped=False):
    return sb.SelectedProduct(
        result=result,
        color_hex=None if color is None else _hex(color),
        estimated=estimated,
        skipped=skipped,
    )


def test_same_product_keeps_gauge_and_measure_as_they_are():
    """같은 제품은 가이드 결과 그대로라 440 계산과 한 글자도 달라지면 안 된다."""
    sides = [side(RED, 0.3)]

    out = sb.measure_for_product(gauge(), "lip", sides, product("SAME", RED))

    assert out.rule == sb.ProductRule(True, True, None, None, None)
    assert out.measure == ms.measure(gauge(), "lip", sides)


def test_far_substitute_measures_strength_against_the_moved_reference():
    """색이 먼 대체 제품은 대체 제품 색 쪽으로 옮긴 기준으로 measure를 잰다.

    주황을 빨강과 같은 크기로 보이게(0.39) 바르면 1 근처, 같은 양(0.3)은 덜 진해 보여 연하게 읽힌다.
    """
    look = sb.measure_for_product(gauge(), "lip", [side(ORANGE, 0.39)], product())
    same_amount = sb.measure_for_product(gauge(), "lip", [side(ORANGE, 0.3)], product())
    moved = sb.substitute_reference(gauge(), _hex(ORANGE))

    assert look.rule.basis == "product"
    assert look.measure.ratio == ms.measure(moved, "lip", [side(ORANGE, 0.39)]).ratio
    assert 0.95 < look.measure.ratio < 1.05
    assert same_amount.measure.ratio < 0.837


def test_far_substitute_hides_color_that_would_always_read_different():
    """대체 제품 색이 레퍼런스와 멀면 제대로 발라도 레퍼런스와 견준 색감은 「다르다」로 나온다.

    그 헛경보를 막으려고 색감을 숨긴다. 숨기기를 빼면(받지 않은 후보) 이 시험이 걸린다.
    """
    sides = [side(ORANGE, 0.39)]
    plain = ms.measure(gauge(), "lip", sides)

    out = sb.measure_for_product(gauge(), "lip", sides, product())

    assert plain.hue_same is False or plain.chroma_same is False
    assert out.rule.color is False and out.rule.color_reason == "farColor"
    assert out.rule.near > sb.NEAR_COLOR_MAX
    assert (out.measure.hue, out.measure.chroma, out.measure.hue_same) == (None, None, None)
    assert all(s.hue is None and s.chroma is None for s in out.measure.sides)


def test_near_substitute_keeps_color_like_the_same_product():
    near_red = (193, 43, 62)
    sides = [side(near_red, 0.3)]

    out = sb.measure_for_product(gauge(), "lip", sides, product(color=near_red))

    assert out.rule.color is True and out.rule.near <= sb.NEAR_COLOR_MAX
    assert out.measure == ms.measure(gauge(), "lip", sides)


@pytest.mark.parametrize(
    ("chosen", "reason"),
    [
        (product(color=(193, 43, 62), estimated=True), "estimatedColor"),
        (product(color=None), "noColor"),
    ],
)
def test_estimated_or_missing_color_hides_only_color(chosen, reason):
    """추정 색은 오차를 알 수 없고, 색이 없으면 견줄 수 없다. 진하기는 그대로 보인다."""
    out = sb.measure_for_product(gauge(), "lip", [side(RED, 0.3)], chosen)

    assert out.rule.show is True and out.rule.color is False
    assert out.rule.color_reason == reason
    assert out.measure.ratio == pytest.approx(1.0, abs=0.01)
    assert out.measure.hue is None


@pytest.mark.parametrize(
    "chosen",
    [product("NONE", color=None, skipped=True), product(skipped=True), product("NONE", None)],
)
def test_no_product_or_skipped_step_hides_the_gauge(chosen):
    out = sb.measure_for_product(gauge(), "lip", [side(RED, 0.3)], chosen)

    assert out.measure is None
    assert out.rule == sb.ProductRule(False, False, None, "noProduct", None)


def test_dark_substitute_measures_strength_without_color():
    sides = [side(BROWN, 0.4, "leftBrow", None), side(BROWN, 0.4, "rightBrow", None)]

    out = sb.measure_for_product(gauge(BROWN, 0.4), "brow", sides, product(color=(80, 60, 50)))

    assert (out.rule.show, out.rule.color, out.rule.color_reason) == (True, False, None)
    assert out.rule.basis == "reference" and out.rule.near <= sb.NEAR_COLOR_MAX
    assert out.measure.ratio == pytest.approx(1.0, abs=1e-3)


def test_estimated_far_color_still_moves_the_reference_for_strength():
    """추정 색은 색감만 숨긴다. 진하기는 색이 20도 틀려도 옮긴 기준이 그대로보다 맞아 옮긴다."""
    out = sb.measure_for_product(
        gauge(), "lip", [side(ORANGE, 0.39)], product(color=ORANGE, estimated=True)
    )

    assert out.rule.basis == "product" and out.rule.color_reason == "estimatedColor"
    assert 0.95 < out.measure.ratio < 1.05


def test_step_without_reference_keeps_measure_reason():
    out = sb.measure_for_product(None, "lip", [side(RED, 0.3)], product())

    assert out.rule.show is True and out.rule.color is False and out.rule.near is None
    assert out.measure.reason == "noReference"


def test_reads_be_execution_step_snapshot():
    """BE 실행 단계 스냅샷(ExecutionSelectionAssembler)의 모양 그대로 읽는다."""
    none = sb.SelectedProduct.from_step(
        {"result": "NONE", "selectedColor": None, "skipped": True, "noneReason": "NOT_SELECTED"}
    )
    substitute = sb.SelectedProduct.from_step(
        {
            "result": "SUBSTITUTE",
            "selectedColor": {
                "colorSpace": "sRGB",
                "hex": "#CD5528",
                "source": "CATALOG",
                "estimated": False,
            },
            "skipped": False,
        }
    )

    assert none == sb.SelectedProduct("NONE", None, False, True)
    assert substitute == sb.SelectedProduct("SUBSTITUTE", "#CD5528", False, False)


def test_toward_color_moves_along_product_color_by_the_reference_effect_size():
    reference = gauge()
    before = np.clip(
        linear_of_lab(np.asarray(reference.color.lab) - reference.effect.delta), 0, None
    )
    after = np.clip(linear_of_lab(np.asarray(reference.color.lab)), 0, None)
    orange = linear_of_srgb(np.asarray(ORANGE, float))

    toward = sb.toward_color(reference, _hex(ORANGE))

    step = (toward - before) / (orange - before)
    assert np.allclose(step, step[0], atol=1e-6) and 0 < step[0] < 1
    assert float(delta_e_map(lab_of(before), lab_of(toward))) == pytest.approx(
        float(delta_e_map(lab_of(before), lab_of(after))), abs=1e-3
    )


def test_toward_color_stops_at_product_color_when_it_cannot_reach_the_effect():
    pale = (172, 128, 118)

    toward = sb.toward_color(gauge(RED, 0.6), _hex(pale))

    assert np.allclose(toward, linear_of_srgb(np.asarray(pale, float)))


def test_reference_basis_would_misread_a_far_substitute():
    """measure의 비율은 목표 효과 방향으로 투영한 길이 비라, 레퍼런스 기준 그대로면 색 방향이 다른
    대체 제품을 같은 크기로 보이게 발라도 1에서 벗어난다(받지 않은 후보). 방향에 따라 짧게도
    길게도 읽힌다.

    옮긴 기준을 빼면 바로 위 시험들이 걸린다.
    """
    sides = [side(ORANGE, 0.39)]

    kept = sb.measure_for_product(gauge(), "lip", sides, product()).measure.ratio
    plain = ms.measure(gauge(), "lip", sides).ratio

    assert abs(plain - 1) > 0.1
    assert abs(kept - 1) < 0.05
