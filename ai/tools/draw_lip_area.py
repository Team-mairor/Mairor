"""샘플 폴더의 립 단계마다 바른 곳을 찾아 얼굴 지도 그림으로 저장한다 (개발용).

사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
저장: output/lip_area_<stepId>.png (흑백 마스크, 바른 곳이 흰색)
      output/lip_area_<stepId>_check.jpg (바른 뒤 지도 입술 부분, 왼쪽 그대로 · 오른쪽 바른 곳 겹침)
실행 (ai/ 폴더에서): uv run python tools/draw_lip_area.py samples/local_01_lip_seq
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
from app.tasks.area.parts.lip_area import (
    MIN_FOUND_RATIO,
    after_map,
    after_rows,
    check_lip_area,
    found_ratio,
    lip_area_on_map,
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

    for step in lip_steps:
        end_ms = round(step.end_seconds * 1000)
        rows = after_rows(result, end_ms)
        after = after_map(
            result, end_ms, lambda row: read_frame_rgb(reference, frames[row.frame_index])
        )
        if after is None:
            print(f"{step.step_id}: 단계 끝 직후에 쓸 사진이 없어 찾지 못했습니다.")
            continue
        area = lip_area_on_map(after)
        found = check_lip_area(area)
        mask_path, check_path = save(area, after, folder, step.step_id)
        times = f"{rows[0].timestamp_ms / 1000:.1f}~{rows[-1].timestamp_ms / 1000:.1f}초"
        print(
            f"{step.step_id}: 사진 {len(rows)}장({times}), 바른 칸 {int(area.sum()):,}개, "
            f"입술의 {found_ratio(area):.0%}"
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
