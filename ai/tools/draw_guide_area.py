"""output/guide_area.json의 영역을 그 단계 분석에 쓴 첫 사진 위에 그려 저장한다 (개발용).

테두리의 얼굴 주소를 그 사진의 얼굴 점으로 다시 계산해, 사진 속 입술 위 제자리에 오는지 본다.
먼저 tools/build_guide_area.py를 실행해 둔다.
저장: output/guide_area_<stepId>_check.jpg (사진의 영역 부분, 왼쪽 그대로 · 오른쪽 테두리)
실행 (ai/ 폴더에서): uv run python tools/draw_guide_area.py samples/local_01_lip_seq
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import GuideArea, MeshAnchor
from app.schemas.landmarks import Face, LandmarksResult
from app.services.face_map import MESH_DIR
from app.services.lip_area import after_rows
from app.services.reference_input import load_reference_input, read_frame_rgb

CHECKED_FILE = Path("output") / "frames_checked.json"
GUIDE_AREA_FILE = Path("output") / "guide_area.json"
LINE_COLOR = (255, 140, 0)
POINT_COLOR = (230, 0, 0)
CROP_PADDING = 0.4
CHECK_SCALE = 2

Pixel = tuple[float, float]


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/draw_guide_area.py <샘플 폴더>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    guide_path = folder / GUIDE_AREA_FILE
    if not guide_path.is_file():
        print(f"{guide_path}가 없습니다. 먼저 tools/build_guide_area.py를 실행하세요.")
        sys.exit(1)

    area = GuideArea.model_validate_json(guide_path.read_text(encoding="utf-8"))
    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    ends = {step.step_id: round(step.end_seconds * 1000) for step in reference.manifest.steps}
    result = LandmarksResult.model_validate_json(
        (folder / CHECKED_FILE).read_text(encoding="utf-8")
    )
    triangles = _triangles()

    drawn = 0
    for step in area.steps:
        outlines = [
            shape.outline
            for sub_step in step.sub_steps
            for guide_set in sub_step.guide_sets
            for shape in guide_set.guides
        ]
        if not outlines:
            continue
        rows = after_rows(result, ends[step.step_id])
        if not rows:
            print(f"{step.step_id}: 단계 끝 직후에 그릴 사진이 없습니다.")
            continue
        row = rows[0]
        photo = read_frame_rgb(reference, frames[row.frame_index])
        height, width = photo.shape[:2]
        lines = [_photo_points(outline, row.face, width, height, triangles) for outline in outlines]
        path = save(photo, lines, folder, step.step_id)
        print(
            f"{step.step_id}: {row.timestamp_ms / 1000:.1f}초 사진, "
            f"테두리 점 {sum(len(line) for line in lines)}개"
        )
        print(f"저장: {path}")
        drawn += 1
    if not drawn:
        print("그릴 영역이 없습니다.")


def save(photo: np.ndarray, lines: list[list[Pixel]], folder: Path, step_id: str) -> Path:
    """사진의 영역 부분을 잘라 왼쪽은 그대로, 오른쪽은 테두리를 그려 저장하고 경로를 돌려준다."""
    out = folder / "output"
    out.mkdir(exist_ok=True)
    height, width = photo.shape[:2]
    box = _box(lines, width, height)
    crop = Image.fromarray(photo).crop(box)
    left = crop.resize(
        (crop.width * CHECK_SCALE, crop.height * CHECK_SCALE), Image.Resampling.LANCZOS
    )
    right = left.copy()
    draw = ImageDraw.Draw(right)
    for line in lines:
        points = [((x - box[0]) * CHECK_SCALE, (y - box[1]) * CHECK_SCALE) for x, y in line]
        draw.line([*points, points[0]], fill=LINE_COLOR, width=2)
        for x, y in points:
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=POINT_COLOR)
    sheet = Image.new("RGB", (left.width * 2, left.height), "white")
    sheet.paste(left, (0, 0))
    sheet.paste(right, (left.width, 0))
    path = out / f"guide_area_{step_id}_check.jpg"
    sheet.save(path, quality=90)
    return path


def _photo_points(
    outline: list[MeshAnchor], face: Face, width: int, height: int, triangles: list[list[int]]
) -> list[Pixel]:
    """얼굴 주소들을 사진 위 픽셀 위치로 바꾼다.

    삼각형 세 꼭짓점의 얼굴 점 위치를 비율로 섞는다.
    FE overlay/mesh.ts의 resolveAnchor와 같은 계산이다.
    """
    points = []
    for anchor in outline:
        corners = [face.landmarks[i] for i in triangles[anchor.triangle]]
        x = sum(ratio * corner.x for ratio, corner in zip(anchor.bary, corners, strict=True))
        y = sum(ratio * corner.y for ratio, corner in zip(anchor.bary, corners, strict=True))
        points.append((x * width, y * height))
    return points


def _triangles() -> list[list[int]]:
    """공유 얼굴 메시의 삼각형 목록. 배열 위치가 MeshAnchor.triangle 번호다."""
    data = json.loads((MESH_DIR / "triangles.v1.json").read_text(encoding="utf-8"))
    return data["triangles"]


def _box(lines: list[list[Pixel]], width: int, height: int) -> tuple[int, int, int, int]:
    """테두리를 감싸는 네모. 테두리 가로의 CROP_PADDING만큼 둘레를 두고 사진 안으로 자른다."""
    xs = [x for line in lines for x, _ in line]
    ys = [y for line in lines for _, y in line]
    pad = (max(xs) - min(xs)) * CROP_PADDING
    return (
        max(0, int(min(xs) - pad)),
        max(0, int(min(ys) - pad)),
        min(width, int(max(xs) + pad)),
        min(height, int(max(ys) + pad)),
    )


if __name__ == "__main__":
    main()
