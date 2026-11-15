"""정답을 아는 합성 시험 세트. 같은 맨얼굴 얼굴 지도에 조명 변화와 화장을 입힌다.

조명은 선형 RGB에 곱한다. 노출(exposure)은 세 채널에 같은 배수,
색온도(warmth)는 빨강을 올리고 파랑을 내리는 배수(음수면 반대),
한쪽 그늘(shade)은 그쪽 얼굴 끝에서 가운데로 갈수록 옅어지는 배수다.
화장은 조명을 입히기 전에 선형 RGB에서 안료 색으로 섞는다(불투명도 opacity). 그래서 같은 화장이
조명을 받으면 함께 어두워지거나 누레진다. 정답 화장 효과는 조명 없이 화장만 입힌 색 − 맨얼굴 색이다.
좌우는 사용자 본인 기준이다. 얼굴 지도에서 본인 왼쪽(leftEye·leftCheek)은 오른쪽 절반(x > 0.5)이다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.tasks.area.parts.area_preparation import SRGB_LINEAR

Side = Literal["left", "right"]


@dataclass(frozen=True)
class Light:
    """조명 변화 하나. 기본값은 바뀐 것이 없는 조명이다."""

    name: str = "same"
    exposure: float = 1.0
    warmth: float = 0.0
    shade: float = 0.0
    shade_side: Side = "left"


@dataclass(frozen=True)
class Makeup:
    """화장 하나. mask는 얼굴 지도 크기 참·거짓 표, color는 안료 sRGB, opacity는 0~1이다."""

    name: str
    mask: np.ndarray
    color: tuple[int, int, int]
    opacity: float


def to_linear(face_map: np.ndarray) -> np.ndarray:
    """0~255 sRGB 지도를 0~1 선형 값으로 바꾼다."""
    return SRGB_LINEAR[face_map]


def to_srgb(linear: np.ndarray) -> np.ndarray:
    """0~1 선형 값을 0~255 sRGB 지도(uint8)로 바꾼다. 범위를 넘는 값은 자른다."""
    c = np.clip(linear, 0, 1)
    out = np.where(c > 0.0031308, 1.055 * c ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.round(out * 255).astype(np.uint8)


def light_gain(light: Light, size: int) -> np.ndarray:
    """size × size × 3 선형 RGB 배수 표."""
    gain = np.full((size, size, 3), light.exposure, dtype=np.float64)
    gain[..., 0] *= 1 + light.warmth
    gain[..., 2] *= 1 - light.warmth
    if light.shade > 0:
        x = (np.arange(size) + 0.5) / size
        edge = (1 - 2 * x) if light.shade_side == "right" else (2 * x - 1)
        depth = light.shade * np.clip(edge, 0, 1)
        gain *= (1 - depth)[None, :, None]
    return gain


def apply_makeup(face_map: np.ndarray, makeups: Sequence[Makeup]) -> np.ndarray:
    """얼굴 지도(sRGB uint8)에 화장을 차례로 섞는다."""
    linear = to_linear(face_map)
    for makeup in makeups:
        pigment = SRGB_LINEAR[np.array(makeup.color)]
        alpha = makeup.opacity * makeup.mask.astype(np.float64)[..., None]
        linear = (1 - alpha) * linear + alpha * pigment
    return to_srgb(linear)


def apply_light(face_map: np.ndarray, light: Light) -> np.ndarray:
    """얼굴 지도(sRGB uint8)에 조명 변화를 입힌다. 얼굴 밖 흰 칸도 같이 바뀐다."""
    return to_srgb(to_linear(face_map) * light_gain(light, face_map.shape[0]))


def scene(face_map: np.ndarray, light: Light, makeups: Sequence[Makeup] = ()) -> np.ndarray:
    """맨얼굴 지도에 화장을 입히고 조명을 바꾼 지도."""
    return apply_light(apply_makeup(face_map, makeups), light)


LIGHTS: tuple[Light, ...] = (
    Light("same"),
    Light("darker15", exposure=0.85),
    Light("darker30", exposure=0.7),
    Light("brighter15", exposure=1.15),
    Light("warm8", warmth=0.08),
    Light("warm15", warmth=0.15),
    Light("cool8", warmth=-0.08),
    Light("cool15", warmth=-0.15),
    Light("shadeLeft25", shade=0.25, shade_side="left"),
    Light("shadeRight25", shade=0.25, shade_side="right"),
    Light("shadeLeft40", shade=0.4, shade_side="left"),
    Light("mixed", exposure=0.85, warmth=0.08, shade=0.25, shade_side="right"),
)
