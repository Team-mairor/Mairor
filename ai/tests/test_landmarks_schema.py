import copy
import json

import pytest
from pydantic import ValidationError

from app.schemas.landmarks import LandmarksResult

POINT = {"x": 0.43, "y": 0.39, "z": -0.01}
FACE = {
    "landmarks": [POINT] * 478,
    "iod": 152.3,
    "pose": {"yaw": 0.05, "pitch": -0.1, "roll": 0.02},
}
GOOD = {
    "videoId": "local_01_seq",
    "meshVersion": "v1",
    "frames": [
        {
            "frameIndex": 15000,
            "timestampMs": 500000,
            "stepId": "s10",
            "imageSize": {"width": 1920, "height": 1080},
            "status": "noFace",
            "faceCount": 0,
            "face": None,
        },
        {
            "frameIndex": 15150,
            "timestampMs": 505000,
            "stepId": None,
            "imageSize": {"width": 1920, "height": 1080},
            "status": "ok",
            "faceCount": 1,
            "face": FACE,
        },
    ],
}

BROKEN = {
    "점 477개": lambda d: d["frames"][1]["face"]["landmarks"].pop(),
    "frameIndex 빠짐": lambda d: d["frames"][0].pop("frameIndex"),
    "얼굴 있는데 noFace": lambda d: d["frames"][1].update(status="noFace"),
    "얼굴 없는데 ok": lambda d: d["frames"][0].update(status="ok"),
    "faceCount 1인데 face 없음": lambda d: d["frames"][0].update(faceCount=1),
    "frameIndex 순서 뒤바뀜": lambda d: d["frames"].reverse(),
    "frameIndex 겹침": lambda d: d["frames"][1].update(frameIndex=15000),
    "meshVersion v2": lambda d: d.update(meshVersion="v2"),
}


def test_good_result_passes():
    result = LandmarksResult.model_validate(GOOD)

    assert result.frames[1].face is not None
    assert len(result.frames[1].face.landmarks) == 478


@pytest.mark.parametrize("change", BROKEN.values(), ids=BROKEN.keys())
def test_broken_result_is_rejected(change):
    data = copy.deepcopy(GOOD)
    change(data)

    with pytest.raises(ValidationError):
        LandmarksResult.model_validate(data)


def test_saved_keys_are_camel_case():
    saved = json.loads(LandmarksResult.model_validate(GOOD).model_dump_json(by_alias=True))

    assert list(saved["frames"][1]) == [
        "frameIndex",
        "timestampMs",
        "stepId",
        "imageSize",
        "status",
        "reasons",
        "measures",
        "faceCount",
        "face",
    ]
