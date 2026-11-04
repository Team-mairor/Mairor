"""진짜 사진으로 가림 정답지를 만든다(개발용). 선생님 모델은 MediaPipe 셀카 다중 분할이다.

영상 폴더마다 판정이 ok인 사진을 시간 순서로 보며 DEDUP_SECONDS 안에 겹치는 사진은 하나만 쓴다.
1. 얼굴 점 네모를 CROP_SCALE배 넓힌 정사각형을 SIZE × SIZE로 줄인다. 사진 밖은 검은색이다.
2. BiSeNet(그대로)이 얼굴 부위 19가지를, MediaPipe가 6가지를 칠한다.
3. 정답지 = BiSeNet 부위. 얼굴 테두리 안에서 MediaPipe가 얼굴 피부가 아니라고 한 곳은
   가림(OCCLUDER), 테두리 바깥 손·물건과 테두리 안쪽 EDGE_BAND 띠, 사진 밖은 학습에서 뺀다(IGNORE).
4. 합성 사진에 붙일 손·물건 조각(RGBA)도 잘라 둔다.
결과는 <작업 폴더>/data/real/<나눔>/<영상>/의 images·labels·pieces와 index.json이다.
나눔이 test(시험 영상)이면 <작업 폴더>/data/test_real/test/<영상>/에 쓴다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/real_labels.py <나눔>:<영상>=<샘플 폴더> ...
"""

import json
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import onnxruntime
from mediapipe.tasks.python import BaseOptions, vision
from PIL import Image
from workspace import BISENET_ONNX, REAL_DIR, SELFIE_MODEL, TEST_REAL_DIR

from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb

OCCLUDED_MAX = 1.0
EDGE_BAND = 0.03
DEDUP_SECONDS = 2.0

SIZE = 512
CROP_SCALE = 1.4
OCCLUDER = 19
IGNORE = 255
MP_FACE_SKIN, MP_BODY_SKIN, MP_OTHERS = 3, 2, 5
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PIECE_MIN_SHARE = 0.01
PIECE_FACE_OVERLAP = 0.1
BISENET_NECK_CLOTH = (14, 15, 16)


def square_crop(rgb, face):
    """얼굴 점 네모 × CROP_SCALE 정사각형을 SIZE로 줄인다.

    (줄인 사진, 사진 안쪽 표, (왼쪽 x, 위 y, 한 변))을 돌려준다. 사진 밖은 검은색이다.
    """
    h, w = rgb.shape[:2]
    xs = [p.x * w for p in face.landmarks]
    ys = [p.y * h for p in face.landmarks]
    side = max(max(xs) - min(xs), max(ys) - min(ys)) * CROP_SCALE
    x0 = int(round((min(xs) + max(xs)) / 2 - side / 2))
    y0 = int(round((min(ys) + max(ys)) / 2 - side / 2))
    side = int(round(side))
    canvas = np.zeros((side, side, 3), np.uint8)
    valid = np.zeros((side, side), np.uint8)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(w, x0 + side), min(h, y0 + side)
    canvas[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
    valid[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = 1
    crop = cv2.resize(canvas, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    valid = cv2.resize(valid, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST).astype(bool)
    return crop, valid, (x0, y0, side)


def face_points(face, w, h, box, indices):
    """얼굴 점 번호들을 square_crop으로 자른 SIZE 정사각형 위 좌표로 옮긴다."""
    x0, y0, side = box
    k = SIZE / side
    return np.array(
        [((face.landmarks[i].x * w - x0) * k, (face.landmarks[i].y * h - y0) * k) for i in indices],
        np.int32,
    )


def selfie_segmenter() -> vision.ImageSegmenter:
    """MediaPipe 셀카 다중 분할(배경·머리카락·몸 피부·얼굴 피부·옷·기타 6가지)."""
    return vision.ImageSegmenter.create_from_options(
        vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(SELFIE_MODEL)),
            output_category_mask=True,
        )
    )


def selfie_classes(segmenter: vision.ImageSegmenter, rgb: np.ndarray) -> np.ndarray:
    """사진의 픽셀마다 MediaPipe 셀카 다중 분할 번호(0~5)."""
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
    return segmenter.segment(image).category_mask.numpy_view().squeeze()


def main() -> None:
    bisenet = onnxruntime.InferenceSession(str(BISENET_ONNX), providers=["CPUExecutionProvider"])
    bisenet_input = bisenet.get_inputs()[0].name
    selfie = selfie_segmenter()
    for arg in sys.argv[1:]:
        split_video, folder = arg.split("=", 1)
        split, video = split_video.split(":", 1)
        folder = Path(folder)
        ref = load_reference_input(folder)
        res = LandmarksResult.model_validate_json(
            (folder / "output" / "frames_checked.json").read_text(encoding="utf-8")
        )
        frames = {f.frame_index: f for f in ref.manifest.frames}
        dest = (TEST_REAL_DIR if split == "test" else REAL_DIR) / split / video
        for sub in ("images", "labels", "pieces"):
            (dest / sub).mkdir(parents=True, exist_ok=True)
        rows, last_kept = [], None
        ok_rows = sorted((r for r in res.frames if r.status == "ok"), key=lambda r: r.timestamp_ms)
        for r in ok_rows:
            t = r.timestamp_ms / 1000
            if last_kept is not None and t - last_kept < DEDUP_SECONDS:
                continue
            rgb = read_frame_rgb(ref, frames[r.frame_index])
            h, w = rgb.shape[:2]
            crop, valid, box = square_crop(rgb, r.face)
            x = ((crop.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None]
            face19 = bisenet.run(None, {bisenet_input: x})[0][0].argmax(0).astype(np.uint8)
            mp6 = selfie_classes(selfie, crop)
            oval = face_points(r.face, w, h, box, REGION_POINTS["faceOval"])
            inside = np.zeros((SIZE, SIZE), np.uint8)
            cv2.fillPoly(inside, [oval], 1)
            inside = inside.astype(bool)
            face_size = float(np.ptp(oval[:, 0]))
            dist = cv2.distanceTransform(inside.astype(np.uint8), cv2.DIST_L2, 5)
            band = inside & (dist <= EDGE_BAND * face_size)
            not_neck = ~np.isin(face19, BISENET_NECK_CLOTH)
            outside_hand = ~inside & np.isin(mp6, (MP_BODY_SKIN, MP_OTHERS)) & not_neck
            occluder = inside & (mp6 != MP_FACE_SKIN)
            label = face19.copy()
            label[occluder] = OCCLUDER
            label[outside_hand] = IGNORE
            label[band] = IGNORE
            label[~valid] = IGNORE
            judged = inside & ~band
            occluded_share = float((label[judged] == OCCLUDER).mean()) if judged.any() else 1.0
            reason = "tooMuchOccluded" if occluded_share > OCCLUDED_MAX else None
            row = {
                "t": t,
                "frameIndex": r.frame_index,
                "occludedShare": round(occluded_share, 4),
                "dropped": reason,
            }
            if reason is None:
                name = f"{r.frame_index:06d}.png"
                Image.fromarray(crop).save(dest / "images" / name)
                Image.fromarray(label).save(dest / "labels" / name)
                row["pieces"] = _save_pieces(
                    crop, mp6, not_neck & valid, judged, dest, r.frame_index
                )
                last_kept = t
            rows.append(row)
        (dest / "index.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        kept = [x for x in rows if x["dropped"] is None]
        print(
            split,
            video,
            f"사진 {len(rows)}장, 남김 {len(kept)}장,",
            f"가림 있음 {sum(x['occludedShare'] > 0.01 for x in kept)}장,",
            f"조각 {sum(x.get('pieces', 0) for x in kept)}개",
            flush=True,
        )


def _save_pieces(crop, mp6, allowed, judged, dest: Path, frame_index: int) -> int:
    """손·물건 덩어리 중 크고 얼굴에 걸친 것만 RGBA 조각으로 저장하고 개수를 돌려준다."""
    pieces = (np.isin(mp6, (MP_BODY_SKIN, MP_OTHERS)) & allowed).astype(np.uint8)
    n, comp, stats, _ = cv2.connectedComponentsWithStats(pieces)
    kept = 0
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < PIECE_MIN_SHARE * SIZE * SIZE:
            continue
        if ((comp == i) & judged).sum() < PIECE_FACE_OVERLAP * area:
            continue
        x, y, bw, bh = stats[i, :4]
        alpha = (comp[y : y + bh, x : x + bw] == i).astype(np.uint8) * 255
        rgba = np.dstack([crop[y : y + bh, x : x + bw], alpha])
        Image.fromarray(rgba, "RGBA").save(dest / "pieces" / f"{frame_index:06d}_{kept}.png")
        kept += 1
    return kept


if __name__ == "__main__":
    main()
