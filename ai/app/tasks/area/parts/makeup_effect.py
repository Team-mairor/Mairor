"""뽑은 영역 색에서 화장 효과와 진하기를 낸다.

화장 효과는 「화장이 그 자리 색을 얼마나 바꿨나」만 남긴 Lab 차이(ΔL·Δa·Δb)다.
영상마다 조명·필터·피부톤이 달라도 견줄 수 있게, 바른 뒤 색을 기준 색과 빼서 낸다.
기준 색(화장이 없었다면 그 자리에 있었을 색)을 무엇으로 잡는지에 따라
네 가지가 있다(EFFECT_METHODS).
around는 둘레 맨피부 색, change는 같은 칸의 바르기 전 색,
relative는 바르기 전 색에 둘레 맨피부가 전후로 바뀐 만큼(조명 변화)을 더한 색,
light는 바른 뒤 색에서 조명 변화를 자리마다 뺀 나머지(light_change)를 뺀 색이다.
바르지 않은 자리에서 읽히는 값이 light에서 가장 작아 light를 쓰고, 직후 지도가 없어
light를 못 내는 부위(아이라인)는 relative로 낸다.
진하기는 바른 뒤 색과 기준 색의 ΔE2000 거리를 0~100으로 바꾼 값이다.
근거 숫자는 docs/experiments/GAUGE_MAKEUP_EFFECT_SCALE.md에 있다.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.schemas.guide_area import GaugeDirection
from app.tasks.area.parts.area_color import AreaColor, Piece, _grown, not_skin
from app.tasks.area.parts.area_preparation import remove_lighting, rgb_to_lab

Lab = Sequence[float]
EffectMethod = Literal["around", "change", "relative", "light"]
EffectDirection = GaugeDirection

EFFECT_METHODS: tuple[EffectMethod, ...] = ("around", "change", "relative", "light")
FALLBACK_METHOD: EffectMethod = "relative"
LIGHT_GAP_CELLS = 24
FULL_STRENGTH_DELTA_E = 20.0
SAME_LIGHTNESS = 1.0
_POW_25_7 = 25.0**7


@dataclass(frozen=True)
class MakeupEffect:
    """영역 하나의 화장 효과.

    delta는 바른 뒤 색 − 기준 색의 (ΔL, Δa, Δb)다. base는 그때 쓴 기준 색의 Lab이다.
    size는 두 색의 ΔE2000 거리다.
    direction은 밝기가 SAME_LIGHTNESS보다 더 어두워졌으면 darker(쉐딩·눈썹·아이라인),
    더 밝아졌으면 lighter(하이라이트), 그 안이면 same(색만 바뀜)이다.
    strength는 진하기 0~100이다.
    method는 기준 색을 잡은 방법이다.
    """

    method: EffectMethod
    delta: tuple[float, float, float]
    base: tuple[float, float, float]
    size: float
    direction: EffectDirection
    strength: float


def delta_e_2000(first: Lab, second: Lab) -> float:
    """두 Lab 색의 CIEDE2000 거리(ΔE2000). 가중치 kL·kC·kH는 모두 1이다.

    Lab 직선 거리(ΔE76)보다 사람이 느끼는 색 차이에 가깝다. 채도가 높은 색끼리는
    같은 Lab 거리여도 덜 다르게 보이는 것, 파란 쪽 색상이 틀어지는 것을 바로잡는다.
    """
    l1, a1, b1 = first
    l2, a2, b2 = second
    mean_c = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(mean_c**7 / (mean_c**7 + _POW_25_7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p, h2p = _hue(a1p, b1), _hue(a2p, b2)
    d_l = l2 - l1
    d_c = c2p - c1p
    if c1p * c2p == 0:
        d_h = 0.0
    elif abs(h2p - h1p) <= 180:
        d_h = h2p - h1p
    elif h2p - h1p > 180:
        d_h = h2p - h1p - 360
    else:
        d_h = h2p - h1p + 360
    d_big_h = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(d_h / 2))
    mean_l = (l1 + l2) / 2
    mean_cp = (c1p + c2p) / 2
    if c1p * c2p == 0:
        mean_h = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        mean_h = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        mean_h = (h1p + h2p + 360) / 2
    else:
        mean_h = (h1p + h2p - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(mean_h - 30))
        + 0.24 * math.cos(math.radians(2 * mean_h))
        + 0.32 * math.cos(math.radians(3 * mean_h + 6))
        - 0.20 * math.cos(math.radians(4 * mean_h - 63))
    )
    d_theta = 30 * math.exp(-(((mean_h - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(mean_cp**7 / (mean_cp**7 + _POW_25_7))
    s_l = 1 + 0.015 * (mean_l - 50) ** 2 / math.sqrt(20 + (mean_l - 50) ** 2)
    s_c = 1 + 0.045 * mean_cp
    s_h = 1 + 0.015 * mean_cp * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c
    return math.sqrt(
        (d_l / s_l) ** 2
        + (d_c / s_c) ** 2
        + (d_big_h / s_h) ** 2
        + r_t * (d_c / s_c) * (d_big_h / s_h)
    )


def light_change(piece: Piece) -> np.ndarray | None:
    """영역 조각의 칸마다 전후 Lab 변화에서 조명 변화를 뺀 나머지(N × 3). 낼 수 없으면 None이다.

    전후 변화 지도에서 영역과 그 둘레 LIGHT_GAP_CELLS칸, 맨피부가 아닌 칸(not_skin)을 뺀
    피부의 변화를 넓게 흐려 자리마다의 조명 변화로 보고 뺀다(remove_lighting).
    둘레 띠 한 줄의 색으로 재는 것보다 넓은 피부를 써서, 띠에 화장이 닿거나 띠가 좁아도 덜 흔들린다.
    직후 지도가 없는 부위(아이라인)와 모름 칸을 빼면 남는 칸이 없는 조각은 None이다.
    """
    maps = piece.maps
    if maps.after is None:
        return None
    cells = piece.cells & ~maps.unknown
    if not cells.any():
        return None
    around = piece.cells if piece.around is None else piece.around
    exclude = not_skin() | _grown(around, LIGHT_GAP_CELLS)
    change = (rgb_to_lab(maps.after) - rgb_to_lab(maps.before)).astype(np.float32)
    return np.stack(
        [
            remove_lighting(change[..., channel], exclude, maps.unknown)[cells]
            for channel in range(3)
        ],
        axis=-1,
    )


def light_base(color: AreaColor, changes: Sequence[np.ndarray | None]) -> Lab | None:
    """조각들의 light_change로 잡은 기준 색. 바른 뒤 색 − 나머지의 가운데 값이다.

    조각 중 하나라도 나머지를 못 냈거나 색을 못 뽑은 영역이면 None이다.
    """
    if color.applied is None or not changes or any(change is None for change in changes):
        return None
    left = np.median(np.concatenate(changes), axis=0)
    return tuple(
        float(applied - rest) for applied, rest in zip(color.applied.lab, left, strict=True)
    )


def effect_base(color: AreaColor, method: EffectMethod = FALLBACK_METHOD) -> Lab | None:
    """method(around·change·relative)로 잡은 기준 색의 Lab. 낼 수 없으면 None이다.

    around는 둘레 맨피부의 바른 뒤 색이다. 둘레 띠가 없으면 None이다.
    change는 같은 칸의 바르기 전 색이다.
    relative는 바르기 전 색 + (둘레 맨피부 바른 뒤 색 − 둘레 맨피부 바르기 전 색)이다.
    전후로 조명·노출이 바뀐 만큼을 둘레 맨피부로 재서 바르기 전 색에 더한 것이다.
    둘레 띠가 없으면 조명 변화를 잴 수 없어 바르기 전 색을 그대로 쓴다.
    """
    if color.applied is None or color.before is None:
        return None
    if method == "around":
        return None if color.skin is None else color.skin.lab
    if method == "change" or color.skin is None or color.skin_before is None:
        return color.before.lab
    return tuple(
        before + skin - skin_before
        for before, skin, skin_before in zip(
            color.before.lab, color.skin.lab, color.skin_before.lab, strict=True
        )
    )


def makeup_effect(
    color: AreaColor, method: EffectMethod = FALLBACK_METHOD, base: Lab | None = None
) -> MakeupEffect | None:
    """AreaColor의 화장 효과와 진하기를 낸다. 색을 못 뽑았거나 기준 색이 없으면 None이다.

    base(light_base)를 넘기면 그 색을 기준으로 삼고 method는 light가 된다.
    없으면 method로 기준 색을 잡는다. relative인데 둘레 띠가 없어 바르기 전 색을 그대로 쓴
    경우 method는 change로 적힌다.
    """
    if color.applied is None or color.before is None:
        return None
    if base is not None:
        method = "light"
    else:
        base = effect_base(color, method)
        if base is None:
            return None
        if method == "relative" and (color.skin is None or color.skin_before is None):
            method = "change"
    applied = color.applied.lab
    delta = tuple(round(after - before, 2) for after, before in zip(applied, base, strict=True))
    size = delta_e_2000(base, applied)
    return MakeupEffect(
        method=method,
        delta=delta,
        base=tuple(round(value, 2) for value in base),
        size=round(size, 2),
        direction=effect_direction(delta[0]),
        strength=strength(size),
    )


def effect_direction(lightness_change: float) -> EffectDirection:
    """밝기 변화(ΔL)로 방향을 낸다. ±SAME_LIGHTNESS 안이면 same이다."""
    if lightness_change < -SAME_LIGHTNESS:
        return "darker"
    if lightness_change > SAME_LIGHTNESS:
        return "lighter"
    return "same"


def strength(size: float) -> float:
    """ΔE2000 거리(size)를 진하기 0~100으로 바꾼다.

    FULL_STRENGTH_DELTA_E에서 100이고 그보다 크면 100에 머문다. 0은 기준 색과 같은 색이다.
    어두워지는 화장과 밝아지는 화장을 같은 눈금에 올린다. 방향은 direction이 따로 말한다.
    """
    return round(min(100.0, max(0.0, size / FULL_STRENGTH_DELTA_E * 100)), 1)


def effect_record(effect: MakeupEffect | None) -> dict | None:
    """MakeupEffect를 기록에 적는 표로 바꾼다. 없으면 None이다."""
    if effect is None:
        return None
    return {
        "method": effect.method,
        "delta": list(effect.delta),
        "base": list(effect.base),
        "size": effect.size,
        "direction": effect.direction,
        "strength": effect.strength,
    }


def _hue(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 0.0
    return math.degrees(math.atan2(b, a)) % 360
