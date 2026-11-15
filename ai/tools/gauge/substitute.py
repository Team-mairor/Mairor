"""대체 제품 · 제품 없음 단계에서 게이지를 고른 제품에 맞추는 파이썬 기준 구현.

튜토리얼을 시작할 때 BE가 단계마다 고른 제품을 고정한다.
실행 단계 스냅샷의 result(SAME · SUBSTITUTE · NONE), selectedColor(sRGB hex · 추정 여부),
skipped다. 가이드는 여러 사용자가 같이 쓰고 고른 제품은 사람마다 달라서,
이 규칙은 가이드 결과가 아니라 튜토리얼을 실행할 때 적용한다.
브라우저(FE)가 같은 규칙으로 게이지를 보이고, 이 파일은 기대값과 시험 데이터를 만든다.

- 같은 제품(SAME): 가이드 결과 gauge와 measure를 그대로 쓴다.
- 대체 제품(SUBSTITUTE)의 진하기 기준(basis): measure의 진하기 비율은 사용자 효과를 목표 효과
  방향으로 투영한 길이 비라서, 색 방향이 다른 대체 제품은 레퍼런스만큼 진해 보이게 발라도
  짧게(「연해요」로) 읽힌다. 그래서 대체 제품 색이 레퍼런스와 거의 같지 않으면
  레퍼런스 기준을 대체 제품 색 쪽으로 옮긴 기준(substitute_reference)으로 잰다(product).
  레퍼런스 바르기 전 색에서 대체 제품 색 쪽으로 레퍼런스 효과와 같은 ΔE2000만큼 간 색
  (toward_color)을 바른 뒤 색으로 둔 기준이다. 대체 제품 색이 레퍼런스와 거의 같으면
  (color_near ≤ NEAR_COLOR_MAX) 레퍼런스 기준 그대로다(reference). 고른 색이 추정값이어도
  옮긴 기준을 쓴다. 색이 20도 틀려도 레퍼런스 기준 그대로보다 맞았다. 색이 없으면 그대로다.
- 대체 제품의 색감은 고른 색이 추정값이 아니고 레퍼런스와 거의 같을 때만 보인다.
  그 밖에는 제품 색 차이를 늘 「다르다」고 읽거나(farColor), 색 오차를 알 수 없거나
  (estimatedColor), 견줄 색이 없다(noColor).
- 제품 없음(NONE)이나 건너뛴 단계는 게이지를 숨긴다(noProduct).
  measure의 측정 이유와 따로 둔다. 사진이 아니라 단계 전체에 정해진 일이기 때문이다.

근거 숫자는 docs/experiments/GAUGE_SUBSTITUTE_PRODUCT.md에 있다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np

from app.schemas.guide_area import GaugeReference, RegionName
from tools.gauge import measure as ms
from tools.gauge.baseline import delta_e_map
from tools.gauge.color_match import DARK_MAKEUPS, AreaSide, lab_of, linear_of_srgb

Matching = Literal["SAME", "SUBSTITUTE", "NONE"]
HideReason = Literal["noProduct"]
ColorReason = Literal["farColor", "estimatedColor", "noColor"]
Basis = Literal["reference", "product"]

NEAR_COLOR_MAX = 1.0
TOWARD_STEPS = 30


@dataclass(frozen=True)
class SelectedProduct:
    """튜토리얼 실행 단계에서 고른 제품.

    result는 BE 매칭 결과, color_hex는 selectedColor.hex(#RRGGBB),
    estimated는 selectedColor.estimated, skipped는 제품 없이 진행하기로 한 단계인지다.
    """

    result: Matching
    color_hex: str | None = None
    estimated: bool = False
    skipped: bool = False

    @classmethod
    def from_step(cls, step: Mapping[str, Any]) -> "SelectedProduct":
        """BE 실행 단계 스냅샷(result · selectedColor · skipped)에서 읽는다."""
        color = step.get("selectedColor") or {}
        return cls(
            result=step.get("result") or "NONE",
            color_hex=color.get("hex"),
            estimated=bool(color.get("estimated", False)),
            skipped=bool(step.get("skipped", False)),
        )


@dataclass(frozen=True)
class ProductRule:
    """고른 제품에 따른 게이지 보이기.

    show가 거짓이면 게이지를 숨기고 hide_reason에 이유가 든다.
    color가 거짓이면 진하기만 보이고 색감은 숨기며, 이유가 있으면 color_reason에 든다.
    near는 대체 제품일 때 잰 color_near 값이다(못 쟀으면 None).
    basis는 진하기를 잴 기준이다. reference는 가이드 결과 gauge 그대로,
    product는 대체 제품 색 쪽으로 옮긴 기준(substitute_reference)이다.
    """

    show: bool
    color: bool
    near: float | None
    hide_reason: HideReason | None
    color_reason: ColorReason | None
    basis: Basis = "reference"


@dataclass(frozen=True)
class ProductMeasure:
    """고른 제품을 반영한 게이지 값. 게이지를 숨기면 measure는 None이다."""

    rule: ProductRule
    measure: ms.Measure | None


def toward_color(gauge: GaugeReference | None, color_hex: str) -> np.ndarray | None:
    """레퍼런스 바르기 전 색에서 color_hex 쪽으로 레퍼런스 효과와 같은 ΔE2000만큼 간 색(선형 RGB).

    바르기 전 · 바른 뒤 색은 measure.reference_side와 같이 gauge.color.lab · effect.delta로 만든다.
    제품 색까지 가도 레퍼런스 효과에 못 미치면 제품 색이다. gauge에 값이 없으면 None이다.
    """
    reference = ms.reference_side(gauge)
    if reference is None:
        return None
    before, after = reference.before, reference.after
    product = linear_of_srgb(_rgb(color_hex))
    before_lab = lab_of(before)
    target = float(delta_e_map(before_lab, lab_of(after)))
    if float(delta_e_map(before_lab, lab_of(product))) < target:
        return product
    low, high = 0.0, 1.0
    for _ in range(TOWARD_STEPS):
        middle = (low + high) / 2
        size = float(delta_e_map(before_lab, lab_of(before + middle * (product - before))))
        low, high = (middle, high) if size < target else (low, middle)
    return before + (low + high) / 2 * (product - before)


def color_near(gauge: GaugeReference | None, color_hex: str) -> float | None:
    """대체 제품 색이 레퍼런스와 얼마나 다른지: toward_color와 레퍼런스 바른 뒤 색의 ΔE2000."""
    toward = toward_color(gauge, color_hex)
    if toward is None:
        return None
    after = np.asarray(gauge.color.lab, dtype=np.float64)
    return float(delta_e_map(after, lab_of(np.clip(toward, 0, None))))


def substitute_reference(gauge: GaugeReference, color_hex: str) -> GaugeReference | None:
    """대체 제품 색 쪽으로 옮긴 기준: toward_color를 바른 뒤 색(color.lab)으로 둔 gauge.

    바르기 전 색은 그대로라 effect.delta도 그 차이로 바뀐다. 가이드 결과처럼 소수 둘째 자리다.
    흰자 · 진하기 등 다른 칸은 그대로다. gauge에 값이 없으면 None이다.
    """
    toward = toward_color(gauge, color_hex)
    if toward is None:
        return None
    after = lab_of(np.clip(toward, 0, None))
    before = np.asarray(gauge.color.lab, dtype=np.float64) - np.asarray(gauge.effect.delta)
    color = gauge.color.model_copy(update={"lab": tuple(round(float(v), 2) for v in after)})
    effect = gauge.effect.model_copy(
        update={"delta": tuple(round(float(a - b), 2) for a, b in zip(after, before, strict=True))}
    )
    return gauge.model_copy(update={"color": color, "effect": effect})


def product_rule(
    gauge: GaugeReference | None, makeup: str, product: SelectedProduct
) -> ProductRule:
    """고른 제품으로 게이지를 보일지, 무엇을 기준으로 잴지, 색감을 보일지 정한다."""
    if product.result == "NONE" or product.skipped:
        return ProductRule(False, False, None, "noProduct", None)
    if product.result == "SAME":
        return ProductRule(True, True, None, None, None)
    colored = makeup not in DARK_MAKEUPS
    if not product.color_hex:
        return ProductRule(True, False, None, None, "noColor" if colored else None)
    near = color_near(gauge, product.color_hex)
    if near is None:
        return ProductRule(True, False, None, None, None)
    basis: Basis = "reference" if near <= NEAR_COLOR_MAX else "product"
    if not colored:
        return ProductRule(True, False, near, None, None, basis)
    if product.estimated:
        return ProductRule(True, False, near, None, "estimatedColor", basis)
    if basis == "product":
        return ProductRule(True, False, near, None, "farColor", basis)
    return ProductRule(True, True, near, None, None, basis)


def measure_for_product(
    gauge: GaugeReference | None,
    makeup: str,
    sides: Sequence[tuple[RegionName | None, AreaSide | None, int]],
    product: SelectedProduct,
) -> ProductMeasure:
    """measure에 고른 제품 규칙을 더한 게이지 값.

    basis가 product이면 substitute_reference로 옮긴 기준을 measure에 넘긴다.
    계산은 measure 그대로다.
    """
    rule = product_rule(gauge, makeup, product)
    if not rule.show:
        return ProductMeasure(rule, None)
    basis = substitute_reference(gauge, product.color_hex) if rule.basis == "product" else gauge
    out = ms.measure(basis, makeup, sides)
    if rule.color:
        return ProductMeasure(rule, out)
    plain = replace(
        out,
        hue=None,
        chroma=None,
        hue_same=None,
        chroma_same=None,
        sides=tuple(replace(side, hue=None, chroma=None) for side in out.sides),
    )
    return ProductMeasure(rule, plain)


def _rgb(value: str) -> np.ndarray:
    return np.array([int(value[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float64)
