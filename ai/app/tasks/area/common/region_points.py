"""부위마다 테두리를 한 바퀴 도는 얼굴 점 번호와 각도 기준 두 점.

FE와 같이 쓰는 shared/face-mesh/regions.v1.json의 indices · axis를 읽는다.
번호를 따로 옮겨 적지 않는다.
"""

import json
from typing import get_args

from app.core.paths import FACE_MESH_DIR
from app.schemas.guide_area import RegionName

REGIONS_PATH = FACE_MESH_DIR / "regions.v1.json"

_REGIONS = json.loads(REGIONS_PATH.read_text(encoding="utf-8"))["regions"]

REGION_POINTS: dict[RegionName, tuple[int, ...]] = {
    name: tuple(_REGIONS[name]["indices"]) for name in get_args(RegionName)
}

REGION_AXIS: dict[RegionName, tuple[int, int]] = {
    name: tuple(_REGIONS[name]["axis"]) for name in get_args(RegionName)
}
