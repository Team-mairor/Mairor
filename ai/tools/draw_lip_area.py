"""샘플 폴더의 립 단계마다 바른 곳을 찾아 얼굴 지도 그림으로 저장한다 (개발용).

단계 직전·직후 사진을 서비스처럼 골라(before_rows·after_rows) 지도로 펴고, lip_area_on_maps로
바른 곳을 찾는다. 가림 표는 쓰지 않는다.
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
저장: output/lip_area_<stepId>.png (흑백 마스크, 바른 곳이 흰색)
      output/lip_area_<stepId>_check.jpg (바른 뒤 지도 입술 부분, 왼쪽 그대로 · 오른쪽 바른 곳 겹침)
실행 (ai/ 폴더에서): uv run python tools/draw_lip_area.py samples/local_03_seq
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.face_map import map_points
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import rows_to_map
from app.tasks.area.parts.lip_area import (
    MIN_FOUND_RATIO,
    after_rows,
    before_rows,
    check_lip_area,
    found_ratio,
    lip_area_on_maps,
)

CHECKED_FILE = Path("output") / "frames_checked.json"
TINT = np.array([0, 190, 255])
TINT_ALPHA = 0.5
CROP_PADDING = 0.4
CHECK_SCALE = 2


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/draw_lip_area.py <샘플 폴더>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    checked_path = folder / CHECKED_FILE
    if not checked_path.is_file():
        print(f"{checked_path}가 없습니다. 먼저 tools/check_frames.py를 실행하세요.")
        sys.exit(1)

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(checked_path.read_text(encoding="utf-8"))
    lip_steps = [step for step in reference.manifest.steps if step.makeup == "lip"]
    if not lip_steps:
        print("립 단계가 없습니다.")
        return

    def load_photo(row) -> np.ndarray:
        return read_frame_rgb(reference, frames[row.frame_index])

    for step in lip_steps:
        start_ms, end_ms = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
        befores, afters = before_rows(result, start_ms), after_rows(result, end_ms)
        if not befores or not afters:
            print(f"{step.step_id}: 단계 직전이나 직후에 쓸 사진이 없어 찾지 못했습니다.")
            continue
        after = rows_to_map(afters, load_photo)
        area = lip_area_on_maps(rows_to_map(befores, load_photo), after)
        found = check_lip_area(area)
        mask_path, check_path = save(area, after, folder, step.step_id)
        print(
            f"{step.step_id}: 사진 직전 {len(befores)}장·직후 {len(afters)}장, "
            f"바른 칸 {int(area.sum()):,}개, 입술의 {found_ratio(area):.0%}"
        )
        if found.reason is not None:
            print(f"→ 입술의 {MIN_FOUND_RATIO:.0%}도 못 찾아 기본 가이드로 갑니다 ({found.reason})")
        print(f"저장: {mask_path}, {check_path}")


def save(area: np.ndarray, after: np.ndarray, folder: Path, step_id: str) -> tuple[Path, Path]:
    """흑백 마스크와 확인 그림을 <샘플 폴더>/output에 저장하고 두 경로를 돌려준다."""
    out = folder / "output"
    out.mkdir(exist_ok=True)
    mask_path = out / f"lip_area_{step_id}.png"
    Image.fromarray((area * 255).astype(np.uint8)).save(mask_path)

    tinted = after.astype(np.float32)
    tinted[area] = tinted[area] * (1 - TINT_ALPHA) + TINT * TINT_ALPHA
    box = _lips_box()
    left = Image.fromarray(after).crop(box)
    right = Image.fromarray(tinted.astype(np.uint8)).crop(box)
    sheet = Image.new("RGB", (left.width * 2, left.height), "white")
    sheet.paste(left, (0, 0))
    sheet.paste(right, (left.width, 0))
    sheet = sheet.resize(
        (sheet.width * CHECK_SCALE, sheet.height * CHECK_SCALE), Image.Resampling.LANCZOS
    )
    check_path = out / f"lip_area_{step_id}_check.jpg"
    sheet.save(check_path, quality=90)
    return mask_path, check_path


def _lips_box() -> tuple[int, int, int, int]:
    """지도에서 입술 부분을 자를 네모. 입술 테두리 크기의 CROP_PADDING만큼 둘레를 둔다."""
    points = np.array(map_points(REGION_POINTS["lipsOuter"]))
    (left, top), (right, bottom) = points.min(axis=0), points.max(axis=0)
    pad = (right - left) * CROP_PADDING
    return int(left - pad), int(top - pad), int(right + pad), int(bottom + pad)


if __name__ == "__main__":
    main()
