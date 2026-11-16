import json

import numpy as np
import pytest

from app.schemas.guide_area import GaugeReference, GuideSet
from tools.gauge import synthetic_frame as sf
from tools.gauge.export_pipeline_spec import (
    CASES,
    SPEC_PATH,
    frames_of,
    guide_set,
    pipeline,
    read_png,
    spec,
)

SAVED = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_shared_spec_matches_python_rule():
    """FE가 읽는 사진 시험 데이터가 파이썬 기준 구현과 같아야 한다.

    measure · baseline · synthetic_frame을 고친 뒤 tools/gauge/export_pipeline_spec.py를 다시 돌리지
    않으면 여기서 걸린다.
    """
    assert SAVED == spec()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_png_files_hold_the_same_frames(case):
    starts, nows, _ = frames_of(case, [guide_set(region) for region in case.regions])
    saved = next(c for c in SAVED["cases"] if c["name"] == case.name)

    for frame, path in zip(
        starts + nows, saved["frames"]["start"] + saved["frames"]["now"], strict=True
    ):
        assert np.array_equal(read_png(path), frame)


@pytest.mark.parametrize("case", SAVED["cases"], ids=lambda case: case["name"])
def test_each_case_recomputes_from_its_files(case):
    """FE처럼 PNG · 얼굴 점 · guideSets · gauge만 읽어 같은 값이 나와야 시험 데이터가 혼자 선다."""
    starts = [read_png(path) for path in case["frames"]["start"]]
    nows = [read_png(path) for path in case["frames"]["now"]]
    sets = [GuideSet.model_validate(s) for s in case["guideSets"]]
    gauge = GaugeReference.model_validate(case["gauge"])

    assert (
        pipeline(starts, nows, case["landmarks"], sets, gauge, case["makeup"]) == case["expected"]
    )


def test_cases_cover_pose_light_sides_dark_makeup_and_several_frames():
    names = {case.name for case in CASES}
    poses = {case.pose for case in CASES}

    assert poses == {"front", "turn", "roll", "far"}
    assert any(case.light.exposure != 1.0 for case in CASES)
    assert any(len(case.regions) == 2 and len(set(case.user)) == 2 for case in CASES)
    assert any(case.makeup == "brow" for case in CASES)
    assert any(len(case.start_offsets) > 1 for case in CASES)
    assert len(names) == len(CASES)


def test_cartoon_face_has_no_real_face_and_fills_every_part():
    face = sf.cartoon_face()

    for color in (sf.BROW, sf.LIP, sf.MOUTH, sf.SCLERA, sf.IRIS):
        assert (face == np.asarray(color)).all(axis=-1).any()
