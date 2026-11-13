"""학습 정답지 한 건의 모양과, 칸 표를 정답 그림으로 바꾸는 규칙(개발용).

정답지 한 건은 폴더 하나다.
- before.png·after.png: 단계 직전·직후 얼굴 지도(MAP_SIZE × MAP_SIZE RGB). 모델 입력이다.
- label.png: 칸마다 바른 부위 번호(CLASSES 순서, 0은 안 바름). 모름 칸은 IGNORE이고 학습에서 뺀다.
- strength.png: 합성 정답지에만 있다. 칸마다 칠한 진하기(0~255, 255가 색을 완전히 덮음)다.
정답지 목록은 나눔·출처 폴더의 list.jsonl이고 한 줄이 한 건이다.

모름 칸은 얼굴 밖 칸, 직전이나 직후 지도에서 모든 사진에 가려진 칸,
합성에서 옅게 번진 가장자리, 실제 장면에서 창을 옮기면 찾았다 말았다 하는 칸이다.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import cv2
import numpy as np

CLASSES = (
    "none",
    "lip",
    "blush",
    "brow",
    "eyeshadowUpper",
    "eyeshadowUnder",
    "eyelinerUpper",
    "eyelinerUnder",
)
CLASS_IDS = {name: number for number, name in enumerate(CLASSES)}
PART_CLASSES: dict[str, tuple[str, ...]] = {
    "lip": ("lip",),
    "blush": ("blush",),
    "brow": ("brow",),
    "eyeshadow": ("eyeshadowUpper", "eyeshadowUnder"),
    "eyeliner": ("eyelinerUpper", "eyelinerUnder"),
}
ZONE_CLASSES = {
    ("eyeshadow", "upper"): "eyeshadowUpper",
    ("eyeshadow", "under"): "eyeshadowUnder",
    ("eyeliner", "upper"): "eyelinerUpper",
    ("eyeliner", "under"): "eyelinerUnder",
}
DEFAULT_ZONES = ("upper", "under")
IGNORE = 255
ON_SHARE = 0.5
EDGE_SHARE = 0.1
LIST_FILE = "list.jsonl"
COLORS = {
    "lip": (255, 0, 80),
    "blush": (255, 140, 0),
    "brow": (0, 200, 255),
    "eyeshadowUpper": (170, 0, 255),
    "eyeshadowUnder": (0, 255, 120),
    "eyelinerUpper": (255, 255, 0),
    "eyelinerUnder": (0, 90, 255),
}


def label_map(
    painted: Mapping[str, np.ndarray],
    unsure: np.ndarray | None,
    face: np.ndarray,
) -> np.ndarray:
    """부위마다 바른 칸 표(painted)를 정답 그림 한 장으로 합친다.

    painted는 부위 이름(CLASSES) → 지도 크기 참·거짓 표다. 뒤에 온 부위가 앞 부위 위에 적힌다.
    unsure(모름 칸)와 얼굴 밖 칸(face가 False)은 IGNORE다.
    """
    out = np.zeros(face.shape, dtype=np.uint8)
    for name, cells in painted.items():
        out[cells] = CLASS_IDS[name]
    if unsure is not None:
        out[unsure] = IGNORE
    out[~face] = IGNORE
    return out


def strength_cells(strength: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """칠한 진하기 지도(0~1)에서 (바른 칸, 모름 칸)을 낸다.

    가장 진한 칸의 ON_SHARE 이상이면 바른 칸, EDGE_SHARE 이상 ON_SHARE 미만이면 모름 칸이다.
    흐린 가장자리는 어디까지가 바른 곳인지 정할 수 없어 학습에서 뺀다.
    하나도 칠하지 않았으면 둘 다 빈 표다.
    """
    peak = float(strength.max())
    if peak <= 0:
        empty = np.zeros(strength.shape, dtype=bool)
        return empty, empty.copy()
    on = strength >= ON_SHARE * peak
    edge = (strength >= EDGE_SHARE * peak) & ~on
    return on, edge


def agreed_cells(masks: Sequence[np.ndarray | None]) -> tuple[np.ndarray, np.ndarray] | None:
    """창을 옮긴 조합마다 찾은 칸 표에서 (모든 조합이 찾은 칸, 일부 조합만 찾은 칸)을 낸다.

    한 조합이라도 못 찾았으면(None) None이다. 그 단계·부위는 정답으로 쓰지 않는다.
    """
    if not masks or any(mask is None for mask in masks):
        return None
    stacked = np.stack(masks)
    every = stacked.all(axis=0)
    return every, stacked.any(axis=0) & ~every


def looked_classes(makeup: str, zones: Sequence[str] | None) -> list[str]:
    """이 단계에서 서비스가 살펴보는 자리의 이름(CLASSES).

    아이섀도·아이라인은 단계 글로 고른 자리(zones)이고 모르면 위·아래 둘 다다.
    아이라인 윗점막(waterline)은 색으로 찾지 않아 뺀다.
    """
    if makeup not in ("eyeshadow", "eyeliner"):
        return list(PART_CLASSES[makeup])
    return [
        ZONE_CLASSES[(makeup, zone)] for zone in (zones or DEFAULT_ZONES) if zone != "waterline"
    ]


def step_label(
    combos: Sequence[Mapping[str, np.ndarray | None]],
    unknown: np.ndarray,
    face: np.ndarray,
    ranges: Mapping[str, np.ndarray],
) -> tuple[np.ndarray, list[str], list[str]] | None:
    """조합마다 자리별로 찾은 칸(combos)에서 (정답 그림, 믿을 자리, 못 믿을 자리)를 낸다.

    모든 조합이 찾은 자리가 하나도 없으면 None이다. 못 믿을 자리는 서비스가 살펴보는 범위
    (ranges의 그 자리 표)를 통째로 모름으로 둔다. 발랐는지 알 수 없는 곳을 안 바름으로 가르치지
    않으려는 것이다. unknown(직전이나 직후에서 모든 사진이 가려진 칸)도 모름이다.
    """
    cells: dict[str, np.ndarray] = {}
    unsure = unknown.copy()
    unstable = []
    for name in combos[0]:
        agreed = agreed_cells([combo[name] for combo in combos])
        if agreed is None:
            unstable.append(name)
            unsure |= ranges[name]
            continue
        cells[name], partly = agreed
        unsure |= partly
    if not cells:
        return None
    return label_map(cells, unsure, face), list(cells), unstable


def class_cells(label: np.ndarray) -> dict[str, int]:
    """정답 그림에서 부위마다 칸 수와 모름 칸 수(ignore)."""
    counts = {name: int((label == number).sum()) for name, number in CLASS_IDS.items()}
    counts["ignore"] = int((label == IGNORE).sum())
    return counts


def save_sample(
    folder: Path,
    before: np.ndarray,
    after: np.ndarray,
    label: np.ndarray,
    strength: np.ndarray | None = None,
) -> None:
    """정답지 한 건을 folder에 쓴다. strength는 0~1 지도이고 0~255로 바꿔 쓴다."""
    folder.mkdir(parents=True, exist_ok=True)
    write_png(folder / "before.png", cv2.cvtColor(before, cv2.COLOR_RGB2BGR))
    write_png(folder / "after.png", cv2.cvtColor(after, cv2.COLOR_RGB2BGR))
    write_png(folder / "label.png", label)
    if strength is not None:
        write_png(folder / "strength.png", np.round(strength * 255).clip(0, 255).astype(np.uint8))


def write_png(path: Path, image: np.ndarray) -> None:
    """한글이 든 경로에도 쓸 수 있게 PNG로 눌러 파일에 쓴다."""
    path.write_bytes(cv2.imencode(".png", image)[1].tobytes())


def read_png(path: Path, color: bool = False) -> np.ndarray:
    """PNG를 읽는다. color가 참이면 RGB, 아니면 한 겹 그대로다."""
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    if not color:
        return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    return cv2.cvtColor(cv2.imdecode(data, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def write_list(folder: Path, rows: Sequence[Mapping]) -> None:
    """정답지 목록을 folder/list.jsonl에 쓴다. 이름 순서로 적는다."""
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / LIST_FILE).open("w", encoding="utf-8") as file:
        for row in sorted(rows, key=lambda row: row["name"]):
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_list(folder: Path) -> list[dict]:
    """folder/list.jsonl의 줄들. 파일이 없으면 빈 목록이다."""
    path = folder / LIST_FILE
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def overlay(image: np.ndarray, label: np.ndarray) -> np.ndarray:
    """얼굴 지도 위에 정답을 겹친 품질 그림(RGB). 바른 칸은 부위 색 테두리, 모름 칸은 회색 줄무늬다.

    칸을 색으로 덮으면 밑의 화장이 안 보여서 테두리만 긋는다.
    """
    out = image.copy()
    rows, cols = np.indices(label.shape)
    hidden = (label == IGNORE) & ((rows + cols) % 8 < 2)
    out[hidden] = (out[hidden] * 0.5 + 64).astype(np.uint8)
    for name, color in COLORS.items():
        cells = (label == CLASS_IDS[name]).astype(np.uint8)
        if not cells.any():
            continue
        outlines, _ = cv2.findContours(cells, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(out, outlines, -1, color, 2)
    return out
