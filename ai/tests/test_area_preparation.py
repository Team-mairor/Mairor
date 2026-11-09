import numpy as np
import pytest

from app.schemas.landmarks import FrameLandmarks, ImageSize, LandmarksResult, Point
from app.tasks.area.common.face_map import MAP_SIZE, flatten, median_map
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.frame_checker import outside_count_name
from app.tasks.area.parts import area_preparation
from app.tasks.area.parts.area_preparation import (
    EYE_OPEN_POINTS,
    RememberedPhotos,
    eye_openness,
    known_median_map,
    match_sizes,
    mostly_unknown,
    remove_lighting,
    rgb_to_lab,
    rows_to_known_map,
    rows_to_map,
    usable_rows,
)
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


def test_lighting_change_on_skin_is_removed_and_makeup_stays():
    exclude = np.zeros((200, 200), dtype=bool)
    exclude[80:120, 80:120] = True
    change = np.full((200, 200), 4.0, dtype=np.float32)
    change[90:110, 90:110] += 6.0
    corrected = remove_lighting(change, exclude)
    assert np.abs(corrected[~exclude]).max() < 0.01
    assert abs(corrected[100, 100] - 6.0) < 0.01


def test_unknown_cells_are_left_out_of_lighting_and_count_as_no_change():
    exclude = np.zeros((200, 200), dtype=bool)
    unknown = np.zeros((200, 200), dtype=bool)
    unknown[80:120, 80:120] = True
    change = np.full((200, 200), 4.0, dtype=np.float32)
    change[unknown] = 40.0
    corrected = remove_lighting(change, exclude, unknown)
    assert np.abs(corrected).max() < 0.01


def test_lighting_is_removed_place_by_place():
    exclude = np.zeros((200, 400), dtype=bool)
    change = np.zeros((200, 400), dtype=np.float32)
    change[:, 200:] = -5.0
    corrected = remove_lighting(change, exclude)
    assert np.abs(corrected[:, :50]).max() < 0.1
    assert np.abs(corrected[:, 350:]).max() < 0.1


def hand_over(index: int, half: int = 40) -> np.ndarray:
    """가짜 얼굴 사진(800 × 600)에서 얼굴 점 index 둘레 half픽셀을 손이 가린 자리(사진 크기 표)."""
    x, y = round(UV[index, 0] * 800), round(UV[index, 1] * 600)
    mask = np.zeros((600, 800), dtype=bool)
    mask[y - half : y + half, x - half : x + half] = True
    return mask


def finds_hand_color(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
    """손 색 픽셀을 가린 곳으로 찾는 가짜 가림 찾기."""
    return np.all(photo == HAND, axis=2)


def cell(index: int) -> tuple[int, int]:
    """얼굴 점 index가 놓인 지도 칸(행, 열)."""
    return round(UV[index, 1] * MAP_SIZE), round(UV[index, 0] * MAP_SIZE)


def photos_with_hands(hands: dict[int, np.ndarray | None]):
    """사진 시각마다 손 자리(없으면 None)를 받아 (사진 정보들, 사진 읽기 함수)를 만든다."""
    rows = [make_row(time) for time in hands]

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        photo = np.full((600, 800, 3), SKIN, dtype=np.uint8)
        hand = hands[row.timestamp_ms]
        if hand is not None:
            photo[hand] = HAND
        return photo

    return rows, load_photo


def test_map_stays_as_before_when_nothing_is_found_hidden():
    rows, load_photo = photos_with_hands({1000: None, 2000: hand_over(13), 3000: hand_over(13)})
    before = median_map([flatten(load_photo(row), row.face) for row in rows])
    for occlusion in (None, lambda row, photo: np.zeros(photo.shape[:2], dtype=bool)):
        out, unknown = rows_to_known_map(rows, load_photo, occlusion)
        assert np.array_equal(out, before)
        assert not unknown.any()


def test_hand_held_over_most_photos_is_left_out_when_one_photo_shows_skin():
    rows, load_photo = photos_with_hands({1000: None, 2000: hand_over(13), 3000: hand_over(13)})
    assert tuple(rows_to_map(rows, load_photo)[cell(13)]) == HAND
    out, unknown = rows_to_known_map(rows, load_photo, finds_hand_color)
    assert tuple(out[cell(13)]) == SKIN
    assert not unknown.any()


def test_cells_hidden_in_every_photo_are_unknown():
    rows, load_photo = photos_with_hands({1000: hand_over(13), 2000: hand_over(13)})
    out, unknown = rows_to_known_map(rows, load_photo, finds_hand_color)
    assert unknown[cell(13)]
    assert not unknown[cell(9)]
    assert tuple(out[cell(13)]) == HAND


def test_margin_widens_hidden_cells(monkeypatch):
    rows, load_photo = photos_with_hands({1000: hand_over(13), 2000: hand_over(13)})
    _, tight = rows_to_known_map(rows, load_photo, finds_hand_color)
    monkeypatch.setattr(area_preparation, "OCCLUSION_MARGIN_CELLS", 10)
    _, wide = rows_to_known_map(rows, load_photo, finds_hand_color)
    assert not (tight & ~wide).any()
    assert wide.sum() > tight.sum()


def counted(load_photo):
    """부를 때마다 사진 시각을 적는 사진 읽기 함수와 그 기록을 돌려준다."""
    reads = []

    def load(row: FrameLandmarks) -> np.ndarray:
        reads.append(row.timestamp_ms)
        return load_photo(row)

    return load, reads


def test_remembered_photos_read_and_find_each_photo_once():
    """좌우 짝 부위처럼 같은 사진 묶음을 두 번 넘겨도 사진 읽기와 가림 찾기는 사진마다 한 번이다."""
    rows, load_photo = photos_with_hands({1000: None, 2000: hand_over(13), 3000: None})
    load, reads = counted(load_photo)
    found = []

    def occlusion(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
        found.append(row.timestamp_ms)
        return finds_hand_color(row, photo)

    photos = RememberedPhotos(load, keep=64)
    rows_to_known_map(rows, photos, occlusion)
    rows_to_known_map(rows[1:], photos, occlusion)

    assert reads == [1000, 2000, 3000]
    assert found == [1000, 2000, 3000]


def test_remembered_photos_give_the_same_maps_as_plain_loader():
    rows, load_photo = photos_with_hands({1000: None, 2000: hand_over(13), 3000: hand_over(13)})
    plain_map, plain_unknown = rows_to_known_map(rows, load_photo, finds_hand_color)
    photos = RememberedPhotos(load_photo, keep=64)
    rows_to_known_map(rows, photos, finds_hand_color)

    remembered_map, remembered_unknown = rows_to_known_map(rows, photos, finds_hand_color)

    assert np.array_equal(remembered_map, plain_map)
    assert np.array_equal(remembered_unknown, plain_unknown)


def test_remembered_photos_forget_the_oldest_photo_past_keep():
    rows, load_photo = photos_with_hands({1000: None, 2000: None})
    load, reads = counted(load_photo)
    photos = RememberedPhotos(load, keep=1)

    for row in (rows[0], rows[1], rows[0]):
        photos.face_maps(row, None)

    assert reads == [1000, 2000, 1000]


def test_remembered_maps_cannot_be_changed():
    """기억한 지도를 꺼내 쓰는 쪽이 고치면, 다음에 꺼내 쓰는 쪽이 고친 지도를 받게 된다."""
    rows, load_photo = photos_with_hands({1000: None})
    face_map, covered = RememberedPhotos(load_photo, keep=64).face_maps(rows[0], finds_hand_color)

    with pytest.raises(ValueError):
        face_map[0, 0] = 0
    with pytest.raises(ValueError):
        covered[0, 0] = True


def test_known_median_map_uses_only_photos_that_show_each_cell():
    skin = np.full((2, 2, 3), SKIN, dtype=np.uint8)
    hand = np.full((2, 2, 3), HAND, dtype=np.uint8)
    corner = np.zeros((2, 2), dtype=bool)
    corner[0, 0] = True
    maps = [skin, hand, hand]

    plain, none_hidden = known_median_map(maps)
    out, unknown = known_median_map(maps, [np.zeros_like(corner), corner, corner])

    assert np.array_equal(plain, median_map(maps)) and not none_hidden.any()
    assert tuple(out[0, 0]) == SKIN and tuple(out[1, 1]) == HAND
    assert not unknown.any()
    assert known_median_map(maps, [corner, corner, corner])[1][0, 0]


def with_eyes(row: FrameLandmarks, openness: float) -> FrameLandmarks:
    """두 눈의 점 6개를 가로 80px, 세로 openness × 80px로 다시 놓은 사진.

    눈 뜬 정도가 openness다.
    """
    width, height = row.image_size.width, row.image_size.height
    points = list(row.face.landmarks)
    for left, top_a, top_b, right, bottom_b, bottom_a in EYE_OPEN_POINTS:
        x0, y = points[left].x, points[left].y
        dx, dy = 80 / width, openness * 80 / height
        points[left] = Point(x=x0, y=y, z=0.0)
        points[right] = Point(x=x0 + dx, y=y, z=0.0)
        for top, bottom, at in ((top_a, bottom_a, 1 / 3), (top_b, bottom_b, 2 / 3)):
            points[top] = Point(x=x0 + dx * at, y=y - dy / 2, z=0.0)
            points[bottom] = Point(x=x0 + dx * at, y=y + dy / 2, z=0.0)
    face = row.face.model_copy(update={"landmarks": points})
    return row.model_copy(update={"face": face})


def test_eye_openness_is_height_over_width_of_the_smaller_eye():
    assert abs(eye_openness(with_eyes(make_row(1000), 0.35)) - 0.35) < 1e-6


def test_half_closed_eyes_are_left_out_only_for_eye_parts():
    """눈 뜬 정도 0.15는 반쯤 감은 눈이라 섀도·아이라인에서 빼고, 0.25는 뜬 눈이라 쓴다."""
    rows = [with_eyes(make_row(1000), 0.15), with_eyes(make_row(2000), 0.25)]

    assert picked(rows, 0, 3000, ["leftEye"]) == [2000]
    assert picked(rows, 0, 3000, ["leftEye", "leftBrow"]) == [2000]
    assert picked(rows, 0, 3000, ["leftCheek"]) == [1000, 2000]


def sized(timestamp_ms: int, width_px: float) -> FrameLandmarks:
    row = make_row(timestamp_ms)
    return row.model_copy(update={"measures": {**row.measures, "faceWidthPx": width_px}})


def test_sizes_inside_the_range_are_kept_as_they_are():
    before = [sized(1000, 400), sized(2000, 420)]
    after = [sized(5000, 380)]

    assert match_sizes(before, after) == (before, after)


def test_bigger_group_keeps_only_photos_close_to_the_other_size():
    """직후 ÷ 직전이 300 ÷ 400 = 0.75라 범위 밖이다.

    사진이 많은 직전에서 300의 1.25배(375px) 이하만 남는다.
    """
    before = [sized(1000, 400), sized(2000, 400), sized(3000, 400), sized(4000, 370)]
    after = [sized(5000, 300), sized(6000, 300)]

    kept_before, kept_after = match_sizes(before, after)

    assert [row.timestamp_ms for row in kept_before] == [4000]
    assert kept_after == after


def test_no_photo_close_enough_leaves_the_group_empty():
    before = [sized(1000, 400), sized(2000, 400)]
    after = [sized(5000, 300)]

    assert match_sizes(before, after) == ([], after)


def test_sizes_are_not_matched_without_face_width():
    before, after = [make_row(1000)], [sized(5000, 300)]

    assert match_sizes(before, after) == (before, after)


def zone_and_cover(hidden_rows: int) -> tuple[np.ndarray, np.ndarray]:
    """10줄짜리 범위와, 그 범위의 위 hidden_rows줄을 가린 표."""
    zone = np.zeros((10, 4), dtype=bool)
    zone[:, :2] = True
    cover = np.zeros_like(zone)
    cover[:hidden_rows, :2] = True
    return zone, cover


def test_photo_hiding_more_than_a_fifth_of_the_zone_is_left_out():
    """범위를 30% 가린 사진은 보이는 칸까지 통째로 빼고, 10% 가린 사진은 보이는 칸을 쓴다."""
    skin = np.full((10, 4, 3), SKIN, dtype=np.uint8)
    red = np.full((10, 4, 3), RED, dtype=np.uint8)
    clear = np.zeros((10, 4), dtype=bool)

    zone, most = zone_and_cover(3)
    out, unknown = known_median_map([red, skin], [most, clear], zone)
    assert tuple(out[9, 0]) == SKIN and not unknown.any()

    zone, few = zone_and_cover(1)
    out, _ = known_median_map([red, red, skin], [few, clear, clear], zone)
    assert tuple(out[9, 0]) == RED


def test_every_photo_hiding_too_much_makes_every_cell_unknown():
    zone, most = zone_and_cover(3)
    skin = np.full((10, 4, 3), SKIN, dtype=np.uint8)

    _, unknown = known_median_map([skin, skin], [most, most], zone)

    assert unknown.all()


def test_range_is_mostly_unknown_past_half():
    cells = np.zeros((10, 4), dtype=bool)
    cells[:, :2] = True
    six, four = np.zeros_like(cells), np.zeros_like(cells)
    six[:6] = True
    four[:4] = True

    assert mostly_unknown(cells, six)
    assert not mostly_unknown(cells, four)
    assert not mostly_unknown(cells, None)
