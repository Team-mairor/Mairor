"""FE로 나가는 영역의 테두리 모양을 재 output/outline.json에 둔다(개발용).

시험 영상의 바른 단계마다 서비스 창(직전·직후 창을 옮기지 않은 것)으로 부위를 찾아, 서비스가 보내는
하위 단계(tools/output_area.py)의 테두리를 잰다. 재는 값은 넷이다.
- 출렁임(wiggles·turnRatio): 서비스가 보낸 점이 아니라 FE가 화면에 그리는 곡선(smooth_points)
  위에서 잰다. 점 위에서 재면 같은 모양도 점을 촘촘히 찍을수록 한 점의 꺾임이 작아져,
  매끈함이 아니라 점 개수를 재게 되기 때문이다. wiggles는 곡선이 꺾이는 방향(왼쪽·오른쪽)이
  바뀌는 횟수로, 볼록하고 매끈하면 0, 입술 산처럼 큰 오목이 하나면 2, 칸 계단을 따라 출렁이면
  수십 번이다. 튀어나온 높이가 WIGGLE_MIN_CELLS칸보다 낮은 흔들림은
  화면에서 거의 안 보여 세지 않는다.
  turnRatio는 꺾인 각도를 모두 더한 값 ÷ 360°로, 볼록하고 매끈하면 1이고 출렁일수록 커진다.
- 점 간격 고르기(spacingCv): 이웃 점 사이 거리의 표준편차 ÷ 평균. 고른 간격이면 0에 가깝다.
  FE는 모든 점을 지나는 곡선을 그려, 간격이 들쭉날쭉하면 곡선이 출렁인다.
- 넓이 차(areaChange·mismatch): FE처럼 곡선으로 칠한 영역이 서비스가 테두리를 딴 칸 표
  (output_area.outlined_masks)보다 몇 비율 많거나 적은지와, 둘이 서로 다른 칸 ÷ 칸 표 넓이.
  짝 부위·립은 가장 큰 덩어리만 테두리로 보내므로 작은 덩어리가 빠진 만큼도 여기 들어간다.
- 두께(thicknessUv·thin): FE thin-area.ts와 같은 식으로 얼굴 지도 0~1 좌표에서 넓이 × 2 ÷ 둘레.
  THIN_AREA_UV보다 얇으면 FE가 테두리 대신 얇은 띠로 그린다.
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
--occlusion·--no-store·--tag·--parts는 tools/stability_metric.py와 같다.
실행 (ai/ 폴더에서):
uv run python tools/outline_metric.py samples/local_03_seq [--occlusion <이름>] [--no-store]
    [--tag <이름>] [--parts <부위,부위>]
"""

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import AreaSubStep, RegionName
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import step_bounds, within_step
from tools.face_map_store import STORE_USAGE, split_store, tool_photos
from tools.metric_settings import (
    PARTS_USAGE,
    TAG_USAGE,
    selected_parts,
    shifted_reference,
    split_parts,
    split_tag,
    tagged_dir,
    write_result,
)
from tools.occlusion_tables import USAGE, output_dir, split_occlusion, table_finder
from tools.output_area import (
    Area,
    Zones,
    anchor_points,
    outlined_masks,
    output_area,
    smooth_points,
    step_zones,
)
from tools.stability_metric import CHECKED_FILE, FACE_MAP_KEEP, PARTS

OUTPUT_FILE = "outline.json"
THIN_AREA_UV = 0.015
WIGGLE_MIN_CELLS = 1.0

Point = tuple[float, float]


def signed_turns(points: Sequence[Point]) -> np.ndarray:
    """닫힌 꺾은선의 점마다 꺾이는 각도(도). 한쪽으로 꺾이면 +, 반대쪽이면 −다.

    같은 자리에 겹친 점은 건너뛴다.
    """
    p = np.asarray(points, dtype=float)
    edges = np.roll(p, -1, axis=0) - p
    edges = edges[np.hypot(edges[:, 0], edges[:, 1]) > 0]
    if len(edges) < 2:
        return np.zeros(0)
    before = np.roll(edges, 1, axis=0)
    cross = before[:, 0] * edges[:, 1] - before[:, 1] * edges[:, 0]
    dot = (before * edges).sum(axis=1)
    return np.degrees(np.arctan2(cross, dot))


def curve_shape(points: Sequence[Point]) -> tuple[float, int]:
    """FE가 그리는 곡선 위에서 (총 꺾임 비, 출렁임 수)를 낸다.

    곡선을 같은 방향으로 꺾이는 구간들로 나누고, 구간마다 앞뒤 끝을 이은 선에서 곡선이 가장 멀리
    벗어난 거리(튀어나온 높이)를 잰다. 높이가 WIGGLE_MIN_CELLS칸보다 낮은 구간은 빼고,
    남은 구간끼리 방향이 바뀌는 횟수를 센다. 각도로 거르면 점이 촘촘할수록 눈에 안 보이는
    잔흔들림까지 세게 되어 높이로 거른다.
    """
    curve = np.asarray(smooth_points(points), dtype=float)
    steps = np.roll(curve, -1, axis=0) - curve
    curve = curve[np.hypot(steps[:, 0], steps[:, 1]) > 0]
    turns = signed_turns(curve)
    if len(turns) < 3:
        return 0.0, 0
    ratio = float(np.abs(turns).sum() / 360)
    signs = np.sign(turns)
    starts = np.nonzero(signs != np.roll(signs, 1))[0]
    if not len(starts):
        return ratio, 0
    count = len(curve)
    order = np.roll(np.arange(count), -starts[0])
    ordered = signs[order]
    bounds = [*np.nonzero(ordered != np.roll(ordered, 1))[0], count]
    kept = [
        ordered[first]
        for first, end in zip(bounds[:-1], bounds[1:], strict=True)
        if ordered[first] != 0
        and _bulge(curve, order[(first - 1) % count], order[first:end], order[end % count])
        >= WIGGLE_MIN_CELLS
    ]
    if len(kept) < 2:
        return ratio, 0
    kept_signs = np.asarray(kept)
    return ratio, int((kept_signs != np.roll(kept_signs, 1)).sum())


def _bulge(curve: np.ndarray, before: int, inside: np.ndarray, after: int) -> float:
    """구간 앞 점과 뒤 점을 이은 선에서 구간 안 점들이 가장 멀리 벗어난 거리(칸)."""
    start, end = curve[before], curve[after]
    chord = end - start
    length = float(np.hypot(*chord))
    offsets = curve[inside] - start
    if length == 0:
        return float(np.hypot(offsets[:, 0], offsets[:, 1]).max())
    return float(np.abs(chord[0] * offsets[:, 1] - chord[1] * offsets[:, 0]).max() / length)


def spacing_cv(points: Sequence[Point]) -> float:
    """닫힌 테두리에서 이웃 점 사이 거리의 표준편차 ÷ 평균. 점이 모두 겹치면 0이다."""
    p = np.asarray(points, dtype=float)
    lengths = np.hypot(*(np.roll(p, -1, axis=0) - p).T)
    mean = float(lengths.mean())
    return 0.0 if mean == 0 else float(lengths.std() / mean)


def thickness_uv(points: Sequence[Point]) -> float:
    """FE thin-area.ts의 평균 두께. 칸 좌표를 얼굴 지도 0~1 좌표로 바꿔 |넓이 × 2| ÷ 둘레를 낸다.

    점은 칸 번호 좌표(anchor_points)라 칸 가운데(+0.5)를 MAP_SIZE로 나눠야 FE가 쓰는 uv와 같다.
    """
    uv = (np.asarray(points, dtype=float) + 0.5) / MAP_SIZE
    x, y = uv[:, 0], uv[:, 1]
    nx, ny = np.roll(x, -1), np.roll(y, -1)
    perimeter = float(np.hypot(nx - x, ny - y).sum())
    return 0.0 if perimeter == 0 else abs(float((x * ny - nx * y).sum())) / perimeter


def area_change(drawn: np.ndarray | None, outlined: np.ndarray | None) -> dict:
    """곡선으로 칠한 영역(drawn)이 테두리를 딴 칸 표(outlined)보다 넓이가 얼마나 다른지.

    areaChange는 (칠한 칸 − 칸 표 칸) ÷ 칸 표 칸, mismatch는 둘 중 한쪽에만 있는 칸 ÷ 칸 표 칸이다.
    어느 한쪽이 없거나 칸 표가 비면 두 값 모두 None이다.
    """
    if drawn is None or outlined is None or not outlined.any():
        return {"areaChange": None, "mismatch": None}
    cells = int(outlined.sum())
    return {
        "areaChange": round((int(drawn.sum()) - cells) / cells, 4),
        "mismatch": round(int((drawn ^ outlined).sum()) / cells, 4),
    }


def polygon_rows(sub_step: AreaSubStep) -> dict[RegionName, list[list[Point]]]:
    """하위 단계에서 부위마다 polygon 테두리 점(칸 좌표)들을 모은다.

    extracted가 아니면 빈 dict다.
    """
    if sub_step.status != "extracted":
        return {}
    out: dict[RegionName, list[list[Point]]] = {}
    for guide_set in sub_step.guide_sets:
        for guide in guide_set.guides:
            if guide.type == "polygon" and len(guide.outline) >= 3:
                out.setdefault(guide_set.region, []).append(anchor_points(guide.outline))
    return out


def measure_side(
    polygons: Sequence[Sequence[Point]], drawn: np.ndarray | None, outlined: np.ndarray | None
) -> dict:
    """한 쪽의 polygon들과 칠한 영역·칸 표로 출렁임·점 간격·넓이 차·두께를 낸다.

    출렁임 수는 polygon마다 세어 더하고, 총 꺾임 비와 점 간격은 polygon마다의 평균이다.
    두께는 polygon마다 재서 가장 얇은 값을 쓴다.
    아이라인처럼 한 눈에 띠가 여러 개면 하나라도 얇으면 FE가 그 띠를 얇게 그리기 때문이다.
    """
    if not polygons:
        return {"polygons": 0, "points": 0} | area_change(drawn, outlined)
    shapes = [curve_shape(p) for p in polygons]
    thickness = min(thickness_uv(p) for p in polygons)
    return {
        "polygons": len(polygons),
        "points": int(sum(len(p) for p in polygons)),
        "wiggles": sum(wiggles for _, wiggles in shapes),
        "turnRatio": round(float(np.mean([ratio for ratio, _ in shapes])), 4),
        "spacingCv": round(float(np.mean([spacing_cv(p) for p in polygons])), 4),
        "thicknessUv": round(thickness, 5),
        "thin": thickness < THIN_AREA_UV,
    } | area_change(drawn, outlined)


def measure_step(
    makeup: str,
    sides: Sequence[RegionName],
    areas: Mapping[RegionName, Area],
    drawn: np.ndarray | None,
    zones: Zones = None,
) -> tuple[list[dict], AreaSubStep, np.ndarray | None]:
    """한 단계의 쪽별 찾기 결과로 쪽마다 테두리 값을 낸다.

    (쪽 순서대로 줄, 서비스가 보낼 하위 단계, 다음 아이라인 단계가 받을 안내한 칸)을 돌려준다.
    zones는 아이섀도 단계의 바른 자리(step_zones)다.
    """
    outlined = outlined_masks(makeup, areas, drawn, zones)
    masks, sub_step, guided = output_area(makeup, areas, drawn, zones)
    polygons = polygon_rows(sub_step)
    rows = [
        {"side": side, "status": sub_step.status}
        | measure_side(polygons.get(side, []), masks.get(side), outlined.get(side))
        for side in sides
    ]
    return rows, sub_step, guided


def summarize(rows: Sequence[dict]) -> list[dict]:
    """부위마다 테두리가 나간 쪽들의 평균 출렁임·꺾임 비·점 간격·넓이 차와, 얇게 그려지는 쪽 수."""
    out = []
    for part in dict.fromkeys(row["part"] for row in rows):
        drawn = [row for row in rows if row["part"] == part and row["polygons"]]

        def mean(key: str, drawn=drawn) -> float | None:
            values = [row[key] for row in drawn if row.get(key) is not None]
            return round(float(np.mean(values)), 4) if values else None

        out.append(
            {
                "part": part,
                "drawnSides": len(drawn),
                "wiggles": mean("wiggles"),
                "turnRatio": mean("turnRatio"),
                "spacingCv": mean("spacingCv"),
                "areaChange": mean("areaChange"),
                "mismatch": mean("mismatch"),
                "thicknessUv": mean("thicknessUv"),
                "thinSides": sum(1 for row in drawn if row["thin"]),
            }
        )
    return out


def main() -> None:
    args, occlusion_name = split_occlusion(sys.argv[1:])
    args, use_store = split_store(args)
    args, tag = split_tag(args)
    args, part_names = split_parts(args)
    if len(args) != 1:
        print(
            f"사용법: uv run python tools/outline_metric.py <샘플 폴더>"
            f" {USAGE} {STORE_USAGE} {TAG_USAGE} {PARTS_USAGE}"
        )
        sys.exit(1)

    folder = Path(args[0])
    checked_path = folder / CHECKED_FILE
    if not checked_path.is_file():
        print(f"{checked_path}가 없습니다. 먼저 tools/check_frames.py를 실행하세요.")
        sys.exit(1)

    reference = shifted_reference(load_reference_input(folder))
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(checked_path.read_text(encoding="utf-8"))
    occlusion = table_finder(folder, occlusion_name)

    def load_photo(row):
        return read_frame_rgb(reference, frames[row.frame_index])

    photos = tool_photos(reference, folder, occlusion_name, load_photo, FACE_MAP_KEEP, use_store)
    rows = []
    bounds = step_bounds(reference.manifest.steps)
    zones = step_zones(folder)
    for part in selected_parts(PARTS, part_names):
        drawn = None
        for step in sorted(reference.manifest.steps, key=lambda s: s.order):
            if step.makeup != part.makeup:
                continue
            start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
            with within_step(*bounds[step.step_id]):
                areas = {
                    side: part.find(result, start, end, photos, side, occlusion)
                    for side in part.sides
                }
            measured, _, drawn = measure_step(
                part.makeup, part.sides, areas, drawn, zones.get(step.step_id)
            )
            for row in measured:
                rows.append({"part": part.name, "stepId": step.step_id} | row)
                print(
                    f"{part.name:9} {step.step_id:4} {row['side']:10} {row['status']:10}"
                    f"  출렁임 {row.get('wiggles')}  꺾임 비 {row.get('turnRatio')}"
                    f"  간격 {row.get('spacingCv')}"
                    f"  넓이 차 {row['areaChange']}  두께 {row.get('thicknessUv')}"
                )

    path = tagged_dir(output_dir(folder, occlusion_name), tag) / OUTPUT_FILE
    write_result(
        path,
        {"videoId": reference.manifest.video_id, "steps": rows, "summary": summarize(rows)},
    )
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
