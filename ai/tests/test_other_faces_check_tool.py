import json
from pathlib import Path

import numpy as np
import pytest

from app.schemas.landmarks import LANDMARK_COUNT, Face, Point, Pose
from app.tasks.area.common.face_map import MAP_SIZE, mesh_uv
from tools.other_faces_check import (
    WORSE_MARGIN,
    area_mask,
    area_shapes,
    baseline,
    flags,
    measure,
)

AREA_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_area.json"
SIZE = 512


def map_face() -> Face:
    """얼굴 점을 얼굴 지도 자리 그대로 놓은 얼굴.

    얼굴 주소가 지도 좌표와 같은 자리에 와서 계산을 따라가기 쉽다.
    """
    uv = mesh_uv() / MAP_SIZE
    points = [Point(x=float(x), y=float(y), z=0.0) for x, y in uv]
    points += [Point(x=0.5, y=0.5, z=0.0)] * (LANDMARK_COUNT - len(points))
    pose = Pose(yaw=0.0, pitch=0.0, roll=0.0)
    return Face(landmarks=points, pose=pose, frame_index=0, iod=0.1)


def lip_shape_with_hole() -> dict:
    """샘플의 찾은 입술 테두리에 입술 안쪽 구멍을 붙인 영역. 샘플에는 구멍이 있는 영역이 없다."""
    area = json.loads(AREA_SAMPLE.read_text(encoding="utf-8"))
    shape = next(s for s in area_shapes(area) if s["region"] == "lipsOuter")
    return {**shape, "exclude": ["lipsInner"]}


def test_lip_area_in_sample_reads_makeup_from_the_area_file():
    """화장 종류를 영역 파일 단계의 makeup 칸에서 읽는다.

    따로 넣는 입력이 없어도 립 · 눈썹 제자리 검사가 켜져야 옵션을 빠뜨려 검사가 꺼지는 일이 없다.
    """
    shape = lip_shape_with_hole()
    assert shape["makeup"] == "lip"


def anchor_area(status: str, guides: list[dict]) -> dict:
    return {"subStepId": "s1-1", "status": status, "guideSets": guides}


def test_only_extracted_polygons_are_checked():
    """기본 영역 · 영역 없음은 FE가 그리는 모양이라 AI 결과 점검에서 뺀다.

    화살표는 칸이 없어 빼고, 빼는 부위는 그대로 넘긴다.
    """
    anchor = {"triangle": 0, "bary": [1.0, 0.0, 0.0]}
    polygon = {"type": "polygon", "outline": [anchor, anchor, anchor]}
    arrow = {"type": "arrow", "from": anchor, "to": anchor}
    guide_set = {"region": "leftEye", "guides": [polygon, arrow], "exclude": ["leftEye"]}
    area = {
        "steps": [
            {
                "stepId": "s1",
                "makeup": "eyeliner",
                "subSteps": [
                    anchor_area("extracted", [guide_set]),
                    {"subStepId": "s1-2", "status": "template", "guideSets": []},
                ],
            },
            {
                "stepId": "s2",
                "makeup": "other",
                "subSteps": [{**anchor_area("notApplicable", []), "subStepId": "s2-1"}],
            },
        ]
    }
    shapes = area_shapes(area)
    summary = [(s["subStepId"], s["makeup"], len(s["outlines"]), s["exclude"]) for s in shapes]
    assert summary == [("s1-1", "eyeliner", 1, ["leftEye"])]


def test_excluded_region_is_cut_out_of_the_area():
    """FE는 빼는 부위를 구멍으로 그린다.

    구멍을 안 빼면 입술 안쪽 · 눈이 영역으로 세어져 눈 덮음 · 제자리 비율이 틀어진다.
    """
    shape = lip_shape_with_hole()
    face = map_face()
    with_hole = area_mask(shape, face, SIZE, SIZE)
    without_hole = area_mask({**shape, "exclude": []}, face, SIZE, SIZE)
    assert 0 < with_hole.sum() < without_hole.sum()
    assert not (with_hole & ~without_hole).any()


def test_shares_are_counted_from_part_labels():
    """얼굴 밖 · 머리카락 · 눈 · 제자리 비율이 칸 번호대로 나뉘는지 본다.

    머리카락을 얼굴 밖과 따로 세야 앞머리가 눈썹을 덮은 경우를 배치 오류와 가를 수 있다.
    """
    mask = np.ones((1, 10), dtype=bool)
    labels = np.array([[0, 17, 17, 4, 2, 2, 2, 1, 1, 19]], dtype=np.uint8)
    value = measure(mask, labels, "brow")
    assert value == {"cells": 10, "outside": 0.1, "hair": 0.2, "eyeCover": 0.1, "onTarget": 0.3}
    assert measure(mask, labels, "blush")["onTarget"] is None
    assert measure(np.zeros((1, 10), dtype=bool), labels, "brow")["outside"] is None


def test_baseline_is_the_middle_of_source_photos():
    """원래 얼굴 사진 한 장이 손에 가려져도 기준이 흔들리지 않게 가운데 값을 쓴다."""
    rows = [
        {"subStepId": "s1-1", "region": "leftBrow", "outside": v, "eyeCover": 0.0, "onTarget": t}
        for v, t in ((0.0, 0.8), (0.1, 0.0), (0.0, 0.7))
    ]
    expected = {"outside": 0.0, "eyeCover": 0.0, "onTarget": 0.7}
    assert baseline(rows)[("s1-1", "leftBrow")] == expected


def value_of(outside: float, hair: float, on_target: float) -> dict:
    return {"outside": outside, "hair": hair, "eyeCover": 0.0, "onTarget": on_target}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (value_of(WORSE_MARGIN + 0.05, 0.0, 0.8), ["outside"]),
        (value_of(WORSE_MARGIN - 0.05, 0.0, 0.8), []),
        (value_of(0.0, 0.5, 0.3), ["onTarget(hair)"]),
        (value_of(0.0, 0.0, 0.3), ["onTarget"]),
    ],
)
def test_only_clearly_worse_than_source_is_flagged(value, expected):
    """원래 얼굴보다 WORSE_MARGIN 넘게 나쁠 때만 큰 오류다.

    머리카락이 덮어 눈썹 위가 아니면 이유를 붙여 배치 오류와 가른다.
    """
    base = {"outside": 0.0, "eyeCover": 0.0, "onTarget": 0.8}
    assert flags(value, base) == expected
