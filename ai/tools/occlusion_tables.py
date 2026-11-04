"""미리 만들어 둔 사진별 가림 표를 지표 도구와 판정 도구에 넘긴다(개발용).

noise_metric·stability_metric·boundary_metric·timing_metric·guide_scorecard는
--occlusion <이름>을 받으면 <샘플 폴더>/output/occlusion/<이름>/masks/의 가림 표로 사진마다
가린 칸을 빼고 재고, 결과는 지금 결과를 덮지 않게 output/occlusion/<이름>/에 둔다.
가림 표는 사진 번호 6자리 이름의 흑백 PNG(사진 크기, 가린 픽셀이 흰색)이고,
가림 찾기 모델로 따로 만든다.
"""

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas.landmarks import FrameLandmarks
from app.tasks.area.landmarks.occlusion import OcclusionFinder

OUTPUT_DIR = Path("output")
OCCLUSION_DIR = OUTPUT_DIR / "occlusion"
MASKS_DIR = "masks"
OPTION = "--occlusion"
USAGE = f"[{OPTION} <가림 표 이름>]"
TABLE_CACHE = 600


def split_occlusion(args: Sequence[str]) -> tuple[list[str], str | None]:
    """명령 인자에서 --occlusion <이름>을 떼어 (나머지 인자, 이름)을 돌려준다.

    --occlusion이 없으면 이름은 None이고, 뒤에 이름이 없으면 사용법을 알리고 끝낸다.
    """
    args = list(args)
    if OPTION not in args:
        return args, None
    at = args.index(OPTION)
    if at + 1 >= len(args):
        raise SystemExit(f"{OPTION} 뒤에 가림 표 이름을 적으세요.")
    return args[:at] + args[at + 2 :], args[at + 1]


def output_dir(folder: Path, name: str | None) -> Path:
    """결과를 둘 폴더. 이름이 없으면 output/, 있으면 output/occlusion/<이름>/이다."""
    return folder / (OUTPUT_DIR if name is None else OCCLUSION_DIR / name)


def table_finder(folder: Path, name: str | None) -> OcclusionFinder | None:
    """<이름>의 가림 표를 사진 번호로 읽는 가림 찾기 함수. 이름이 없으면 None이다.

    가림 표 폴더가 없으면 알리고 끝낸다. 사진 번호의 표가 없으면 FileNotFoundError,
    표 크기가 사진과 다르면 ValueError를 낸다.
    표가 빠지거나 다른 영상 것이면 조용히 넘어가지 않게 하려는 것이다.
    """
    if name is None:
        return None
    masks = folder / OCCLUSION_DIR / name / MASKS_DIR
    if not masks.is_dir():
        raise SystemExit(f"{masks}가 없습니다. 먼저 가림 표를 만드세요.")

    @lru_cache(maxsize=TABLE_CACHE)
    def read(index: int) -> np.ndarray:
        return np.asarray(Image.open(masks / f"{index:06d}.png").convert("L")) > 127

    def finder(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
        table = read(row.frame_index)
        if table.shape != photo.shape[:2]:
            raise ValueError(f"{row.frame_index}번 가림 표 크기 {table.shape}가 사진과 다릅니다")
        return table

    return finder
