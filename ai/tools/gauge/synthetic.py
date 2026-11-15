"""정답을 아는 합성 시험 세트. 같은 맨얼굴 얼굴 지도에 조명 변화와 화장을 입힌다.

조명은 선형 RGB에 곱한다. 노출(exposure)은 세 채널에 같은 배수,
색온도(warmth)는 빨강을 올리고 파랑을 내리는 배수(음수면 반대),
초록 기(green)는 초록만 올리는 배수(음수면 자홍 조명),
한쪽 그늘(shade)은 그쪽 얼굴 끝에서 가운데로 갈수록 옅어지는 배수다.
카메라(Camera)는 조명 뒤 사진 값(sRGB)에 일어나는 처리다. 곱하기가 아니어서 조명처럼 피부 비율로
정확히 지워지지 않는다. 사진 값에서 맞추는 화이트밸런스(balance), 감마(gamma), S자 대비(contrast),
채도(saturation), 피부 밝히기(lift), 매끄럽게(smooth), 압축(jpeg)이 있다.
피부톤(skin_tone)은 조명이 아니라 얼굴 자체(알베도)를 바꾼 것이라 화장을 입히기 전에 곱한다.
화장은 조명을 입히기 전에 선형 RGB에서 안료 색으로 섞는다(불투명도 opacity). 그래서 같은 화장이
조명을 받으면 함께 어두워지거나 누레진다. 정답 화장 효과는 조명 없이 화장만 입힌 색 − 맨얼굴 색이다.
좌우는 사용자 본인 기준이다. 얼굴 지도에서 본인 왼쪽(leftEye·leftCheek)은 오른쪽 절반(x > 0.5)이다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import cv2
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
    green: float = 0.0


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
    gain[..., 1] *= 1 + light.green
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

EXTREME_LIGHTS: tuple[Light, ...] = (
    Light("darker50", exposure=0.5),
    Light("brighter40", exposure=1.4),
    Light("warm30", warmth=0.3),
    Light("cool30", warmth=-0.3),
    Light("magenta15", green=-0.15),
    Light("green15", green=0.15),
)


@dataclass(frozen=True)
class Camera:
    """카메라·화면 처리 하나. 기본값은 아무것도 하지 않는다.

    balance는 사진 값(0~1)에 곱하는 채널 배수(감마를 푼 뒤가 아니라 앞에서 맞추는 화이트밸런스),
    gamma는 사진 값의 거듭제곱(1보다 크면 어둡고 진함), contrast는 S자 곡선 세기(음수면 납작),
    saturation은 밝기를 두고 색만 늘리는 배수(선형 RGB),
    lift는 사진 값을 흰색 쪽으로 끌어올리는 비율,
    smooth는 얼굴 지도에서 흐리는 시그마(칸), jpeg는 압축 품질(0이면 압축하지 않음)이다.
    """

    name: str = "plain"
    balance: tuple[float, float, float] = (1.0, 1.0, 1.0)
    gamma: float = 1.0
    contrast: float = 0.0
    saturation: float = 1.0
    lift: float = 0.0
    smooth: float = 0.0
    jpeg: int = 0


CAMERAS: tuple[Camera, ...] = (
    Camera("plain"),
    Camera("beautyFilter", lift=0.08, smooth=1.5, saturation=0.9, jpeg=85),
    Camera("vivid", contrast=0.3, saturation=1.25),
    Camera("flat", gamma=0.85, contrast=-0.2, saturation=0.9),
    Camera("darkCurve", gamma=1.2),
    Camera("photoWarm", balance=(1.06, 1.0, 0.92)),
    Camera("photoCool", balance=(0.94, 1.0, 1.07)),
    Camera("jpeg60", jpeg=60),
)

SKIN_TONES: dict[str, tuple[float, float, float]] = {
    "same": (1.0, 1.0, 1.0),
    "lighter": (1.12, 1.18, 1.25),
    "darker": (0.62, 0.5, 0.42),
    "darkest": (0.4, 0.28, 0.2),
}


def skin_tone(face_map: np.ndarray, tone: str) -> np.ndarray:
    """얼굴 지도(sRGB uint8)의 얼굴 자체 색을 바꾼다. 선형 RGB에 SKIN_TONES 배수를 곱한다.

    멜라닌이 많을수록 파랑·초록이 빨강보다 더 줄어드는 것을 흉내 낸다. 입술·눈썹도 함께 바뀌고,
    두 눈 구멍(흰자·눈동자)은 피부가 아니라서 그대로 둔다.
    """
    gain = np.where(eye_holes(face_map.shape[0])[..., None], 1.0, np.asarray(SKIN_TONES[tone]))
    return to_srgb(to_linear(face_map) * gain)


def eye_holes(size: int) -> np.ndarray:
    """size × size 얼굴 지도에서 두 눈 구멍 칸."""
    from app.tasks.area.common.face_map import face_cells
    from tools.gauge.baseline import measured_pixels

    holes = face_cells() & ~measured_pixels()
    return cv2.resize(holes.astype(np.uint8), (size, size), interpolation=cv2.INTER_NEAREST) > 0


def apply_camera(face_map: np.ndarray, camera: Camera) -> np.ndarray:
    """조명을 받은 얼굴 지도(sRGB uint8)에 카메라 처리를 입힌다."""
    value = face_map.astype(np.float64) / 255 * np.asarray(camera.balance)
    value = np.clip(value, 0, 1) ** camera.gamma
    if camera.contrast:
        curve = value - camera.contrast * value * (1 - value) * (1 - 2 * value) * 2
        value = np.clip(curve, 0, 1)
    if camera.saturation != 1.0:
        linear = _from_display(value)
        gray = linear @ np.array([0.2126, 0.7152, 0.0722])
        linear = gray[..., None] + camera.saturation * (linear - gray[..., None])
        value = _to_display(np.clip(linear, 0, 1))
    if camera.lift:
        value = value + camera.lift * (1 - value)
    if camera.smooth > 0:
        value = cv2.GaussianBlur(value.astype(np.float32), (0, 0), camera.smooth).astype(np.float64)
    out = np.round(np.clip(value, 0, 1) * 255).astype(np.uint8)
    if camera.jpeg:
        ok, data = cv2.imencode(".jpg", out[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, camera.jpeg])
        if ok:
            out = cv2.imdecode(data, cv2.IMREAD_COLOR)[..., ::-1]
    return out


def shot(
    face_map: np.ndarray,
    light: Light,
    camera: Camera,
    makeups: Sequence[Makeup] = (),
    tone: str = "same",
) -> np.ndarray:
    """맨얼굴 지도를 피부톤 → 화장 → 조명 → 카메라 순서로 찍은 지도."""
    face = skin_tone(face_map, tone) if tone != "same" else face_map
    return apply_camera(scene(face, light, makeups), camera)


def _from_display(value: np.ndarray) -> np.ndarray:
    return np.where(value > 0.04045, ((value + 0.055) / 1.055) ** 2.4, value / 12.92)


def _to_display(linear: np.ndarray) -> np.ndarray:
    return np.where(linear > 0.0031308, 1.055 * linear ** (1 / 2.4) - 0.055, 12.92 * linear)
