"""output/guide_area.json의 영역을 단계 끝 직후 사진 위에 그려 저장한다 (개발용).

테두리의 얼굴 주소를 그 사진의 얼굴 점으로 다시 계산해, 사진 속 바른 자리에 오는지 본다.
사진은 단계 끝 직후 PHOTO_WINDOW_MS 안에서 영역의 부위(빼는 부위 포함)가 모두 화면 안인 첫 사진이다.
빼는 부위(exclude)는 그 사진의 얼굴 점 테두리를 다른 색으로 그린다. FE가 구멍으로 그리는 자리다.
바른 방향(arrow)이 있으면 먼저 바른 곳에서 나중에 바른 곳으로 화살표를 그린다.
먼저 tools/build_guide_area.py를 실행해 둔다.
--area <파일>을 주면 output/guide_area.json 대신 그 파일을 읽고 그림도 그 파일 옆에 둔다
(tools/direction_metric.py --out 결과를 볼 때).
사진 시각(초)을 붙이면 그 시각에 가장 가까운 ok 사진마다 그린다(다른 자세에서 따라가는지 보기).
저장: output/guide_area_<stepId>_check.jpg (사진의 영역 부분, 왼쪽 그대로 · 오른쪽 테두리와 구멍)
      시각을 붙이면 output/guide_area_<stepId>_<초>s_check.jpg
실행 (ai/ 폴더에서): uv run python tools/draw_guide_area.py samples/local_01_lip_seq
                     uv run python tools/draw_guide_area.py samples/local_01_lip_seq 473.0 511.0
                     uv run python tools/draw_guide_area.py samples/local_03_seq --area <파일>
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import GuideArea, MeshAnchor, RegionName
from app.schemas.landmarks import Face, FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MESH_DIR
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import usable_rows

CHECKED_FILE = Path("output") / "frames_checked.json"
GUIDE_AREA_FILE = Path("output") / "guide_area.json"
PHOTO_WINDOW_MS = 1000
LINE_COLOR = (255, 140, 0)
POINT_COLOR = (230, 0, 0)
HOLE_COLOR = (0, 120, 255)
ARROW_COLOR = (0, 200, 80)
ARROW_HEAD = 0.25
CROP_PADDING = 0.4
CHECK_SCALE = 2

Pixel = tuple[float, float]


def main() -> None:
    usage = (
        "사용법: uv run python tools/draw_guide_area.py <샘플 폴더> [사진 시각(초) …]"
        " [--area <파일>]"
    )
    args = sys.argv[1:]
    area_file = None
    if "--area" in args:
        at = args.index("--area")
        if at + 1 >= len(args):
            print(usage)
            sys.exit(1)
        area_file = Path(args[at + 1])
        args = args[:at] + args[at + 2 :]
    if not args:
        print(usage)
        sys.exit(1)
    try:
        seconds = [float(text) for text in args[1:]]
    except ValueError:
        print(usage)
        sys.exit(1)

    folder = Path(args[0])
    guide_path = area_file or folder / GUIDE_AREA_FILE
    out = guide_path.parent if area_file else folder / "output"
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
        guide_sets = [guide_set for sub_step in step.sub_steps for guide_set in sub_step.guide_sets]
        shapes = [shape for guide_set in guide_sets for shape in guide_set.guides]
        outlines = [shape.outline for shape in shapes if shape.type == "polygon"]
        ways = [[shape.start, shape.end] for shape in shapes if shape.type == "arrow"]
        if not outlines:
            continue
        holes = list(dict.fromkeys(name for guide_set in guide_sets for name in guide_set.exclude))
        regions = list(dict.fromkeys([*(guide_set.region for guide_set in guide_sets), *holes]))
        if seconds:
            rows = [_nearest_row(result, s) for s in seconds]
        else:
            rows = _first_row(result, ends[step.step_id], regions)
        if not rows:
            print(f"{step.step_id}: 단계 끝 직후에 그릴 사진이 없습니다.")
            continue
        for row in rows:
            photo = read_frame_rgb(reference, frames[row.frame_index])
            height, width = photo.shape[:2]
            lines = [
                _photo_points(outline, row.face, width, height, triangles) for outline in outlines
            ]
            hole_lines = [_region_pixels(hole, row.face, width, height) for hole in holes]
            arrows = [_photo_points(way, row.face, width, height, triangles) for way in ways]
            name = f"{step.step_id}_{row.timestamp_ms / 1000:.1f}s" if seconds else step.step_id
            path = save(photo, lines, out, name, hole_lines, arrows)
            print(
                f"{step.step_id}: {row.timestamp_ms / 1000:.1f}초 사진, "
                f"테두리 점 {sum(len(line) for line in lines)}개, 구멍 {len(hole_lines)}개, "
                f"화살표 {len(arrows)}개"
            )
            print(f"저장: {path}")
            drawn += 1
    if not drawn:
        print("그릴 영역이 없습니다.")


def save(
    photo: np.ndarray,
    lines: list[list[Pixel]],
    out: Path,
    name: str,
    holes: Sequence[list[Pixel]] = (),
    arrows: Sequence[list[Pixel]] = (),
) -> Path:
    """사진의 영역 부분을 잘라 왼쪽은 그대로, 오른쪽은 테두리·구멍·화살표를 그려 out에 저장한다.

    저장한 경로를 돌려준다. holes는 빼는 부위의 테두리로, 영역 테두리와 다른 색 선으로 그린다.
    arrows는 (먼저 바른 곳, 나중에 바른 곳) 픽셀 쌍이고 나중에 바른 곳에 화살촉을 그린다.
    """
    out.mkdir(parents=True, exist_ok=True)
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
    for hole in holes:
        points = [((x - box[0]) * CHECK_SCALE, (y - box[1]) * CHECK_SCALE) for x, y in hole]
        draw.line([*points, points[0]], fill=HOLE_COLOR, width=2)
    for arrow in arrows:
        start, end = (((x - box[0]) * CHECK_SCALE, (y - box[1]) * CHECK_SCALE) for x, y in arrow)
        draw.line([start, end], fill=ARROW_COLOR, width=4)
        for head in _arrow_head(start, end):
            draw.line([end, head], fill=ARROW_COLOR, width=4)
        draw.ellipse((start[0] - 5, start[1] - 5, start[0] + 5, start[1] + 5), fill=ARROW_COLOR)
    sheet = Image.new("RGB", (left.width * 2, left.height), "white")
    sheet.paste(left, (0, 0))
    sheet.paste(right, (left.width, 0))
    path = out / f"guide_area_{name}_check.jpg"
    sheet.save(path, quality=90)
    return path


def _arrow_head(start: Pixel, end: Pixel) -> list[Pixel]:
    """화살촉 두 날개의 끝 점. 화살표 길이의 ARROW_HEAD만큼, 뒤로 30도씩 벌린다."""
    back = np.array([start[0] - end[0], start[1] - end[1]], dtype=float) * ARROW_HEAD
    cos, sin = np.cos(np.pi / 6), np.sin(np.pi / 6)
    wings = [(cos, -sin, sin, cos), (cos, sin, -sin, cos)]
    return [
        (end[0] + a * back[0] + b * back[1], end[1] + c * back[0] + d * back[1])
        for a, b, c, d in wings
    ]


def _first_row(
    result: LandmarksResult, step_end_ms: int, regions: Sequence[RegionName]
) -> list[FrameLandmarks]:
    """단계 끝 직후 PHOTO_WINDOW_MS 안에서 regions가 모두 화면 안인 첫 사진(없으면 빈 목록)."""
    return usable_rows(result, step_end_ms, step_end_ms + PHOTO_WINDOW_MS, regions)[:1]


def _region_pixels(region: RegionName, face: Face, width: int, height: int) -> list[Pixel]:
    """부위 테두리 얼굴 점들의 사진 위 픽셀 위치. FE renderer.ts의 holeOf와 같은 점이다."""
    return [
        (face.landmarks[i].x * width, face.landmarks[i].y * height) for i in REGION_POINTS[region]
    ]


def _nearest_row(result: LandmarksResult, seconds: float) -> FrameLandmarks:
    """seconds초에 가장 가까운, 판정이 ok인 사진."""
    rows = [row for row in result.frames if row.status == "ok"]
    return min(rows, key=lambda row: abs(row.timestamp_ms - seconds * 1000))


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
