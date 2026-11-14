import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.schemas.landmarks import FrameLandmarks, ImageSize, LandmarksResult, Point
from app.tasks.area.common.face_map import MAP_SIZE, flatten, median_map
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.frame_checker import outside_count_name
from app.tasks.area.parts import (
    area_preparation,
    blush_area,
    brow_area,
    eyeliner_area,
    eyeshadow_area,
    lip_area,
)
from app.tasks.area.parts.area_preparation import (
    EYE_OPEN_POINTS,
    RememberedPhotos,
    drop_blurry,
    eye_openness,
    known_median_map,
    match_sizes,
    mostly_unknown,
    recording_dropped,
    remove_lighting,
    rgb_to_lab,
    rows_to_known_map,
    rows_to_map,
    step_bounds,
    usable_rows,
    within_step,
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


def test_step_bounds_are_the_previous_end_and_the_next_start():
    """앞뒤 단계는 화장 종류와 상관없이 order 순서로 바로 붙은 단계다. 처음·끝은 한쪽이 없다."""
    steps = [
        SimpleNamespace(step_id="b", order=2, start_seconds=10.0, end_seconds=20.0),
        SimpleNamespace(step_id="a", order=1, start_seconds=0.0, end_seconds=8.0),
        SimpleNamespace(step_id="c", order=3, start_seconds=21.5, end_seconds=30.0),
    ]

    assert step_bounds(steps) == {
        "a": (None, 10_000),
        "b": (8_000, 21_500),
        "c": (20_000, None),
    }


def test_photos_of_neighbor_steps_are_left_out_inside_a_step():
    """직전 창이 앞 단계 끝에, 직후 창이 다음 단계 시작에 걸치면 다른 화장 장면이 섞인다.

    경계 시각과 그 바깥 사진은 빼고, 빠진 이유를 neighborStep으로 남겨야
    운영 기록에서 보여서 고른 경우다.
    밖에서는 자르지 않는다.
    """
    rows = [make_row(t) for t in (7_500, 8_000, 8_500, 9_500, 20_500, 21_000, 21_500, 22_000)]
    result = LandmarksResult(video_id="test_01", frames=rows)

    with recording_dropped() as dropped, within_step(8_000, 21_500):
        before = usable_rows(result, 7_000, 10_000, ["lipsOuter"])
        after = usable_rows(result, 20_000, 23_000, ["lipsOuter"])

    assert [row.timestamp_ms for row in before] == [8_500, 9_500]
    assert [row.timestamp_ms for row in after] == [20_500, 21_000]
    assert dropped["neighborStep"] == {7_500, 8_000, 21_500, 22_000}
    assert picked(rows, 7_000, 10_000, ["lipsOuter"]) == [7_500, 8_000, 8_500, 9_500]


def test_window_cut_to_nothing_falls_back_to_the_whole_window():
    """창 전체가 앞 단계 시간에 들어가 자르면 남는 사진이 없을 때는 자르지 않은 창을 쓴다.

    BE가 한 번에 바른 것을 끝과 시작이 붙은 단계로 나누면 경계에 깨끗한 사진이 원래 없다.
    그때 기본 가이드로 버리면 창 떼기 전보다 나빠져서 고른 경우다.
    되돌린 사진은 빠진 것으로 세지 않는다.
    """
    rows = [make_row(t) for t in (7_000, 7_500, 8_000)]
    result = LandmarksResult(video_id="test_01", frames=rows)

    with recording_dropped() as dropped, within_step(8_000, None):
        kept = usable_rows(result, 6_000, 8_000, ["lipsOuter"])

    assert [row.timestamp_ms for row in kept] == [7_000, 7_500, 8_000]
    assert "neighborStep" not in dropped


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


def test_remembered_photos_make_a_photo_once_when_two_threads_ask_together():
    """줄들이 한 꾸러미를 같이 쓴다. 같은 사진을 두 스레드가 같이 찾아도 한 번만 읽고 펴야 한다.

    먼저 온 스레드가 사진을 읽는 동안 다른 스레드가 같은 사진을 찾게 해 고른 경우다.
    두 번째 스레드도 사진을 읽으러 오면 바로 드러나고, 오지 않으면 첫 스레드가 0.5초 기다린 뒤
    끝낸다.
    """
    rows, load_photo = photos_with_hands({1000: None})
    reading, read_again = threading.Event(), threading.Event()
    reads = []

    def load(row: FrameLandmarks) -> np.ndarray:
        reads.append(row.timestamp_ms)
        if len(reads) == 1:
            reading.set()
            read_again.wait(0.5)
        else:
            read_again.set()
        return load_photo(row)

    photos = RememberedPhotos(load, keep=64)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(photos.face_maps, rows[0], None)
        assert reading.wait(10)
        second = pool.submit(photos.face_maps, rows[0], None)
        first_map, second_map = first.result()[0], second.result()[0]

    assert reads == [1000]
    assert first_map is second_map


def test_remembered_photos_do_not_keep_a_photo_that_failed():
    """읽다 오류가 난 사진을 기억하면 다음에 찾는 쪽이 같은 오류만 받는다. 다시 읽게 한다."""
    rows, load_photo = photos_with_hands({1000: None})
    reads = []

    def load(row: FrameLandmarks) -> np.ndarray:
        reads.append(row.timestamp_ms)
        if len(reads) == 1:
            raise OSError("읽을 수 없는 사진")
        return load_photo(row)

    photos = RememberedPhotos(load, keep=64)
    with pytest.raises(OSError):
        photos.face_maps(rows[0], None)

    assert photos.face_maps(rows[0], None)[0] is not None
    assert reads == [1000, 1000]


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


def textured_photo(blur_sigma: float = 0.0) -> np.ndarray:
    """얼굴 지도에 펴면 칸마다 밝기가 달라 경계가 많은 무늬 사진(800 × 600).

    blur_sigma를 주면 그만큼 흐리게 해서 초점이 나간 사진을 흉내 낸다.
    """
    photo = np.random.default_rng(0).integers(60, 200, size=(600, 800, 3), dtype=np.uint8)
    return photo if blur_sigma == 0 else cv2.GaussianBlur(photo, (0, 0), blur_sigma)


def photos_by_time(photos: dict[int, np.ndarray]):
    """사진 시각마다 사진을 받아 (사진 정보들, 사진 읽기 함수)를 만든다."""
    rows = [make_row(time) for time in photos]
    return rows, lambda row: photos[row.timestamp_ms]


def times(rows: list[FrameLandmarks]) -> list[int]:
    return [row.timestamp_ms for row in rows]


def test_photo_much_blurrier_than_the_step_photos_is_dropped_and_recorded():
    """직전·직후를 합친 사진들 가운데 선명도의 BLUR_SHARE배 미만인 사진만 빼고 이유를 모은다."""
    rows, load = photos_by_time(
        {1000: textured_photo(8), 2000: textured_photo(), 5000: textured_photo()}
    )
    with recording_dropped() as dropped:
        before, after = drop_blurry(rows[:2], rows[2:], load)
    assert (times(before), times(after)) == ([2000], [5000])
    assert dropped == {"faceBlurry": {1000}}


def test_sharp_hand_over_a_blurry_face_does_not_hide_the_blur():
    """초점이 손에 가고 얼굴이 흐린 사진은 가린 칸을 빼고 재야 흐린 사진으로 잡힌다.

    가린 칸을 빼지 않으면 또렷한 손 무늬가 선명도를 끌어올려 흐린 사진을 놓친다.
    """
    hand = hand_over(13, half=150)
    focused_on_hand = textured_photo(8)
    focused_on_hand[hand] = textured_photo()[hand]
    rows, load = photos_by_time(
        {1000: focused_on_hand, 2000: textured_photo(), 5000: textured_photo()}
    )

    def finds_the_hand(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
        return hand if row.timestamp_ms == 1000 else np.zeros(photo.shape[:2], dtype=bool)

    assert times(drop_blurry(rows[:2], rows[2:], load)[0]) == [1000, 2000]
    assert times(drop_blurry(rows[:2], rows[2:], load, finds_the_hand)[0]) == [2000]


def test_photo_with_its_whole_face_hidden_is_kept_without_judging():
    """얼굴이 모두 가려 볼 칸이 없으면 흐린지 알 수 없어 그대로 둔다.

    가린 칸은 지도 만들기(rows_to_known_map)가 따로 뺀다.
    """
    rows, load = photos_by_time(
        {1000: textured_photo(8), 2000: textured_photo(), 5000: textured_photo()}
    )

    def hides_first(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
        return np.full(photo.shape[:2], row.timestamp_ms == 1000)

    before, _ = drop_blurry(rows[:2], rows[2:], load, hides_first)
    assert times(before) == [1000, 2000]


def test_blur_is_measured_on_maps_the_photo_bundle_already_made():
    """사진 꾸러미로 넘기면 흐림을 잴 때 편 지도를 지도 만들기에서 다시 쓴다.

    그래서 사진마다 한 번만 읽는다. 서비스가 흐림을 재는 데 시간을 거의 더 쓰지 않는 까닭이다.
    """
    rows, load_photo = photos_by_time({1000: textured_photo(), 5000: textured_photo()})
    load, reads = counted(load_photo)
    photos = RememberedPhotos(load, keep=64)

    before, after = drop_blurry(rows[:1], rows[1:], photos)
    rows_to_known_map(before + after, photos)

    assert reads == [1000, 5000]


def test_photo_bundle_measures_each_photo_sharpness_once(monkeypatch):
    """좌우 짝 부위와 지표 도구는 같은 사진 묶음을 여러 번 넘기므로 선명도는 사진마다 한 번만 잰다.

    지도는 keep장만 기억해 keep=1이면 잊히지만, 선명도는 값 하나라 계속 기억해야 한다.
    기억한 값은 꾸러미 없이 잰 값과 같아야 빼는 사진도 같다.
    """
    rows, load_photo = photos_by_time(
        {1000: textured_photo(8), 2000: textured_photo(), 5000: textured_photo()}
    )
    plain = [area_preparation.face_sharpness(row, load_photo) for row in rows]
    measured = []
    measure = area_preparation.sharpness_on_maps
    monkeypatch.setattr(
        area_preparation,
        "sharpness_on_maps",
        lambda face_map, covered: measured.append(1) or measure(face_map, covered),
    )
    photos = RememberedPhotos(load_photo, keep=1)

    drop_blurry(rows[:2], rows[2:], photos)
    before, after = drop_blurry(rows[:2], rows[2:], photos)

    assert len(measured) == len(rows)
    assert [photos.sharpness(row, None) for row in rows] == plain
    assert (times(before), times(after)) == ([2000], [5000])


STEP_START_MS, STEP_END_MS = 10_000, 20_000
PART_FINDERS = {
    "lip": lambda result, load: lip_area.find_lip_area(result, STEP_START_MS, STEP_END_MS, load),
    "blush": lambda result, load: blush_area.find_blush_area(
        result, STEP_START_MS, STEP_END_MS, load, "leftCheek"
    ),
    "brow": lambda result, load: brow_area.find_brow_area(
        result, STEP_START_MS, STEP_END_MS, load, "leftBrow"
    ),
    "eyeshadow": lambda result, load: eyeshadow_area.find_eyeshadow_area(
        result, STEP_START_MS, STEP_END_MS, load, "leftEye"
    ),
    "eyeliner": lambda result, load: eyeliner_area.find_eyeliner_area(
        result, STEP_START_MS, STEP_END_MS, load, "leftEye"
    ),
}


@pytest.mark.parametrize("part", PART_FINDERS)
def test_every_part_leaves_out_a_blurry_photo(part):
    """부위 함수마다 흐린 사진 빼기(drop_blurry)를 부르는지 본다.

    흐림 빼기 자체는 위 시험들이 보지만, 한 부위 함수에서 부르는 줄이 지워지면 그 부위만 조용히
    흐린 사진을 다시 쓴다. 직후 창에 흐린 사진을 하나 섞어, 빠진 사진 기록에 흐림으로 남는지 본다.
    """
    sharp, blurry = textured_photo(), textured_photo(8)
    photos = {
        STEP_START_MS - 500: sharp,
        STEP_END_MS + 300: blurry,
        STEP_END_MS + 500: sharp,
        STEP_END_MS + 700: sharp,
    }
    rows = [with_eyes(make_row(time), 0.35) for time in photos]
    result = LandmarksResult(video_id="test_01", frames=rows)
    with recording_dropped() as dropped:
        PART_FINDERS[part](result, lambda row: photos[row.timestamp_ms])
    assert dropped.get("faceBlurry") == {STEP_END_MS + 300}


def test_photos_left_out_after_the_check_are_recorded_with_their_reasons():
    """판정은 통과했는데 부위 분석에서 빠진 사진을 이유별 사진 번호로 한 번씩 모은다."""
    rows = [
        make_row(1000, {"leftCheek": 1}),
        with_eyes(make_row(2000), 0.1),
        with_eyes(make_row(3000), 0.35),
    ]
    result = LandmarksResult(video_id="test_01", frames=rows)
    with recording_dropped() as dropped:
        usable_rows(result, 0, 4000, ["leftCheek"])
        usable_rows(result, 0, 4000, ["leftCheek"])
        usable_rows(result, 1500, 4000, ["leftEye"])
        match_sizes([sized(5000, 400), sized(6000, 400), sized(7000, 300)], [sized(8000, 300)])
    assert dropped == {
        "regionOutside": {1000},
        "eyesClosed": {2000},
        "faceSizeUnmatched": {5000, 6000},
    }


def test_photo_hiding_most_of_the_zone_is_recorded():
    rows, load_photo = photos_with_hands({1000: hand_over(13, half=200), 2000: None})
    row, col = cell(13)
    zone = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    zone[row - 20 : row + 20, col - 20 : col + 20] = True
    with recording_dropped() as dropped:
        rows_to_known_map(rows, load_photo, finds_hand_color, zone)
    assert dropped == {"heavilyOccluded": {1000}}


def test_nothing_is_recorded_outside_recording():
    rows = [make_row(1000, {"leftCheek": 1})]
    result = LandmarksResult(video_id="test_01", frames=rows)
    usable_rows(result, 0, 4000, ["leftCheek"])
    with recording_dropped() as dropped:
        pass
    assert dropped == {}


def test_range_is_mostly_unknown_past_half():
    cells = np.zeros((10, 4), dtype=bool)
    cells[:, :2] = True
    six, four = np.zeros_like(cells), np.zeros_like(cells)
    six[:6] = True
    four[:4] = True

    assert mostly_unknown(cells, six)
    assert not mostly_unknown(cells, four)
    assert not mostly_unknown(cells, None)


def test_rgb_to_lab_from_the_table_equals_the_direct_calculation():
    """0~255 정수 표는 미리 계산한 감마 표에서 꺼내는데, 직접 계산한 값과 한 자리도 다르지 않다."""
    rgb = np.random.default_rng(0).integers(0, 256, (64, 64, 3), dtype=np.uint8)

    from_table = area_preparation.rgb_to_lab(rgb)
    direct = area_preparation.rgb_to_lab(rgb.astype(np.float64))

    assert np.array_equal(from_table, direct)
    assert np.allclose(
        area_preparation.rgb_to_lab(np.array([[255, 255, 255]])), [[100, 0, 0]], atol=1e-3
    )
