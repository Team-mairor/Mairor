"""가림 없는 얼굴에 자막·그린 도구·손 조각을 붙여 합성 가림 문제를 만든다(개발용).

문제 하나 = 가림 없는 바탕 얼굴(512 × 512) 하나 + 붙인 것 0~3개(+ 사진 전체 흐림).
정답지는 바탕의 정답지에서 붙인 것이 얼굴 부위(1~13)를 덮은 칸은 가림(OCCLUDER), 그 밖은 학습에서
뺀다(IGNORE). 나눔은 섞지 않는다. 학습 바탕·조각은 학습 문제에만, 검증은 검증, 시험은 시험에만 쓴다.
자막 글꼴은 Windows의 맑은 고딕 굵게(FONT)다.
결과는 <작업 폴더>/data/synth/<나눔>/의 images·labels와 list.jsonl이다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/make_synth.py train=<정답지 폴더>/train ...
"""

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from workspace import SYNTH_DIR

SEED = 287
COUNTS = {"train": 3000, "val": 400, "test": 600}
BASE_MAX = {"train": 10, "val": 5, "test": 10}
PIECE_MAX = {"train": 20, "val": 15, "test": 20}
TYPE_WEIGHTS = {"subtitle": 0.30, "tool": 0.35, "piece": 0.35}
CLEAN_SHARE = 0.15
BLUR_SHARE = 0.25
ITEMS_PER_PROBLEM = (1, 3)
NEAR_PART_SHARE = 0.7
SCALE_RANGE = (0.15, 0.8)
ANGLE_RANGE = 45
BRIGHTNESS_RANGE = 0.2
PIECE_MOTION_SHARE = 0.3
FEATHER_PX = (1, 2)
SUBTITLE_FONT_SHARE = (0.05, 0.10)
BASE_FACE_MIN = 0.05

SIZE = 512
OCCLUDER = 19
IGNORE = 255
FACE_LABELS = (*range(1, 14), OCCLUDER)
PART_LABELS = (2, 3, 4, 5, 10, 12, 13)
FONT = "C:/Windows/Fonts/malgunbd.ttf"
PHRASES = [
    "이렇게 톡톡 두드려 주세요",
    "눈두덩 전체에 펴 발라요",
    "입술 안쪽부터 채워 주세요",
    "브러시로 가볍게 쓸어 줍니다",
    "광대 위쪽에 살짝 올려요",
    "눈꼬리를 길게 빼 줄게요",
    "콧대를 따라 내려 주세요",
    "손가락으로 경계를 풀어요",
    "속눈썹 뿌리부터 올려요",
    "언더에 포인트를 줄게요",
    "이 정도면 충분해요",
    "자연스럽게 블렌딩 해요",
]


def face_mask(label):
    """정답지에서 얼굴 칸(부위와 가림)."""
    return np.isin(label, FACE_LABELS)


def face_width(mask):
    """얼굴 칸의 가로 길이(픽셀). 얼굴 칸이 없으면 SIZE의 0.6배다."""
    xs = np.where(mask.any(axis=0))[0]
    return float(xs.max() - xs.min()) if len(xs) else SIZE * 0.6


def pick_center(rng, label):
    """붙일 자리. NEAR_PART_SHARE만큼은 눈·눈썹·입술 칸에서, 나머지는 얼굴 칸에서 고른다."""
    near = np.isin(label, PART_LABELS)
    pool = near if rng.random() < NEAR_PART_SHARE and near.any() else face_mask(label)
    ys, xs = np.nonzero(pool)
    i = rng.integers(len(ys))
    return int(xs[i]), int(ys[i])


def motion_kernel(length, angle):
    """length 길이, angle 방향의 움직임 번짐 커널."""
    k = np.zeros((length, length), np.float32)
    k[length // 2, :] = 1
    rot = cv2.getRotationMatrix2D((length / 2 - 0.5, length / 2 - 0.5), angle, 1)
    k = cv2.warpAffine(k, rot, (length, length))
    return k / max(k.sum(), 1e-6)


def draw_tool(rng, fw):
    """투명한 바탕에 오른쪽을 향한 펜슬·브러시·뷰러 중 하나를 그린다."""
    kind = rng.choice(["pencil", "brush", "curler"])
    length = int(fw * rng.uniform(0.35, 0.8))
    thick = max(4, int(fw * rng.uniform(0.025, 0.05)))
    img = Image.new("RGBA", (length + thick * 4, thick * 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = img.height // 2
    body = tuple(int(c) for c in rng.integers(30, 240, 3)) + (255,)
    if kind == "pencil":
        d.rounded_rectangle(
            (0, cy - thick // 2, length, cy + thick // 2), radius=thick // 3, fill=body
        )
        tip = tuple(int(c) for c in rng.integers(20, 120, 3)) + (255,)
        d.polygon(
            [(length, cy - thick // 2), (length, cy + thick // 2), (length + thick * 2, cy)],
            fill=tip,
        )
    elif kind == "brush":
        handle = int(length * 0.7)
        d.rounded_rectangle(
            (0, cy - thick // 2, handle, cy + thick // 2), radius=thick // 3, fill=body
        )
        d.rectangle(
            (handle, cy - thick * 0.7, handle + thick * 2, cy + thick * 0.7),
            fill=(190, 190, 195, 255),
        )
        hair = tuple(int(c) for c in rng.integers(20, 230, 3)) + (255,)
        d.ellipse(
            (handle + thick * 2 - 2, cy - thick * 1.4, length + thick * 3, cy + thick * 1.4),
            fill=hair,
        )
    else:
        metal = (175, 175, 180, 255)
        d.line((0, cy, int(length * 0.6), cy - thick), fill=metal, width=max(2, thick // 2))
        d.line((0, cy, int(length * 0.6), cy + thick), fill=metal, width=max(2, thick // 2))
        d.arc(
            (int(length * 0.5), cy - thick * 2.5, length + thick * 2, cy + thick * 2.5),
            270,
            90,
            fill=metal,
            width=max(2, thick // 2),
        )
    return img, str(kind)


def draw_subtitle(rng, fw):
    """흰 상자+검은 글자 또는 흰 글자+검은 테두리 자막 한 줄을 그린다. (그림, 모양)을 돌려준다."""
    size = max(10, int(fw * rng.uniform(*SUBTITLE_FONT_SHARE)))
    font = ImageFont.truetype(FONT, size)
    text = str(rng.choice(PHRASES))
    box = font.getbbox(text)
    w, h = box[2] - box[0] + size, box[3] - box[1] + size // 2
    img = Image.new("RGBA", (w + 6, h + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rng.random() < 0.5:
        d.rectangle((0, 0, w + 5, h + 5), fill=(255, 255, 255, 255))
        d.text((size // 2, size // 4 - box[1]), text, font=font, fill=(20, 20, 20, 255))
        style = "box"
    else:
        d.text(
            (size // 2, size // 4 - box[1]),
            text,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=max(1, size // 12),
            stroke_fill=(10, 10, 10, 255),
        )
        style = "outline"
    return img, style


def transform(rng, item, fw, keep_level=False):
    """크기·회전·밝기·가장자리 흐림·움직임 번짐을 준다.

    자막(keep_level)은 크기·회전을 바꾸지 않는다.
    """
    scale = 1.0
    if not keep_level:
        target = fw * rng.uniform(*SCALE_RANGE)
        scale = target / max(item.width, item.height)
        item = item.resize(
            (max(2, int(item.width * scale)), max(2, int(item.height * scale))), Image.BILINEAR
        )
        angle = float(rng.uniform(-ANGLE_RANGE, ANGLE_RANGE))
        item = item.rotate(angle, expand=True, resample=Image.BILINEAR)
    else:
        angle = 0.0
    rgba = np.asarray(item).astype(np.float32)
    rgba[..., :3] *= 1 + rng.uniform(-BRIGHTNESS_RANGE, BRIGHTNESS_RANGE)
    alpha = rgba[..., 3]
    feather = int(rng.integers(FEATHER_PX[0], FEATHER_PX[1] + 1))
    alpha = cv2.GaussianBlur(alpha, (0, 0), feather)
    motion = 0
    if not keep_level and rng.random() < PIECE_MOTION_SHARE:
        motion = int(rng.integers(5, 17))
        k = motion_kernel(motion, float(rng.uniform(0, 180)))
        rgba[..., :3] = cv2.filter2D(rgba[..., :3], -1, k)
        alpha = cv2.filter2D(alpha, -1, k)
    rgba[..., 3] = alpha
    return rgba.clip(0, 255), {"scale": round(scale, 3), "angle": round(angle, 1), "motion": motion}


def paste(image, label, rgba, center):
    """사진과 정답지에 붙이고, 덮은 얼굴 칸 수를 돌려준다."""
    h, w = rgba.shape[:2]
    x0, y0 = center[0] - w // 2, center[1] - h // 2
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(SIZE, x0 + w), min(SIZE, y0 + h)
    if sx1 <= sx0 or sy1 <= sy0:
        return 0
    part = rgba[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0]
    a = part[..., 3:4] / 255
    region = image[sy0:sy1, sx0:sx1]
    image[sy0:sy1, sx0:sx1] = region * (1 - a) + part[..., :3] * a
    covered = part[..., 3] > 127
    lab = label[sy0:sy1, sx0:sx1]
    on_face = covered & np.isin(lab, FACE_LABELS)
    lab[on_face] = OCCLUDER
    lab[covered & ~np.isin(lab, FACE_LABELS) & (lab != IGNORE)] = IGNORE
    return int(on_face.sum())


def load_split(folder):
    """나눔 폴더의 바탕과 조각. 정답지에 얼굴 칸이 BASE_FACE_MIN도 안 되는 바탕은 뺀다.

    초점이 나가 BiSeNet이 얼굴을 못 본 사진이 그렇다.
    """
    bases = []
    for base in json.loads((folder / "bases.json").read_text(encoding="utf-8")):
        label = np.asarray(
            Image.open(folder / base["video"] / "labels" / f"{base['frameIndex']:06d}.png")
        )
        if face_mask(label).mean() >= BASE_FACE_MIN:
            bases.append(base)
        else:
            print("얼굴 칸이 없는 바탕은 뺌:", base["video"], base["frameIndex"], flush=True)
    pieces = sorted(folder.glob("*/pieces/*.png"))
    return bases, pieces


def make_split(rng, split, folder, out):
    """나눔 하나의 문제를 COUNTS만큼 만든다. 바탕은 무작위 순서를 되풀이해 고르게 쓴다."""
    bases, pieces = load_split(folder)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    base_cap = max(BASE_MAX[split], math.ceil(COUNTS[split] / max(1, len(bases))))
    base_order = np.concatenate([rng.permutation(len(bases)) for _ in range(base_cap)])[
        : COUNTS[split]
    ]
    piece_use = np.zeros(len(pieces), int)
    names = list(TYPE_WEIGHTS)
    probs = np.array([TYPE_WEIGHTS[n] for n in names])
    rows = []
    for i, bi in enumerate(base_order):
        base = bases[int(bi)]
        name = f"{base['frameIndex']:06d}.png"
        src = folder / base["video"]
        image = np.asarray(Image.open(src / "images" / name).convert("RGB")).astype(np.float32)
        label = np.asarray(Image.open(src / "labels" / name)).copy()
        fw = face_width(face_mask(label))
        items = []
        if rng.random() >= CLEAN_SHARE:
            for _ in range(int(rng.integers(ITEMS_PER_PROBLEM[0], ITEMS_PER_PROBLEM[1] + 1))):
                kind = str(rng.choice(names, p=probs))
                if kind == "piece":
                    free = np.nonzero(piece_use < PIECE_MAX[split])[0]
                    if not len(free):
                        kind = "tool"
                    else:
                        pi = int(rng.choice(free))
                        piece_use[pi] += 1
                        rgba, info = transform(rng, Image.open(pieces[pi]).convert("RGBA"), fw)
                        info |= {
                            "type": "piece",
                            "piece": pieces[pi].parent.parent.name + "/" + pieces[pi].name,
                        }
                if kind == "tool":
                    tool, tool_kind = draw_tool(rng, fw)
                    rgba, info = transform(rng, tool, fw)
                    info |= {"type": "tool", "tool": tool_kind}
                if kind == "subtitle":
                    sub, style = draw_subtitle(rng, fw)
                    rgba, info = transform(rng, sub, fw, keep_level=True)
                    info |= {"type": "subtitle", "style": style}
                center = pick_center(rng, label)
                info["center"] = list(center)
                info["coveredFaceCells"] = paste(image, label, rgba, center)
                items.append(info)
        blur = None
        if rng.random() < BLUR_SHARE:
            if rng.random() < 0.5:
                sigma = float(rng.uniform(1.5, 4.0))
                image = cv2.GaussianBlur(image, (0, 0), sigma)
                blur = {"type": "focus", "sigma": round(sigma, 2)}
            else:
                length = int(rng.integers(7, 22))
                image = cv2.filter2D(image, -1, motion_kernel(length, float(rng.uniform(0, 180))))
                blur = {"type": "motion", "length": length}
        out_name = f"{i:05d}.png"
        Image.fromarray(image.clip(0, 255).astype(np.uint8)).save(out / "images" / out_name)
        Image.fromarray(label).save(out / "labels" / out_name)
        rows.append(
            {"name": out_name, "base": f"{base['video']}/{name}", "items": items, "blur": blur}
        )
    with (out / "list.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        split,
        f"문제 {len(rows)}개, 바탕 {len(bases)}장, 조각 {len(pieces)}개,",
        f"바탕 최대 {int(np.bincount(base_order).max())}번,",
        f"조각 최대 {int(piece_use.max()) if len(pieces) else 0}번",
        flush=True,
    )


def main() -> None:
    out = SYNTH_DIR
    rng = np.random.default_rng(SEED)
    for arg in sys.argv[1:]:
        split, folder = arg.split("=", 1)
        make_split(rng, split, Path(folder), out / split)


if __name__ == "__main__":
    main()
