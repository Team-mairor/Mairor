"""색 추출 기준 세트와 정확도 리포트.

기준 세트는 사진과 정답 색(HEX)의 목록이다. 두 가지를 쓴다.
- 합성 세트(synthetic_cases): 정답을 알고 만든 이미지다. 칩, 잡음·JPEG, 흰 배경 위 타일, 색 배경,
  하이라이트 줄, 그라데이션, 모서리 그림자, 저해상도 같은 조건과, 정답이 없어야 하는 함정
  (두 색으로 갈린 이미지, 줄무늬, 무작위 색, 너무 작은 이미지, 투명 이미지)을 섞는다.
  코드로 만들므로 바이너리 파일이 저장소에 없고, 알고리즘을 고치면 이 세트로 바로 회귀를 본다.
- 실사 세트(load_manifest): 사람이 정답을 붙인 실제 호수 사진이다. manifest.json 에
  {"cases": [{"id", "image"(manifest 기준 상대 경로), "expectedHex"(#RRGGBB 또는 null),
  "bbox"({x,y,width,height} 또는 null), "wholePhoto"(기본 false), "tags"}]} 로 적는다.
  expectedHex 가 null 이면 '믿으면 안 되는 사진'이다.

리포트는 품질 임계값별로 받아들인 건수(coverage), 받아들인 것 중 정답 오차 이내의 비율(precision),
틀린 것을 받아들인 건수(false accept)를 보여 준다. 임계값은 백엔드가 정하고, 여기서는 정한 정밀도
이상이 되는 가장 낮은 임계값을 참고로 제안할 뿐이다.
"""

import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from app.tasks.catalog.color.pixels import hex_delta_e, read_color
from app.tasks.catalog.contract import BBox

SEED = 20261105
MAX_DELTA_E = 10.0
MIN_PRECISION = 0.99
THRESHOLDS = (0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)

BASES = {
    "rose": "#C9707A",
    "coral": "#E8836B",
    "nude": "#C8A08A",
    "berry": "#8E2F4F",
    "red": "#C8102E",
    "brown": "#6B3B2A",
    "peach": "#F4B38F",
    "plum": "#5A2A4A",
    "pink": "#F2A1B8",
    "mauve": "#A5707D",
    "gold": "#C9A24B",
    "light_pink": "#F7D4DC",
}


@dataclass(frozen=True)
class ReferenceCase:
    id: str
    image: Image.Image
    expected_hex: str | None
    bbox: BBox | None = None
    whole_photo: bool = False
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    tags: tuple[str, ...]
    expected_hex: str | None
    hex: str | None
    quality: float | None
    delta_e: float | None


@dataclass(frozen=True)
class ThresholdRow:
    threshold: float
    accepted: int
    correct: int
    false_accepted: int
    coverage: float
    precision: float | None


@dataclass
class Report:
    results: list[CaseResult] = field(default_factory=list)
    rows: list[ThresholdRow] = field(default_factory=list)
    suggested: float | None = None


def _rgb(hex_value: str) -> tuple[int, int, int]:
    return tuple(int(hex_value[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _solid(color: tuple[int, int, int], size: int = 64) -> np.ndarray:
    return np.full((size, size, 3), color, dtype=np.float64)


def _image(pixels: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(pixels, 0, 255).astype("uint8"))


def _jpeg(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")


def _conditions(color: tuple[int, int, int], rng: np.random.Generator):
    yield "chip", _image(_solid(color))
    noisy = _solid(color) + rng.normal(0, 4, (64, 64, 3))
    yield "noisy_jpeg", _jpeg(_image(noisy), 60)
    for name, background in (("on_white", (255, 255, 255)), ("on_grey", (170, 170, 175))):
        canvas = _solid(background, 120)
        canvas[32:88, 32:88] = color
        yield name, _image(canvas)
    canvas = _solid((40, 90, 150), 120)
    canvas[32:88, 32:88] = color
    yield "on_blue", _image(canvas)
    stripe = _solid(color)
    stripe[8:18, :] = (250, 250, 245)
    yield "highlight", _image(stripe)
    ramp = np.linspace(-10, 10, 64)[None, :, None] * np.ones((64, 1, 3))
    yield "gradient", _image(_solid(color) + ramp)
    yy, xx = np.mgrid[0:64, 0:64]
    radius = np.hypot(yy - 31.5, xx - 31.5) / 45.0
    shade = 1 - 0.25 * np.clip(radius - 0.6, 0, 1)[..., None]
    yield "vignette", _image(_solid(color) * shade)
    low = _solid(color, 24) + rng.normal(0, 3, (24, 24, 3))
    yield "low_res", _image(low)


def _traps(rng: np.random.Generator):
    halves = _solid((201, 112, 122))
    halves[:, 32:] = (40, 80, 200)
    yield "two_halves", _image(halves)
    thirds = _solid((201, 112, 122))
    thirds[:, 21:43] = (60, 160, 90)
    thirds[:, 43:] = (230, 200, 60)
    yield "three_stripes", _image(thirds)
    yield "random_field", _image(rng.integers(0, 256, (64, 64, 3)).astype("float64"))
    yield "tiny", _image(_solid((201, 112, 122), 4))
    yield "transparent", Image.new("RGBA", (64, 64), (201, 112, 122, 0))


def synthetic_cases(seed: int = SEED) -> list[ReferenceCase]:
    rng = np.random.default_rng(seed)
    cases: list[ReferenceCase] = []
    for name, hex_value in BASES.items():
        for condition, image in _conditions(_rgb(hex_value), rng):
            cases.append(
                ReferenceCase(
                    f"{name}/{condition}", image, hex_value, tags=("synthetic", condition)
                )
            )
    for name, image in _traps(rng):
        cases.append(ReferenceCase(f"trap/{name}", image, None, tags=("synthetic", "trap", name)))
    return cases


def load_manifest(path: Path) -> list[ReferenceCase]:
    """사람이 정답을 붙인 실사 세트를 읽는다. 형식이 틀리면 ValueError다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cases: list[ReferenceCase] = []
    for entry in data["cases"]:
        expected = entry.get("expectedHex")
        if expected is not None and not (isinstance(expected, str) and len(expected) == 7):
            raise ValueError(f"{entry.get('id')}: expectedHex 는 #RRGGBB 이거나 null 이어야 한다")
        box = entry.get("bbox")
        with Image.open(path.parent / entry["image"]) as opened:
            image = opened.convert("RGBA")
        cases.append(
            ReferenceCase(
                id=entry["id"],
                image=image,
                expected_hex=expected.upper() if expected else None,
                bbox=BBox(**box) if box else None,
                whole_photo=bool(entry.get("wholePhoto", False)),
                tags=("labeled", *entry.get("tags", [])),
            )
        )
    return cases


def evaluate(cases: list[ReferenceCase]) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        reading = read_color(case.image, case.bbox, whole_photo=case.whole_photo)
        error = (
            hex_delta_e(reading.hex, case.expected_hex)
            if reading is not None and case.expected_hex
            else None
        )
        results.append(
            CaseResult(
                case_id=case.id,
                tags=case.tags,
                expected_hex=case.expected_hex,
                hex=reading.hex if reading else None,
                quality=reading.quality if reading else None,
                delta_e=round(error, 2) if error is not None else None,
            )
        )
    return results


def threshold_table(
    results: list[CaseResult],
    thresholds: tuple[float, ...] = THRESHOLDS,
    max_delta_e: float = MAX_DELTA_E,
) -> list[ThresholdRow]:
    """임계값별로 받아들인 건수와 맞은 비율. 정답이 없는 사진(함정)을 받아들이면 틀린 것이다."""
    total = len(results)
    rows: list[ThresholdRow] = []
    for threshold in thresholds:
        accepted = [r for r in results if r.quality is not None and r.quality >= threshold]
        correct = [r for r in accepted if r.delta_e is not None and r.delta_e <= max_delta_e]
        rows.append(
            ThresholdRow(
                threshold=threshold,
                accepted=len(accepted),
                correct=len(correct),
                false_accepted=len(accepted) - len(correct),
                coverage=round(len(accepted) / total, 3) if total else 0.0,
                precision=round(len(correct) / len(accepted), 3) if accepted else None,
            )
        )
    return rows


def suggest_threshold(
    rows: list[ThresholdRow], min_precision: float = MIN_PRECISION
) -> float | None:
    """정밀도가 기준 이상이 되는 가장 낮은 임계값. 그런 임계값이 없으면 None이다."""
    for row in rows:
        if row.precision is not None and row.precision >= min_precision:
            return row.threshold
    return None


def build_report(cases: list[ReferenceCase]) -> Report:
    results = evaluate(cases)
    rows = threshold_table(results)
    return Report(results=results, rows=rows, suggested=suggest_threshold(rows))


def render_markdown(report: Report, title: str = "색 추출 기준 세트 리포트") -> str:
    lines = [
        f"# {title}",
        "",
        f"- 사례 {len(report.results)}건, 오차 기준 ΔE76 ≤ {MAX_DELTA_E:g}",
        "",
    ]
    lines += [
        "| 품질 임계값 | 받아들임 | 맞음 | 틀린 걸 받아들임 | coverage | precision |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.rows:
        precision = "-" if row.precision is None else f"{row.precision:.3f}"
        lines.append(
            f"| {row.threshold:g} | {row.accepted} | {row.correct} | {row.false_accepted} "
            f"| {row.coverage:.3f} | {precision} |"
        )
    labeled = sum(1 for r in report.results if "labeled" in r.tags)
    note = (
        "실사 사례가 없다. 합성 세트는 알고리즘 회귀를 보는 용도이며 임계값의 근거가 아니다."
        if labeled == 0
        else f"실사 사례 {labeled}건 포함."
    )
    lines += ["", f"- {note}"]
    suggestion = "없음" if report.suggested is None else f"{report.suggested:g}"
    lines += [
        "",
        f"- 정밀도 {MIN_PRECISION:g} 이상이 되는 가장 낮은 임계값(참고): {suggestion}",
        "",
    ]
    worst = sorted(
        (r for r in report.results if r.delta_e is not None),
        key=lambda r: r.delta_e or 0.0,
        reverse=True,
    )[:10]
    lines += [
        "## 오차가 큰 사례",
        "",
        "| 사례 | 정답 | 읽은 값 | ΔE | 품질 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in worst:
        lines.append(f"| {r.case_id} | {r.expected_hex} | {r.hex} | {r.delta_e} | {r.quality} |")
    traps = [r for r in report.results if r.expected_hex is None]
    lines += [
        "",
        "## 정답이 없어야 하는 사진(함정)",
        "",
        "| 사례 | 읽은 값 | 품질 |",
        "| --- | --- | --- |",
    ]
    for r in traps:
        lines.append(
            f"| {r.case_id} | {r.hex or '(없음)'} | {r.quality if r.quality is not None else '-'} |"
        )
    return "\n".join(lines) + "\n"
