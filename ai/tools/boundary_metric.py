"""찾은 영역이 입술·눈썹·눈 경계를 넘거나 덜 덮는지 분할 모델로 재 output/boundary.json에 둔다.

개발용이다. 얼굴 분할 모델은 BiSeNet(CelebAMask-HQ로 학습, 19개 부위)을 쓴다. 저장소에 두지 않으므로
MODEL_URL에서 받아 경로를 넘기고, 파일 지문이 MODEL_SHA256과 같은지 먼저 확인한다.
실제로 바른 단계마다 서비스 찾기 함수로 영역을 찾고, 같은 직후 사진들을 분할해
얼굴 지도에 펴서 견준다.
립·눈썹은 덮음(실제 부위 중 찾은 영역이 덮은 비율)과 넘침(찾은 영역 중 실제 부위 밖 비율)을,
섀도·아이라인은 침범(찾은 영역 중 눈 안 비율)을 잰다. 블러셔는 볼 경계가 모델에 없어 재지 않는다.
점 테두리(REGION_POINTS)가 실제 부위와 얼마나 맞는지도 같이 적는다.
쪽마다 찾은 영역과 함께, 두 쪽 결과를 서비스처럼 하위 단계로 바꿔(tools/output_area.py)
FE로 나가는 영역도 같은 점수로 재 output 칸에 둔다.
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
--occlusion <이름>을 주면 그 가림 표로 사진마다 가린 칸을 빼고 영역을 찾는다
(tools/occlusion_tables.py).
쪽마다 같은 직전·직후 사진을 쓰므로, 서비스 찾기에 사진 꾸러미(RememberedPhotos)를 넘겨
사진마다 얼굴 지도를 한 번만 편다. 한 단계 직전·직후 사진(시험 영상 최대 40장)을 다 기억하도록
FACE_MAP_KEEP장(서비스와 같은 수)을 기억한다. 기억에 없는 사진은 디스크 저장
(tools/face_map_store.py)에서 꺼내고, --no-store를 주면 쓰지 않는다.
기준값을 바꿔 다시 재려면 tools/run_metric.py로 --set을 준다.
--tag <이름>을 주면 결과를 그 이름 폴더에 따로 둔다.
실행 (ai/ 폴더에서):
uv run python tools/boundary_metric.py samples/local_03_seq <모델 파일>
    [--occlusion <이름>] [--no-store] [--tag <이름>] [--parts <부위,부위>] [--ort-threads <수>]
--ort-threads는 분할 모델이 쓸 코어 수다. 주지 않으면 라이브러리가 이 컴퓨터 코어 수로 정한다.
일꾼 여러 명이 동시에 돌 때(tools/run_metrics.py) 서로 코어를 다투지 않게 줄인다.
"""

import hashlib
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import Face, FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, flatten, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import PhotoLoader, usable_rows
from tools.face_map_store import STORE_USAGE, split_store, tool_photos
from tools.metric_settings import (
    PARTS_USAGE,
    TAG_USAGE,
    selected_parts,
    split_parts,
    split_tag,
    tagged_dir,
    take_option,
    write_result,
)
from tools.occlusion_tables import USAGE, output_dir, split_occlusion, table_finder
from tools.output_area import Area, found_side, output_area

CHECKED_FILE = Path("output") / "frames_checked.json"
OUTPUT_FILE = "boundary.json"
FACE_MAP_KEEP = 64
ORT_THREADS_OPTION = "--ort-threads"
MODEL_URL = "https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx"
MODEL_SHA256 = "0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f"
INPUT_SIZE = 512
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
CROP_SCALE = 1.4
LABELS = {"brows": (2, 3), "eyes": (4, 5), "lips": (12, 13)}
POINT_REGIONS = {
    "brows": ("leftBrow", "rightBrow"),
    "eyes": ("leftEye", "rightEye"),
    "lips": ("lipsOuter",),
}

Parser = Callable[[np.ndarray, Face], np.ndarray]


@dataclass(frozen=True)
class Part:
    """잴 부위 하나. find는 (결과, 시작 ms, 끝 ms, 사진 읽기, 쪽, 가림 찾기)로
    서비스 부위 코드의 찾기 결과(BrowArea 등)를 낸다.

    label은 견줄 실제 부위(LABELS의 키), kind는 "cover"(덮음·넘침) 또는 "intrude"(침범)다.
    regions는 직후 사진을 고를 때 화면 안에 있어야 하는 부위다.
    """

    name: str
    makeup: str
    sides: tuple[RegionName, ...]
    after_ms: int
    label: str
    kind: str
    regions: Callable[[RegionName], list[RegionName]]
    find: Callable[
        [LandmarksResult, int, int, PhotoLoader, RegionName, OcclusionFinder | None], Area
    ]


PARTS = (
    Part(
        "brow",
        "brow",
        brow_area.BROWS,
        brow_area.AFTER_WINDOW_MS,
        "brows",
        "cover",
        lambda side: [side],
        lambda r, s, e, load, side, occ: brow_area.find_brow_area(r, s, e, load, side, occ),
    ),
    Part(
        "eyeshadow",
        "eyeshadow",
        eyeshadow_area.EYES,
        eyeshadow_area.AFTER_WINDOW_MS,
        "eyes",
        "intrude",
        lambda side: [side, eyeshadow_area.EYE_BROWS[side]],
        lambda r, s, e, load, side, occ: eyeshadow_area.find_eyeshadow_area(
            r, s, e, load, side, occ
        ),
    ),
    Part(
        "eyeliner",
        "eyeliner",
        eyeliner_area.EYES,
        eyeliner_area.AFTER_WINDOW_MS,
        "eyes",
        "intrude",
        lambda side: [side],
        lambda r, s, e, load, side, occ: eyeliner_area.find_eyeliner_area(r, s, e, load, side, occ),
    ),
    Part(
        "lip",
        "lip",
        ("lipsOuter",),
        lip_area.AFTER_WINDOW_MS,
        "lips",
        "cover",
        lambda side: [side],
        lambda r, s, e, load, side, occ: lip_area.find_lip_area(r, e, load, occ),
    ),
)


def check_model(path: Path) -> None:
    """모델 파일 지문이 MODEL_SHA256과 다르면 ValueError를 낸다."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise ValueError(
            f"모델 파일 지문이 다릅니다: {digest} (기대 {MODEL_SHA256}, 출처 {MODEL_URL})"
        )


def crop_box(face: Face, width: int, height: int) -> tuple[int, int, int, int]:
    """얼굴 점을 감싸는 네모를 CROP_SCALE배로 넓힌 정사각형 (x0, y0, x1, y1). 사진 밖은 잘라낸다."""
    xs = [p.x * width for p in face.landmarks]
    ys = [p.y * height for p in face.landmarks]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    half = max(max(xs) - min(xs), max(ys) - min(ys)) * CROP_SCALE / 2
    x0, y0 = max(0, round(cx - half)), max(0, round(cy - half))
    x1, y1 = min(width, round(cx + half)), min(height, round(cy + half))
    return x0, y0, x1, y1


def onnx_parser(model_path: Path, threads: int | None = None) -> Parser:
    """BiSeNet ONNX로 사진의 픽셀마다 부위 번호(0~18)를 매기는 함수를 만든다.

    얼굴만 잘라 INPUT_SIZE로 줄여 넣고, 결과를 잘라 낸 크기로 되돌려 사진 크기 표에 놓는다.
    잘라 낸 곳 밖은 0(배경)이다. threads가 있으면 모델 안 일꾼(intra-op) 수를 그만큼으로,
    노드 사이 일꾼(inter-op)을 1로 정한다. 없으면 onnxruntime 기본값이다.
    """
    import onnxruntime

    options = onnxruntime.SessionOptions()
    if threads is not None:
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
    session = onnxruntime.InferenceSession(
        str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
    )
    name = session.get_inputs()[0].name

    def parse(rgb: np.ndarray, face: Face) -> np.ndarray:
        height, width = rgb.shape[:2]
        x0, y0, x1, y1 = crop_box(face, width, height)
        crop = rgb[y0:y1, x0:x1]
        x = cv2.resize(crop, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)
        x = ((x.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None]
        labels = session.run(None, {name: x})[0][0].argmax(0).astype(np.uint8)
        out = np.zeros((height, width), dtype=np.uint8)
        out[y0:y1, x0:x1] = cv2.resize(labels, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        return out

    return parse


def mask_to_map(mask: np.ndarray, face: Face) -> np.ndarray:
    """사진 크기 흑백 표(True가 부위)를 얼굴 지도에 펴서 지도 크기 흑백 표로 바꾼다.

    빨강 칸에 부위를 담아 flatten으로 펴고, 얼굴 밖(흰색) 칸은 부위가 아닌 것으로 본다.
    """
    image = np.zeros((*mask.shape, 3), dtype=np.uint8)
    image[mask, 0] = 255
    flat = flatten(image, face)
    return (flat[..., 0] > 127) & (flat[..., 2] < 128)


def majority(masks: Sequence[np.ndarray]) -> np.ndarray:
    """여러 장의 흑백 표에서 절반 넘게 True인 칸만 True로 둔다."""
    return np.mean(np.stack(masks), axis=0) > 0.5


def side_half(side: RegionName) -> np.ndarray:
    """짝 부위의 한쪽이 놓인 얼굴 지도 반쪽. 가운데 부위(lipsOuter)는 지도 전체다."""
    if side == "lipsOuter":
        return np.ones((MAP_SIZE, MAP_SIZE), dtype=bool)
    xs = [x for x, _ in map_points(REGION_POINTS[side])]
    half = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    if np.mean(xs) < MAP_SIZE / 2:
        half[:, : MAP_SIZE // 2] = True
    else:
        half[:, MAP_SIZE // 2 :] = True
    return half


def ratio(numerator: np.ndarray, denominator: np.ndarray) -> float | None:
    """True 칸 수의 비. 분모가 비어 있으면 None이다."""
    total = int(denominator.sum())
    return None if total == 0 else round(float(numerator.sum() / total), 3)


def boundary_scores(area: np.ndarray, part: np.ndarray, kind: str) -> dict:
    """찾은 영역과 실제 부위를 견준다. cover는 덮음·넘침, intrude는 침범이다."""
    if kind == "cover":
        return {"cover": ratio(area & part, part), "overflow": ratio(area & ~part, area)}
    return {"intrude": ratio(area & part, area)}


def point_outline(side: RegionName) -> np.ndarray:
    """점 테두리(REGION_POINTS)를 지도에 칠한 흑백 표."""
    return polygon_mask(map_points(REGION_POINTS[side]), MAP_SIZE, MAP_SIZE)


def iou(a: np.ndarray, b: np.ndarray) -> float | None:
    """겹친 칸 수 / 합친 칸 수. 둘 다 비어 있으면 None이다."""
    return ratio(a & b, a | b)


def side_scores(
    area: np.ndarray | None, real: np.ndarray | None, photos: int, part: Part, side: RegionName
) -> dict:
    """한 쪽 영역의 경계 점수. 영역이나 직후 사진이 없으면 찾음 여부와 사진 수만 적는다."""
    row = {"found": area is not None, "photos": photos}
    if area is None or real is None:
        return row
    row |= {"areaCells": int(area.sum()), "realCells": int(real.sum())}
    row |= boundary_scores(area, real, part.kind)
    if part.kind == "cover":
        row["pointOutlineIoU"] = iou(point_outline(side), real)
    return row


def measure_part(
    part: Part,
    result: LandmarksResult,
    steps: Sequence,
    load_photo: PhotoLoader,
    label_map: Callable[[FrameLandmarks, str], np.ndarray],
    occlusion: OcclusionFinder | None = None,
) -> list[dict]:
    """부위 하나의 실제로 바른 단계마다, 쪽마다 경계 점수를 낸다. occlusion은 영역 찾기에 넘긴다.

    쪽마다 찾은 영역 점수는 줄에 바로 두고, 나가는 영역 점수는 output 칸에 둔다.
    단계는 서비스처럼 order 순서로 보고, 아이라인은 앞 단계에서 안내한 칸을 빼고 본다.
    """
    out = []
    drawn = None
    for step in sorted(steps, key=lambda s: s.order):
        if step.makeup != part.makeup:
            continue
        start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
        areas = {
            side: part.find(result, start, end, load_photo, side, occlusion) for side in part.sides
        }
        output, _, drawn = output_area(part.makeup, areas, drawn)
        for side in part.sides:
            area, drawn_area = areas[side].mask, found_side(output, side)
            rows = usable_rows(result, end, end + part.after_ms, part.regions(side))
            real = None
            if rows and (area is not None or drawn_area is not None):
                real = majority([label_map(r, part.label) for r in rows]) & side_half(side)
            row = {"part": part.name, "stepId": step.step_id, "side": side}
            row |= side_scores(area, real, len(rows), part, side)
            row["output"] = side_scores(drawn_area, real, len(rows), part, side)
            out.append(row)
    return out


def main() -> None:
    args, occlusion_name = split_occlusion(sys.argv[1:])
    args, use_store = split_store(args)
    args, tag = split_tag(args)
    args, part_names = split_parts(args)
    args, threads = take_option(args, ORT_THREADS_OPTION)
    if len(threads) > 1 or not all(value.isdigit() and int(value) > 0 for value in threads):
        print(f"{ORT_THREADS_OPTION}는 한 번, 1 이상 정수로 줍니다")
        sys.exit(1)
    if len(args) != 2:
        print(
            "사용법: uv run python tools/boundary_metric.py <샘플 폴더> <모델 파일>"
            f" {USAGE} {STORE_USAGE} {TAG_USAGE} {PARTS_USAGE} [{ORT_THREADS_OPTION} <수>]"
        )
        sys.exit(1)

    folder, model_path = Path(args[0]), Path(args[1])
    checked_path = folder / CHECKED_FILE
    if not checked_path.is_file():
        print(f"{checked_path}가 없습니다. 먼저 tools/check_frames.py를 실행하세요.")
        sys.exit(1)
    check_model(model_path)

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(checked_path.read_text(encoding="utf-8"))
    rows_by_index = {row.frame_index: row for row in result.frames}
    parse = onnx_parser(model_path, int(threads[0]) if threads else None)
    occlusion = table_finder(folder, occlusion_name)

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        return read_frame_rgb(reference, frames[row.frame_index])

    @lru_cache(maxsize=64)
    def labels_of(index: int) -> np.ndarray:
        row = rows_by_index[index]
        return parse(load_photo(row), row.face)

    def label_map(row: FrameLandmarks, label: str) -> np.ndarray:
        return mask_to_map(np.isin(labels_of(row.frame_index), LABELS[label]), row.face)

    photos = tool_photos(reference, folder, occlusion_name, load_photo, FACE_MAP_KEEP, use_store)
    out = []
    for part in selected_parts(PARTS, part_names):
        rows = measure_part(part, result, reference.manifest.steps, photos, label_map, occlusion)
        out += rows
        for row in rows:
            keys = ("cover", "overflow", "intrude", "pointOutlineIoU")
            scores = {k: row[k] for k in keys if k in row}
            output = {k: row["output"][k] for k in keys if k in row["output"]}
            print(
                f"{row['part']:9} {row['stepId']:4} {row['side']:10} 찾음 {row['found']}  {scores}"
                f"  | 나가는 영역 찾음 {row['output']['found']}  {output}"
            )

    path = tagged_dir(output_dir(folder, occlusion_name), tag) / OUTPUT_FILE
    write_result(path, {"videoId": reference.manifest.video_id, "steps": out})
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
