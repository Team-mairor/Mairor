"""사진의 한 영역에서 대표 색(HEX)을 픽셀로 계산한다. 모델에게 색을 묻지 않는다.

순서:
1. 영역을 잘라 작게 줄인다(BOX 평균). 투명한 픽셀은 뺀다.
2. 가장자리 테두리가 거의 한 색이면 그것을 배경으로 보고, 그 색과 가까운 픽셀을 뺀다.
   빼고 나서 남는 게 거의 없으면(칩이 화면을 꽉 채운 경우) 배경이 없는 것으로 본다.
3. 하이라이트(아주 밝고 색이 없는 픽셀)는 소수일 때만 뺀다. 다수면 흰색 제품이라고 본다.
4. 남은 픽셀의 Lab 중앙값에서 가까운 픽셀만 두 번 걸러 모으고, 그 픽셀의 sRGB 채널 중앙값이 HEX다.

품질(0~1)은 모은 픽셀이 얼마나 한 색으로 모이는지(homogeneity), 영역을 얼마나 차지하는지(coverage),
픽셀 수(resolution), 하이라이트·그림자로 날아간 정도(clip)를 섞는다. 임계값은 백엔드가 정한다.
영역을 모르고 사진 전체를 본 경우(whole_photo)는 제품과 배경이 섞였을 수 있어 품질을 0.3으로 막고,
거의 무채색의 밝은 값은 배경이나 투명 젤일 가능성이 커서 내보내지 않는다. 실제 에뛰드 제품 사진에서
사진 전체를 읽으면 호수 색(코랄)이 아니라 흰색 계열이 나왔고, 칸 영역을 주면 정확히 읽혔다.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.tasks.catalog.contract import BBox

METHOD = "pixel_median_lab"
METHOD_VERSION = "1"
MAX_SIDE = 160
MIN_PIXELS = 50
BORDER_SPREAD = 6.0
BORDER_SHARE = 0.9
BACKGROUND_DELTA = 8.0
CLUSTER_DELTA = 12.0
MIN_FOREGROUND_SHARE = 0.02
HIGHLIGHT_L = 92.0
HIGHLIGHT_CHROMA = 10.0
SHADOW_L = 8.0
MINORITY_HIGHLIGHT = 0.3
ONLY_CLIPPED = 0.7
CANDIDATES = 64
WHOLE_PHOTO_CAP = 0.3
NEUTRAL_LIGHT_L = 85.0
NEUTRAL_CHROMA = 8.0


@dataclass(frozen=True)
class ColorReading:
    hex: str
    quality: float
    scores: dict[str, float]


_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)
_WHITE = np.array([0.95047, 1.0, 1.08883])


def _to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB(0~255)를 CIELAB(D65)으로 바꾼다."""
    linear = rgb / 255.0
    linear = np.where(linear <= 0.04045, linear / 12.92, ((linear + 0.055) / 1.055) ** 2.4)
    xyz = linear @ _RGB_TO_XYZ.T / _WHITE
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    lightness = 116 * f[:, 1] - 16
    return np.stack([lightness, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


to_lab = _to_lab


def is_neutral_light(hex_value: str) -> bool:
    """거의 무채색이고 밝은 값인가. 배경·흰 케이스·투명 젤을 잘못 잡았을 가능성이 크다."""
    rgb = np.array([[int(hex_value[i : i + 2], 16) for i in (1, 3, 5)]], dtype=np.float64)
    lab = _to_lab(rgb)[0]
    return bool(lab[0] > NEUTRAL_LIGHT_L and np.hypot(lab[1], lab[2]) < NEUTRAL_CHROMA)


def hex_delta_e(first: str, second: str) -> float:
    """두 HEX의 CIELAB 거리(ΔE76). 기준 세트 리포트가 오차를 잴 때 쓴다."""
    rgb = np.array(
        [[int(value[i : i + 2], 16) for i in (1, 3, 5)] for value in (first, second)],
        dtype=np.float64,
    )
    lab = _to_lab(rgb)
    return float(np.linalg.norm(lab[0] - lab[1]))


def _delta(lab: np.ndarray, center: np.ndarray) -> np.ndarray:
    return np.linalg.norm(lab - center, axis=1)


def _clipped(lab: np.ndarray) -> np.ndarray:
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    return ((lab[:, 0] > HIGHLIGHT_L) & (chroma < HIGHLIGHT_CHROMA)) | (lab[:, 0] < SHADOW_L)


def _only_clipped(lab: np.ndarray) -> bool:
    """배경을 빼고 남은 게 거의 하이라이트·그림자뿐이면 배경이 아니라 제품 위의 반사다."""
    return bool(np.mean(_clipped(lab)) > ONLY_CLIPPED)


def _densest(lab: np.ndarray) -> np.ndarray:
    """후보 점 중 CLUSTER_DELTA 안에 가장 많은 픽셀을 가진 점. 색이 둘로 갈려도 큰 쪽을 고른다."""
    step = max(1, len(lab) // CANDIDATES)
    best, best_count = lab[0], -1
    for candidate in lab[::step]:
        count = int(np.count_nonzero(_delta(lab, candidate) <= CLUSTER_DELTA))
        if count > best_count:
            best, best_count = candidate, count
    return best


def _crop(image: Image.Image, bbox: BBox | None) -> Image.Image:
    if bbox is None:
        return image
    left = max(0, int(bbox.x))
    top = max(0, int(bbox.y))
    right = min(image.width, int(bbox.x + bbox.width))
    bottom = min(image.height, int(bbox.y + bbox.height))
    if right <= left or bottom <= top:
        return image.crop((0, 0, 0, 0))
    return image.crop((left, top, right, bottom))


def _prepare(image: Image.Image, bbox: BBox | None) -> tuple[np.ndarray, np.ndarray]:
    region = _crop(image.convert("RGBA"), bbox)
    if region.width == 0 or region.height == 0:
        return np.zeros((0, 0, 3)), np.zeros((0, 0), dtype=bool)
    region.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.BOX)
    pixels = np.asarray(region, dtype=np.float64)
    return pixels[..., :3], pixels[..., 3] >= 128


def _background(lab: np.ndarray, opaque: np.ndarray) -> np.ndarray | None:
    """테두리가 거의 한 색이면 그 색(Lab)을 돌려준다. 아니면 None이다."""
    height, width = opaque.shape
    if height < 4 or width < 4:
        return None
    ring = np.zeros_like(opaque)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    border = lab[ring & opaque]
    if len(border) < 8:
        return None
    center = np.median(border, axis=0)
    if np.mean(_delta(border, center) <= BORDER_SPREAD) < BORDER_SHARE:
        return None
    return center


def read_color(
    image: Image.Image, bbox: BBox | None = None, *, whole_photo: bool = False
) -> ColorReading | None:
    """영역의 대표 색. 쓸 만한 픽셀이 너무 적으면 None이다(색을 지어내지 않는다)."""
    rgb, opaque = _prepare(image, bbox)
    total = int(opaque.size)
    if total == 0 or int(opaque.sum()) < MIN_PIXELS:
        return None
    lab_all = _to_lab(rgb.reshape(-1, 3)).reshape(rgb.shape)
    valid = opaque.copy()
    background = _background(lab_all, opaque)
    if background is not None:
        foreground = opaque & (
            _delta(lab_all.reshape(-1, 3), background).reshape(opaque.shape) > BACKGROUND_DELTA
        )
        enough = foreground.sum() >= MIN_FOREGROUND_SHARE * opaque.sum()
        if enough and not _only_clipped(lab_all[foreground]):
            valid = foreground
    if int(valid.sum()) < MIN_PIXELS:
        return None
    chosen_rgb, chosen_lab = rgb[valid], lab_all[valid]
    chroma = np.hypot(chosen_lab[:, 1], chosen_lab[:, 2])
    highlight = (chosen_lab[:, 0] > HIGHLIGHT_L) & (chroma < HIGHLIGHT_CHROMA)
    clip = float(np.mean(_clipped(chosen_lab)))
    if highlight.mean() < MINORITY_HIGHLIGHT and (~highlight).sum() >= MIN_PIXELS:
        chosen_rgb, chosen_lab = chosen_rgb[~highlight], chosen_lab[~highlight]
    center = _densest(chosen_lab)
    for _ in range(2):
        near = _delta(chosen_lab, center) <= CLUSTER_DELTA
        if near.sum() < MIN_PIXELS:
            break
        center = np.median(chosen_lab[near], axis=0)
    near = _delta(chosen_lab, center) <= CLUSTER_DELTA
    if int(near.sum()) < MIN_PIXELS:
        return None
    if (
        whole_photo
        and center[0] > NEUTRAL_LIGHT_L
        and np.hypot(center[1], center[2]) < NEUTRAL_CHROMA
    ):
        return None
    red, green, blue = (int(round(v)) for v in np.median(chosen_rgb[near], axis=0))
    homogeneity = float(near.mean())
    coverage = float(near.sum() / total)
    resolution = min(1.0, float(np.sqrt(near.sum())) / 20.0)
    quality = (
        0.5 * homogeneity + 0.2 * min(1.0, coverage / 0.25) + 0.15 * resolution + 0.15 * (1 - clip)
    )
    if whole_photo:
        quality = min(quality, WHOLE_PHOTO_CAP)
    return ColorReading(
        hex=f"#{red:02X}{green:02X}{blue:02X}",
        quality=round(max(0.0, min(1.0, quality)), 3),
        scores={
            "homogeneity": round(homogeneity, 3),
            "coverage": round(coverage, 3),
            "resolution": round(resolution, 3),
            "clip": round(clip, 3),
            "pixels": float(near.sum()),
        },
    )
