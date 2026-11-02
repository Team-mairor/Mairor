import numpy as np

from app.schemas.landmarks import FrameLandmarks, ImageSize, LandmarksResult
from app.services.area_preparation import rgb_to_lab, rows_to_map, usable_rows
from app.services.face_map import MAP_SIZE
from app.services.frame_checker import outside_count_name
from app.services.region_points import REGION_POINTS
from tests.test_face_map import UV, face_on_map

SKIN = (232, 192, 172)
DARK_SKIN = (200, 160, 140)
RED = (200, 70, 80)
HAND = (90, 60, 50)


def make_row(timestamp_ms: int, outside: dict[str, float] | None = None) -> FrameLandmarks:
    """판정을 통과한 사진 한 장. outside에 적은 부위만 화면 밖 점이 있다."""
    measures = {outside_count_name(region): 0.0 for region in REGION_POINTS}
    measures.update({outside_count_name(r): count for r, count in (outside or {}).items()})
    return FrameLandmarks(
        frame_index=timestamp_ms,
        timestamp_ms=timestamp_ms,
        step_id=None,
        image_size=ImageSize(width=800, height=600),
        status="ok",
        measures={"faceWidthRatio": 1.0, **measures},
        face_count=1,
        face=face_on_map(),
    )


def picked(rows: list[FrameLandmarks], start_ms: int, end_ms: int, regions: list) -> list[int]:
    result = LandmarksResult(video_id="test_01", frames=rows)
    return [row.timestamp_ms for row in usable_rows(result, start_ms, end_ms, regions)]


def test_each_cheek_is_picked_on_its_own():
    rows = [make_row(1000), make_row(2000, {"leftCheek": 2})]
    assert picked(rows, 0, 3000, ["leftCheek"]) == [1000]
    assert picked(rows, 0, 3000, ["rightCheek"]) == [1000, 2000]


def test_every_listed_region_must_be_inside():
    rows = [make_row(1000, {"rightCheek": 1})]
    assert picked(rows, 0, 3000, ["leftCheek", "rightCheek"]) == []


def test_window_leaves_out_its_start_and_keeps_its_end():
    rows = [make_row(1000), make_row(1500), make_row(2000), make_row(2100)]
    assert picked(rows, 1000, 2000, ["lipsOuter"]) == [1500, 2000]


def test_photo_without_outside_count_is_not_used():
    row = make_row(1000)
    del row.measures[outside_count_name("leftCheek")]
    assert picked([row], 0, 3000, ["leftCheek"]) == []


def test_redness_stays_when_skin_gets_darker():
    skin, dark, red = rgb_to_lab(np.array([[SKIN, DARK_SKIN, RED]], dtype=np.uint8))[0]
    assert dark[0] < skin[0] - 10
    assert abs(dark[1] - skin[1]) < 1
    assert red[1] > skin[1] + 30


def test_map_keeps_the_color_most_photos_show():
    colors = {1000: SKIN, 2000: SKIN, 3000: HAND}
    rows = [make_row(time) for time in colors]

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        return np.full((600, 800, 3), colors[row.timestamp_ms], dtype=np.uint8)

    out = rows_to_map(rows, load_photo)
    assert tuple(out[round(UV[13, 1] * MAP_SIZE), round(UV[13, 0] * MAP_SIZE)]) == SKIN
