"""사진에서 얼굴을 가린 것을 찾는 함수의 모양.

가린 것은 손·붓·퍼프·제품·머리카락·자막처럼 얼굴이 아닌 모든 것이다.
찾는 함수는 사진 정보(얼굴 점)와 사진 1장의 RGB 배열을 받아,
사진 크기 참·거짓 표(가린 픽셀이 True)를 돌려준다.
부위 분석은 이 표를 얼굴 지도에 펴서 사진마다 가린 칸을 빼고 본다(rows_to_known_map).
서비스는 가림 찾기 모델을 쓰는 occlusion_finder.find_occlusion을 remember_by_frame으로 감싸 넘긴다.
"""

from collections import OrderedDict
from collections.abc import Callable

import numpy as np

from app.schemas.landmarks import FrameLandmarks

OcclusionFinder = Callable[[FrameLandmarks, np.ndarray], np.ndarray]


def remember_by_frame(find: OcclusionFinder, keep: int) -> OcclusionFinder:
    """사진 번호로 가림 결과를 기억해 두고, 같은 사진이 다시 오면 찾지 않고 돌려주는 함수.

    좌우 짝 부위(눈썹·섀도·아이라인·볼)는 쪽마다 같은 직전·직후 사진을 쓰므로,
    영역 작업 하나에서 같은 사진이 두 번 들어온다. 가장 최근 keep장만 기억하고,
    표는 비트로 눌러 둬서 1080p 사진 1장에 약 260KB다. 작업마다 새로 만들어 쓴다.
    """
    kept: OrderedDict[int, tuple[np.ndarray, tuple[int, int]]] = OrderedDict()

    def find_once(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
        hit = kept.get(row.frame_index)
        if hit is not None:
            kept.move_to_end(row.frame_index)
            bits, shape = hit
            return np.unpackbits(bits, count=shape[0] * shape[1]).reshape(shape).astype(bool)
        mask = find(row, photo)
        kept[row.frame_index] = (np.packbits(mask), mask.shape)
        if len(kept) > keep:
            kept.popitem(last=False)
        return mask

    return find_once
