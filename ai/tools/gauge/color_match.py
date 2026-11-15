"""레퍼런스 화면과 사용자 캠 화면의 색을 같은 기준으로 맞춰 두 화장을 견주는 방법들.

레퍼런스(링라이트·뷰티 필터·영상 압축)와 사용자 캠(방 조명·태블릿 자동 노출)은 같은 화장도
다른 색으로 찍는다. 화면마다 잰 영역 색(AreaSide)을 받아 두 화장을 한 바탕 위에 올려 놓고
ΔE2000으로 견준다(compare). 방법(MatchMethod.name)은 다섯 가지다.

- none: 맞추지 않고 바른 뒤 색끼리 본다.
- effect: 각자 같은 칸의 바르기 전 → 바른 뒤 Lab 차이(화장 효과)를 한 바탕 위에 얹는다.
- skin: 각자 맨피부를 기준 피부로 옮기는 색순응 변환을 바른 색에 적용한 뒤 바른 뒤 색끼리 본다.
- skinEffect: skin으로 옮긴 공간에서 effect처럼 효과끼리 본다.
- local: 각자 같은 칸의 바른 뒤 ÷ 바르기 전 비율을 한 바탕 색에 곱한다.
  그 자리의 바르기 전 색을 흰 종이 삼아 맞추는 색순응 변환과 같다.
  weight를 1보다 작게 하면 바탕 ÷ 바르기 전 배수를 weight 제곱만큼만 곱해
  효과(선형 RGB 차이)를 옮긴다.
  0이면 선형 RGB 차이를 그대로 더한다.
- mix: 바른 뒤 색 = (1 − 양) × 바르기 전 색 + 양 × 안료 색(혼합 모델)으로 보고 바른 양을 견준다.
  레퍼런스 효과에서 가장 적게 바른 양(least_paint)과 그때 안료 색을 거꾸로 구하고,
  안료 색을 사용자 화면으로 (사용자 기준 색 ÷ 레퍼런스 기준 색)^weight 배수만큼 옮긴 뒤
  레퍼런스와 같은 양을 사용자 바르기 전 색에 칠한 목표 색을 바탕 위 레퍼런스 화장으로 둔다.
  사용자가 바른 양을 그 안료 쪽으로 간 거리로 잰 양의 비율은 amount에 따로 담는다.

맞추기 기준 색(anchor)은 맨피부(skin)나 흰자(white)다. 맨피부 차이에는 조명과 피부톤이 섞여 있어
사진만으로 가를 수 없다. 흰자는 피부톤과 상관없이 거의 흰색이라 조명·카메라 차이만 담는다.
색순응 변환은 채널마다 곱하는 배수다. 배수를 곱하는 축(space)은 선형 RGB, Bradford, CAT16
세 가지이고, 얼마나 맞출지(degree)는 밝기까지(full), 색만(chroma), 절반(half)이다.
바탕(target)은 레퍼런스 쪽, 사용자 쪽, 둘의 가운데(average) 중 하나다.

같은 화장은 같은 제품을 같은 양 바른 것이다. 피부톤이 달라도 같은 양이면 같다고 읽혀야 한다.
그래서 색 있는 화장(립·블러셔·섀도 등)은 흰자 기준 mix(COLOR_METHOD)로, 검정·갈색 화장
(DARK_MAKEUPS: 눈썹·아이라인)은 사용자 바탕 local(DARK_METHOD)로 견준다(method_for).
값은 여러 영역을 한꺼번에 견줄 수 있게 모두 (… × 3) 표로 받는다.
근거 숫자는 docs/experiments/GAUGE_COLOR_MATCHING.md에 있다.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.tasks.area.parts.area_preparation import D65_WHITE, SRGB_LINEAR, SRGB_TO_XYZ
from tools.gauge.baseline import delta_e_map

MatchName = Literal["none", "effect", "skin", "skinEffect", "local", "mix"]
Space = Literal["rgb", "bradford", "cat16"]
Degree = Literal["full", "chroma", "half"]
Target = Literal["reference", "user", "average"]
Anchor = Literal["skin", "white"]

MATCH_NAMES: tuple[MatchName, ...] = ("none", "effect", "skin", "skinEffect", "local", "mix")
WEIGHTS: tuple[float, ...] = (1.0, 0.5, 0.0)
SPACES: tuple[Space, ...] = ("rgb", "bradford", "cat16")
DEGREES: tuple[Degree, ...] = ("full", "chroma", "half")
TARGETS: tuple[Target, ...] = ("reference", "user", "average")
ANCHORS: tuple[Anchor, ...] = ("skin", "white")
BRADFORD = np.array(
    [[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]]
)
CAT16 = np.array(
    [
        [0.401288, 0.650173, -0.051461],
        [-0.250268, 1.204414, 0.045854],
        [-0.002079, 0.048952, 0.953127],
    ]
)
XYZ_TO_SRGB = np.linalg.inv(SRGB_TO_XYZ)
TINY = 1e-6
LEAST_PAINT_MIN = 0.02
WHITE_SHARE = 0.25
WHITE_CLIP = 250


@dataclass(frozen=True)
class AreaSide:
    """한 화면에서 잰 영역들. 색은 모두 선형 RGB(0~1)이고 모양은 (… × 3)이다.

    before는 바르기 전 영역 색, after는 바른 뒤 영역 색, skin은 맞추기 기준으로 쓰는 맨피부 색,
    white는 맨얼굴 사진에서 잰 흰자 색(white_color)이다.
    ratio는 칸마다 바른 뒤 ÷ 바르기 전의 가운데 값이고, 없으면 after ÷ before를 쓴다.
    """

    before: np.ndarray
    after: np.ndarray
    skin: np.ndarray
    white: np.ndarray | None = None
    ratio: np.ndarray | None = None


@dataclass(frozen=True)
class MatchMethod:
    """맞추는 방법 하나. space·degree는 skin·skinEffect·local에만, target은 none·mix 말고 모두에,
    weight는 local(선형 RGB)·mix에만, anchor는 skin·skinEffect·mix에만 쓴다."""

    name: MatchName
    space: Space = "rgb"
    degree: Degree = "full"
    target: Target = "reference"
    weight: float = 1.0
    anchor: Anchor = "skin"

    @property
    def label(self) -> str:
        """결과표에 쓰는 이름."""
        if self.name == "none":
            return "none"
        if self.name == "effect":
            return f"effect/{self.target}"
        white = "/white" if self.anchor == "white" else ""
        if self.name == "mix":
            return f"mix/w{self.weight:g}{white}"
        if self.name == "local":
            tail = "" if self.weight == 1.0 else f"/w{self.weight:g}"
            return f"local/{self.space}/{self.target}{tail}"
        return f"{self.name}/{self.space}/{self.degree}/{self.target}{white}"


@dataclass(frozen=True)
class Comparison:
    """두 화장을 한 바탕에 올린 결과. 색은 Lab이고 모양은 (… × 3), 값은 (…)이다.

    base는 바탕(바르기 전) 색, reference·user는 바탕 위에 올린 두 화장 색이다.
    same은 reference와 user의 ΔE2000(0이면 같은 화장),
    ratio는 user 효과 크기 ÷ reference 효과 크기(둘 다 base에서 잰 ΔE2000),
    along은 user 효과를 reference 효과 방향에 투영한 길이 ÷ reference 효과 길이(Lab)다.
    amount는 mix에서만 낸 바른 양의 비율(사용자 ÷ 레퍼런스)이고 다른 방법은 NaN이다.
    """

    base: np.ndarray
    reference: np.ndarray
    user: np.ndarray
    same: np.ndarray
    ratio: np.ndarray
    along: np.ndarray
    amount: np.ndarray


COLOR_METHOD = MatchMethod("mix", weight=1.0, anchor="white")
DARK_METHOD = MatchMethod("local", target="user")
DARK_MAKEUPS = frozenset({"brow", "eyeliner"})


def method_for(makeup: str) -> MatchMethod:
    """화장 종류(GuideStep.makeup)마다 고른 맞추기 방법."""
    return DARK_METHOD if makeup in DARK_MAKEUPS else COLOR_METHOD


def all_methods() -> Iterator[MatchMethod]:
    """견줄 방법을 모두 낸다."""
    yield MatchMethod("none")
    for anchor in ANCHORS:
        for weight in WEIGHTS:
            yield MatchMethod("mix", weight=weight, anchor=anchor)
    for target in TARGETS:
        yield MatchMethod("effect", target=target)
        for weight in WEIGHTS[1:]:
            yield MatchMethod("local", target=target, weight=weight)
        for space in SPACES:
            yield MatchMethod("local", space=space, target=target)
            for degree in DEGREES:
                for anchor in ANCHORS:
                    yield MatchMethod("skin", space, degree, target, anchor=anchor)
                    yield MatchMethod("skinEffect", space, degree, target, anchor=anchor)


def lab_of(linear: np.ndarray) -> np.ndarray:
    """선형 RGB(0~1, … × 3)를 Lab(D65)으로 바꾼다. rgb_to_lab와 같은 식이다."""
    xyz = np.asarray(linear, dtype=np.float64) @ SRGB_TO_XYZ.T / D65_WHITE
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def linear_of_lab(lab: np.ndarray) -> np.ndarray:
    """Lab(D65, … × 3)을 선형 RGB로 바꾼다. 범위를 넘는 값은 자르지 않는다."""
    lab = np.asarray(lab, dtype=np.float64)
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], axis=-1)
    xyz = np.where(f > 6 / 29, f**3, 3 * (6 / 29) ** 2 * (f - 4 / 29)) * D65_WHITE
    return xyz @ XYZ_TO_SRGB.T


def linear_of_srgb(rgb: np.ndarray) -> np.ndarray:
    """0~255 sRGB 값(정수나 실수)을 선형 RGB로 바꾼다."""
    rgb = np.asarray(rgb)
    if rgb.dtype == np.uint8:
        return SRGB_LINEAR[rgb]
    c = rgb.astype(np.float64) / 255
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


def adaptation(
    source: np.ndarray, target: np.ndarray, space: Space = "rgb", degree: Degree = "full"
) -> np.ndarray:
    """source 색을 target 색으로 옮기는 색순응 변환(선형 RGB에 곱할 … × 3 × 3 행렬).

    space 축에서 채널마다 target ÷ source 배수를 곱한다. chroma는 밝기(Y)를 그대로 두고 색만 옮기고,
    half는 배수의 제곱근만 곱한다.
    """
    cone = _cone(space)
    source_cone = np.asarray(source, dtype=np.float64) @ cone.T
    target_cone = np.asarray(target, dtype=np.float64) @ cone.T
    gain = target_cone / np.maximum(source_cone, TINY)
    if degree == "chroma":
        luma = SRGB_TO_XYZ[1]
        keep = (np.asarray(source) @ luma) / np.maximum(np.asarray(target) @ luma, TINY)
        gain = gain * keep[..., None]
    elif degree == "half":
        gain = np.sqrt(gain)
    return np.linalg.inv(cone) @ (gain[..., :, None] * cone)


def compare(reference: AreaSide, user: AreaSide, method: MatchMethod) -> Comparison:
    """레퍼런스 화장과 사용자 화장을 method로 맞춰 한 바탕 위에서 견준다."""
    if method.name == "none":
        base = lab_of(reference.before)
        return _result(base, lab_of(reference.after), lab_of(user.after))
    if method.name == "effect":
        base = lab_of(_pick(reference.before, user.before, method.target))
        return _result(
            base,
            base + lab_of(reference.after) - lab_of(reference.before),
            base + lab_of(user.after) - lab_of(user.before),
        )
    if method.name == "mix":
        return _mix(reference, user, method)
    if method.name == "local" and method.weight != 1.0:
        base_linear = _pick(reference.before, user.before, method.target)
        return _result(
            lab_of(base_linear),
            lab_of(_moved_effect(reference, base_linear, method.weight)),
            lab_of(_moved_effect(user, base_linear, method.weight)),
        )
    if method.name == "local":
        base_linear = _pick(reference.before, user.before, method.target)
        return _result(
            lab_of(base_linear),
            lab_of(_apply(_ratio_matrix(reference, method.space), base_linear)),
            lab_of(_apply(_ratio_matrix(user, method.space), base_linear)),
        )
    ref_anchor, user_anchor = _anchor(reference, method), _anchor(user, method)
    skin = _pick(ref_anchor, user_anchor, method.target)
    to_ref = adaptation(ref_anchor, skin, method.space, method.degree)
    to_user = adaptation(user_anchor, skin, method.space, method.degree)
    ref_before, ref_after = _apply(to_ref, reference.before), _apply(to_ref, reference.after)
    user_before, user_after = _apply(to_user, user.before), _apply(to_user, user.after)
    base = lab_of(_pick(ref_before, user_before, method.target))
    if method.name == "skin":
        return _result(base, lab_of(ref_after), lab_of(user_after))
    return _result(
        base,
        base + lab_of(ref_after) - lab_of(ref_before),
        base + lab_of(user_after) - lab_of(user_before),
    )


def measure_side(
    before: np.ndarray,
    after: np.ndarray,
    area: np.ndarray,
    skin: np.ndarray,
    white: np.ndarray | None = None,
) -> AreaSide | None:
    """얼굴 지도 두 장(sRGB uint8, 같은 크기)에서 영역 하나의 AreaSide를 잰다.

    영역 색은 area 칸 sRGB의 채널별 가운데 값, skin은 skin 칸의 가운데 값, ratio는 area 칸마다
    선형 바른 뒤 ÷ 바르기 전의 가운데 값이다. white(흰자 색)는 그대로 담는다. 칸이 없으면 None이다.
    """
    if not area.any() or not skin.any():
        return None
    before_linear = SRGB_LINEAR[before[area]]
    after_linear = SRGB_LINEAR[after[area]]
    ratio = np.median(after_linear / np.maximum(before_linear, TINY), axis=0)
    return AreaSide(
        before=linear_of_srgb(np.median(before[area].astype(np.float64), axis=0)),
        after=linear_of_srgb(np.median(after[area].astype(np.float64), axis=0)),
        skin=linear_of_srgb(np.median(before[skin].astype(np.float64), axis=0)),
        white=white,
        ratio=ratio,
    )


def least_paint(before: np.ndarray, change: np.ndarray) -> np.ndarray:
    """바르기 전 색(선형)에 change만큼 바뀌려면 적어도 얼마나 발라야 하는지(0~1).

    안료 색은 채널마다 0(검정)과 1(흰색) 사이여야 하므로, 어두워진 채널은 바르기 전 색까지,
    밝아진 채널은 1까지 남은 거리로 나눈 값 중 가장 큰 것이 가장 적은 양이다.
    """
    before = np.asarray(before, dtype=np.float64)
    change = np.asarray(change, dtype=np.float64)
    darker = -change / np.maximum(before, TINY)
    lighter = change / np.maximum(1 - before, TINY)
    need = np.where(change < 0, darker, lighter).max(axis=-1)
    return np.clip(need, LEAST_PAINT_MIN, 1.0)


def _mix(reference: AreaSide, user: AreaSide, method: MatchMethod) -> Comparison:
    ref_before = np.asarray(reference.before, dtype=np.float64)
    ref_change = np.asarray(reference.after, dtype=np.float64) - ref_before
    ref_amount = least_paint(ref_before, ref_change)
    pigment = ref_before + ref_change / ref_amount[..., None]
    ratio = np.maximum(_anchor(user, method), TINY) / np.maximum(_anchor(reference, method), TINY)
    gain = ratio**method.weight
    user_before = np.asarray(user.before, dtype=np.float64)
    toward = gain * pigment - user_before
    length = np.maximum(np.sum(toward**2, axis=-1), TINY)
    user_amount = np.clip(
        np.sum((np.asarray(user.after) - user_before) * toward, axis=-1) / length, 0, None
    )
    target = user_before + ref_amount[..., None] * toward
    result = _result(lab_of(user_before), lab_of(np.clip(target, 0, None)), lab_of(user.after))
    return Comparison(
        base=result.base,
        reference=result.reference,
        user=result.user,
        same=result.same,
        ratio=result.ratio,
        along=result.along,
        amount=user_amount / ref_amount,
    )


def _moved_effect(side: AreaSide, base: np.ndarray, weight: float) -> np.ndarray:
    before = np.asarray(side.before, dtype=np.float64)
    gain = (np.maximum(base, TINY) / np.maximum(before, TINY)) ** weight
    return base + gain * (np.asarray(side.after) - before)


def white_color(face_map: np.ndarray, holes: np.ndarray) -> np.ndarray | None:
    """맨얼굴 지도(sRGB uint8)에서 흰자 색(선형 RGB). 흰자 칸이 없으면 None이다.

    화장한 뒤에는 아이라인·속눈썹이 흰자 둘레를 덮어 어둡게 읽히므로 맨얼굴(기준) 사진에서 잰다.
    """
    cells = white_cells(face_map, holes)
    if not cells.any():
        return None
    return linear_of_srgb(np.median(face_map[cells].astype(np.float64), axis=0))


def white_cells(face_map: np.ndarray, holes: np.ndarray) -> np.ndarray:
    """눈 구멍 칸 중 흰자로 볼 칸.

    밝기 위 WHITE_SHARE 칸이고, 하얗게 날아간 칸(WHITE_CLIP 이상)은 뺀다.

    흰자는 피부톤과 상관없이 거의 흰색이라 그 화면의 조명·카메라 색만 알려 준다.
    """
    pixels = face_map[holes].astype(np.float64)
    if not len(pixels):
        return holes
    light = pixels @ np.array([0.2126, 0.7152, 0.0722])
    keep = (light >= np.percentile(light, 100 * (1 - WHITE_SHARE))) & (
        pixels.max(axis=1) < WHITE_CLIP
    )
    out = np.zeros_like(holes)
    out[holes] = keep
    return out


def _anchor(side: AreaSide, method: MatchMethod) -> np.ndarray:
    if method.anchor == "white":
        if side.white is None:
            raise ValueError("흰자 기준 방법인데 흰자 색이 없다")
        return np.asarray(side.white, dtype=np.float64)
    return np.asarray(side.skin, dtype=np.float64)


def _cone(space: Space) -> np.ndarray:
    if space == "rgb":
        return np.eye(3)
    return (BRADFORD if space == "bradford" else CAT16) @ SRGB_TO_XYZ


def _pick(reference: np.ndarray, user: np.ndarray, target: Target) -> np.ndarray:
    if target == "reference":
        return np.asarray(reference, dtype=np.float64)
    if target == "user":
        return np.asarray(user, dtype=np.float64)
    return np.sqrt(np.maximum(reference, 0) * np.maximum(user, 0))


def _ratio_matrix(side: AreaSide, space: Space) -> np.ndarray:
    if space == "rgb" and side.ratio is not None:
        gain = np.asarray(side.ratio, dtype=np.float64)
        return gain[..., :, None] * np.eye(3)
    return adaptation(side.before, side.after, space)


def _apply(matrix: np.ndarray, color: np.ndarray) -> np.ndarray:
    return np.einsum("...ij,...j->...i", matrix, np.asarray(color, dtype=np.float64))


def _result(base: np.ndarray, reference: np.ndarray, user: np.ndarray) -> Comparison:
    ref_size = delta_e_map(base, reference)
    user_size = delta_e_map(base, user)
    ref_step = reference - base
    length = np.sum(ref_step**2, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(ref_size > 0, user_size / ref_size, np.nan)
        along = np.where(length > 0, np.sum((user - base) * ref_step, axis=-1) / length, np.nan)
    return Comparison(
        base=base,
        reference=reference,
        user=user,
        same=delta_e_map(reference, user),
        ratio=ratio,
        along=along,
        amount=np.full(np.shape(ratio), np.nan),
    )
