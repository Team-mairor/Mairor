"""가이드 영역을 다른 사람 얼굴에 씌워 큰 오류를 찾는다 (개발용).

큰 오류는 눈 덮음 · 얼굴 밖 · 엉뚱한 자리다. 영역은 얼굴 주소(삼각형 번호 + 세 꼭짓점
비율)라서, 다른 사람 사진의 얼굴 점에 같은 계산을 하면 FE가 사용자 얼굴에 그리는 자리와
같은 곳에 놓인다(tools/draw_guide_area.py와 같은 계산).
영역 칸은 테두리 안에서 빼는 부위(exclude) 테두리 안을 뺀 곳이다. FE가 구멍으로 그리는 자리다.

픽셀마다 얼굴 부위는 가림 찾기 모델의 칸 번호로 정한다. 이 모델은 얼굴 분할 BiSeNet에
가림 칸을 더한 것이다. 영역 칸마다 아래를 센다.
- outside: 영역 칸 중 얼굴 밖(배경 · 목 · 옷 · 모자) 비율
- hair: 영역 칸 중 머리카락 비율. 앞머리가 눈썹을 덮은 경우처럼, 자리는 맞아도 가려진
  경우를 가른다
- eyeCover: 영역 칸 중 눈(흰자 · 검은자) 비율
- onTarget: 눈썹 영역은 눈썹 칸 비율, 립 영역은 입술 · 입 칸 비율. 그 밖의 부위는 비운다
같은 값을 영역을 만든 사람(원래 얼굴)의 사진에서도 재고, 사진들의 가운데 값을 기준으로 둔다.
다른 얼굴 값이 기준보다 WORSE_MARGIN 넘게 나쁘면 큰 오류로 적는다(outside · eyeCover는
더 크면, onTarget은 더 작으면). onTarget이 나쁜데 hair도 WORSE_MARGIN보다 크면
onTarget(hair)로 적는다.
정확도 점수가 아니다. 다른 얼굴에는 그 사람이 바른 곳(정답)이 없기 때문이다.
영역 파일은 공유 형식(shared/guide-area)을 JSON으로 그대로 읽고 polygon만 쓴다.

사진 고르기: 폴더의 사진을 고르게 SCAN_LIMIT장까지 훑는다. 얼굴이 하나이고, 고개(yaw ·
pitch)가 POSE_LIMIT_DEG 안이고, 얼굴 가로가 MIN_FACE_PX 이상이고, 얼굴 테두리 안을 손 ·
도구 · 자막이 서비스 사진 거르기와 같은 기준(area_preparation.OCCLUDED_MAX)보다 많이
가리지 않은 사진 중 PHOTOS_PER_FACE장을 고르게 고른다.

결과: <저장 폴더>/other_faces.json(사진 · 영역마다 값과 큰 오류)과 얼굴마다 그림
(<이름>.jpg는 첫 사진, 큰 오류가 난 사진은 <이름>_<사진>.jpg)
실행 (ai/ 폴더에서):
uv run python tools/other_faces_check.py <guide_area.json> <저장 폴더> <원래 얼굴 사진 폴더>
    <이름>=<사진 폴더> [<이름>=<사진 폴더> ...]
화장 종류(눈썹 · 립의 onTarget)는 영역 파일 단계마다 있는 makeup 칸을 쓴다.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime
from PIL import Image, ImageDraw, ImageFont

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.landmarks import Face
from app.tasks.area.common.face_map import MESH_DIR
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.face_finder import find_faces
from app.tasks.area.landmarks.occlusion_finder import (
    INPUT_NAME,
    INPUT_SIZE,
    MEAN,
    MODEL_PATH,
    STD,
    square_box,
)
from app.tasks.area.parts.area_preparation import OCCLUDED_MAX

PHOTOS_PER_FACE = 5
SCAN_LIMIT = 60
POSE_LIMIT_DEG = 12.0
MIN_FACE_PX = 250
WORSE_MARGIN = 0.2
OUTSIDE_LABELS = (0, 14, 15, 16, 18)
HAIR_LABELS = (17,)
OCCLUDER_LABEL = 19
EYE_LABELS = (4, 5)
TARGET_LABELS = {"brow": (2, 3), "lip": (11, 12, 13)}
PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png")
DRAW_COLOR = (255, 0, 140)
FLAG_COLOR = (255, 200, 0)
USAGE = (
    "사용법: uv run python tools/other_faces_check.py <guide_area.json> <저장 폴더>"
    " <원래 얼굴 사진 폴더> <이름>=<사진 폴더> [...]"
)

Photo = tuple[Path, Face, np.ndarray]


def area_shapes(area: dict) -> list[dict]:
    """찾은 영역(extracted)마다 테두리 · 구멍 · 부위 · 화장 종류.

    기본 영역 · 영역 없음은 FE가 그리는 모양이라 뺀다. 화장 종류는 단계의 makeup 칸이다.
    """
    shapes = []
    for step in area["steps"]:
        for sub in step["subSteps"]:
            if sub["status"] != "extracted":
                continue
            for guide_set in sub["guideSets"]:
                outlines = [g["outline"] for g in guide_set["guides"] if g["type"] == "polygon"]
                shapes.append(
                    {
                        "subStepId": sub["subStepId"],
                        "makeup": step["makeup"],
                        "region": guide_set["region"],
                        "outlines": outlines,
                        "exclude": guide_set.get("exclude") or [],
                    }
                )
    return shapes


def photo_points(outline: list[dict], face: Face, width: int, height: int) -> np.ndarray:
    """얼굴 주소들을 사진 픽셀 좌표로. 삼각형 세 꼭짓점 얼굴 점을 비율로 섞는다."""
    triangles = _triangles()
    points = []
    for anchor in outline:
        corners = [face.landmarks[i] for i in triangles[anchor["triangle"]]]
        x = sum(r * c.x for r, c in zip(anchor["bary"], corners, strict=True))
        y = sum(r * c.y for r, c in zip(anchor["bary"], corners, strict=True))
        points.append((x * width, y * height))
    return np.array(points, dtype=np.float64)


def region_points(region: str, face: Face, width: int, height: int) -> np.ndarray:
    """부위 테두리 얼굴 점들의 사진 픽셀 좌표."""
    return np.array(
        [(face.landmarks[i].x * width, face.landmarks[i].y * height) for i in REGION_POINTS[region]]
    )


def area_mask(shape: dict, face: Face, width: int, height: int) -> np.ndarray:
    """영역 칸 표. 테두리 안을 칠하고 빼는 부위 테두리 안을 지운다."""
    mask = np.zeros((height, width), dtype=np.uint8)
    for outline in shape["outlines"]:
        points = photo_points(outline, face, width, height)
        cv2.fillPoly(mask, [np.round(points).astype(np.int32)], 1)
    for region in shape["exclude"]:
        hole = region_points(region, face, width, height)
        cv2.fillPoly(mask, [np.round(hole).astype(np.int32)], 0)
    return mask.astype(bool)


def face_labels(rgb: np.ndarray, face: Face) -> np.ndarray:
    """사진 크기 부위 칸 번호 표. 얼굴 둘레 정사각형만 모델에 넣고 밖은 배경(0)이다."""
    height, width = rgb.shape[:2]
    x0, y0, side = square_box(face, width, height)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(width, x0 + side), min(height, y0 + side)
    canvas = np.zeros((side, side, 3), dtype=np.uint8)
    canvas[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
    crop = cv2.resize(canvas, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_AREA)
    x = ((crop.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None]
    labels = _model().run(None, {INPUT_NAME: np.ascontiguousarray(x)})[0][0].argmax(0)
    back = cv2.resize(labels.astype(np.uint8), (side, side), interpolation=cv2.INTER_NEAREST)
    out = np.zeros((height, width), dtype=np.uint8)
    out[sy0:sy1, sx0:sx1] = back[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0]
    return out


def measure(mask: np.ndarray, labels: np.ndarray, makeup: str) -> dict:
    """영역 칸 하나의 outside · hair · eyeCover · onTarget. 칸이 없으면 모두 None이다."""
    cells = int(mask.sum())
    if not cells:
        return {"cells": 0, "outside": None, "hair": None, "eyeCover": None, "onTarget": None}
    picked = labels[mask]
    target = TARGET_LABELS.get(makeup)
    return {
        "cells": cells,
        "outside": round(float(np.isin(picked, OUTSIDE_LABELS).mean()), 4),
        "hair": round(float(np.isin(picked, HAIR_LABELS).mean()), 4),
        "eyeCover": round(float(np.isin(picked, EYE_LABELS).mean()), 4),
        "onTarget": round(float(np.isin(picked, target).mean()), 4) if target else None,
    }


def flags(value: dict, base: dict) -> list[str]:
    """원래 얼굴 기준보다 WORSE_MARGIN 넘게 나쁜 항목 이름들."""
    out = []
    for key in ("outside", "eyeCover"):
        if value[key] is None or base.get(key) is None:
            continue
        if value[key] > base[key] + WORSE_MARGIN:
            out.append(key)
    if value["onTarget"] is not None and base.get("onTarget") is not None:
        if value["onTarget"] < base["onTarget"] - WORSE_MARGIN:
            hair = value["hair"] is not None and value["hair"] > WORSE_MARGIN
            out.append("onTarget(hair)" if hair else "onTarget")
    return out


def occluded_share(rgb: np.ndarray, face: Face) -> float:
    """얼굴 테두리 안에서 손 · 도구 · 자막(가림 칸)이 차지하는 비율."""
    height, width = rgb.shape[:2]
    oval = np.zeros((height, width), dtype=np.uint8)
    points = region_points("faceOval", face, width, height)
    cv2.fillPoly(oval, [np.round(points).astype(np.int32)], 1)
    inside = oval.astype(bool)
    if not inside.any():
        return 1.0
    return float((face_labels(rgb, face)[inside] == OCCLUDER_LABEL).mean())


def pick_photos(folder: Path) -> list[Photo]:
    """정면에 가깝고 얼굴이 하나이며 가리지 않은 사진을 PHOTOS_PER_FACE장 고르게 고른다."""
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_SUFFIXES)
    step = max(1, len(files) // SCAN_LIMIT)
    good = []
    for path in files[::step][:SCAN_LIMIT]:
        rgb = np.array(Image.open(path).convert("RGB"))
        faces = find_faces(rgb)
        if len(faces) != 1:
            continue
        face = faces[0]
        xs = [p.x for p in face.landmarks]
        if (
            abs(np.degrees(face.pose.yaw)) <= POSE_LIMIT_DEG
            and abs(np.degrees(face.pose.pitch)) <= POSE_LIMIT_DEG
            and (max(xs) - min(xs)) * rgb.shape[1] >= MIN_FACE_PX
            and occluded_share(rgb, face) <= OCCLUDED_MAX
        ):
            good.append((path, face, rgb))
    if len(good) <= PHOTOS_PER_FACE:
        return good
    index = np.linspace(0, len(good) - 1, PHOTOS_PER_FACE).round().astype(int)
    return [good[i] for i in index]


def check_face(shapes: list[dict], photos: list[Photo]) -> list[dict]:
    """사진마다 영역마다 값. 사진 순서 · 영역 순서 그대로다."""
    rows = []
    for path, face, rgb in photos:
        height, width = rgb.shape[:2]
        labels = face_labels(rgb, face)
        for shape in shapes:
            mask = area_mask(shape, face, width, height)
            value = measure(mask, labels, shape["makeup"])
            key = {"photo": path.name, "subStepId": shape["subStepId"], "region": shape["region"]}
            rows.append({**key, **value})
    return rows


def baseline(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """원래 얼굴의 영역마다 사진들의 가운데 값.

    한 사진이 손 · 제품에 가려져도 기준이 흔들리지 않는다.
    """
    values: dict[tuple[str, str], dict[str, list[float]]] = {}
    for row in rows:
        key = (row["subStepId"], row["region"])
        bucket = values.setdefault(key, {"outside": [], "eyeCover": [], "onTarget": []})
        for name, found in bucket.items():
            if row[name] is not None:
                found.append(row[name])
    return {
        key: {name: round(float(np.median(v)), 4) if v else None for name, v in bucket.items()}
        for key, bucket in values.items()
    }


def draw(shapes: list[dict], photo: Photo, flagged: set[str], out: Path, name: str) -> None:
    """한 사진에 모든 영역 테두리를 그린다. 큰 오류가 난 영역은 다른 색이다."""
    _, face, rgb = photo
    height, width = rgb.shape[:2]
    image = Image.fromarray(rgb)
    pen = ImageDraw.Draw(image)
    for shape in shapes:
        flagged_here = f"{shape['subStepId']}|{shape['region']}" in flagged
        color = FLAG_COLOR if flagged_here else DRAW_COLOR
        for outline in shape["outlines"]:
            points = [tuple(p) for p in photo_points(outline, face, width, height)]
            pen.line([*points, points[0]], fill=color, width=max(2, width // 400))
    xs = [p.x * width for p in face.landmarks]
    ys = [p.y * height for p in face.landmarks]
    pad = (max(xs) - min(xs)) * 0.25
    box = (
        max(0, int(min(xs) - pad)),
        max(0, int(min(ys) - pad)),
        min(width, int(max(xs) + pad)),
        min(height, int(max(ys) + pad)),
    )
    crop = image.crop(box)
    font = _font(max(16, crop.width // 20))
    ImageDraw.Draw(crop).text((8, 8), name, fill=(255, 255, 255), font=font)
    crop.save(out / f"{name}.jpg", quality=88)


def check_other(shapes: list[dict], base: dict, name: str, folder: str, out: Path) -> dict:
    """다른 얼굴 하나를 재고, 첫 사진과 큰 오류가 난 사진을 그린다."""
    photos = pick_photos(Path(folder))
    rows = check_face(shapes, photos)
    for row in rows:
        row["flags"] = flags(row, base[(row["subStepId"], row["region"])])
    for index, photo in enumerate(photos):
        flagged = {
            f"{r['subStepId']}|{r['region']}"
            for r in rows
            if r["flags"] and r["photo"] == photo[0].name
        }
        if index == 0 or flagged:
            draw(shapes, photo, flagged, out, name if index == 0 else f"{name}_{photo[0].stem}")
    flagged_rows = {
        f"{r['subStepId']}|{r['region']}|{','.join(r['flags'])}" for r in rows if r["flags"]
    }
    print(f"{name}: 사진 {len(photos)}장, 큰 오류 {sum(1 for r in rows if r['flags'])}개")
    return {
        "name": name,
        "folder": folder,
        "photos": [p.name for p, _, _ in photos],
        "rows": rows,
        "flagged": sorted(flagged_rows),
    }


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 4 or any("=" not in item for item in args[3:]):
        print(USAGE)
        sys.exit(1)
    area = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    out = Path(args[1])
    out.mkdir(parents=True, exist_ok=True)
    shapes = area_shapes(area)
    source_photos = pick_photos(Path(args[2]))
    source_rows = check_face(shapes, source_photos)
    base = baseline(source_rows)
    if source_photos:
        draw(shapes, source_photos[0], set(), out, "source")
    result = {
        "source": {
            "folder": args[2],
            "photos": [p.name for p, _, _ in source_photos],
            "baseline": [{"subStepId": k[0], "region": k[1], **v} for k, v in base.items()],
            "rows": source_rows,
        },
        "faces": [],
    }
    for item in args[3:]:
        name, _, folder = item.partition("=")
        result["faces"].append(check_other(shapes, base, name, folder, out))
    path = out / "other_faces.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {path}")


_cache: dict = {}


def _triangles() -> list[list[int]]:
    """공유 얼굴 메시의 삼각형 목록. 배열 위치가 얼굴 주소의 삼각형 번호다."""
    if "triangles" not in _cache:
        data = json.loads((MESH_DIR / "triangles.v1.json").read_text(encoding="utf-8"))
        _cache["triangles"] = data["triangles"]
    return _cache["triangles"]


def _model() -> onnxruntime.InferenceSession:
    """가림 찾기 모델을 한 번만 연다."""
    if "model" not in _cache:
        providers = ["CPUExecutionProvider"]
        _cache["model"] = onnxruntime.InferenceSession(str(MODEL_PATH), providers=providers)
    return _cache["model"]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """그림 이름표 글꼴. 한글 글꼴이 없으면 기본 글꼴을 쓴다."""
    try:
        return ImageFont.truetype("malgun.ttf", size)
    except OSError:
        return ImageFont.load_default()


if __name__ == "__main__":
    main()
