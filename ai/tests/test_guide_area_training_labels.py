import importlib
from pathlib import Path

import numpy as np

from app.schemas.landmarks import Face, Point, Pose
from app.tasks.area.common.face_map import MAP_SIZE, face_cells, flatten, mesh_uv
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts.eyeliner_area import eyeliner_range
from app.tasks.area.parts.eyeshadow_area import eyeshadow_range
from tools.guide_area_training import labels, paint, plan

SIZE = 8


def cells(*points: tuple[int, int]) -> np.ndarray:
    out = np.zeros((SIZE, SIZE), dtype=bool)
    for row, col in points:
        out[row, col] = True
    return out


def step(step_id: str, makeup: str, start: float, end: float) -> dict:
    return {"stepId": step_id, "makeup": makeup, "startSeconds": start, "endSeconds": end}


def map_face(scale: float = 1.0) -> Face:
    """얼굴 점이 얼굴 지도 자리 그대로(scale배) 놓인 얼굴. 사진 크기는 MAP_SIZE × scale이다."""
    uv = mesh_uv() / MAP_SIZE
    points = [Point(x=float(x), y=float(y), z=0.0) for x, y in uv]
    points += [points[0]] * (478 - len(points))
    return Face(landmarks=points, iod=0.2, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0))


def test_label_map_writes_class_numbers_and_ignores_unsure_and_outside_face_cells():
    face = np.ones((SIZE, SIZE), dtype=bool)
    face[0, :] = False

    label = labels.label_map(
        {"lip": cells((2, 2), (2, 3)), "blush": cells((4, 4))}, cells((2, 3), (5, 5)), face
    )

    assert label[2, 2] == labels.CLASS_IDS["lip"]
    assert label[4, 4] == labels.CLASS_IDS["blush"]
    assert label[2, 3] == labels.IGNORE
    assert label[5, 5] == labels.IGNORE
    assert (label[0] == labels.IGNORE).all()
    assert label[6, 6] == 0


def test_strength_cells_split_strong_cells_faint_edge_and_untouched_cells():
    strength = np.zeros((SIZE, SIZE), dtype=np.float32)
    strength[1, 1], strength[1, 2], strength[1, 3], strength[1, 4] = 0.8, 0.4, 0.2, 0.05

    on, edge = labels.strength_cells(strength)

    assert on[1, 1] and on[1, 2]
    assert edge[1, 3] and not on[1, 3]
    assert not on[1, 4] and not edge[1, 4]


def test_strength_cells_are_empty_when_nothing_was_painted():
    on, edge = labels.strength_cells(np.zeros((SIZE, SIZE), dtype=np.float32))

    assert not on.any() and not edge.any()


def test_agreed_cells_keep_cells_every_window_found_and_mark_the_rest_unsure():
    agreed = labels.agreed_cells([cells((1, 1), (1, 2)), cells((1, 1)), cells((1, 1), (3, 3))])

    assert agreed is not None
    every, partly = agreed
    assert every[1, 1] and every.sum() == 1
    assert partly[1, 2] and partly[3, 3] and not partly[1, 1]


def test_agreed_cells_reject_the_area_when_one_window_found_nothing():
    assert labels.agreed_cells([cells((1, 1)), None, cells((1, 1))]) is None


def test_looked_classes_follow_the_step_zones_and_skip_the_waterline():
    assert labels.looked_classes("lip", None) == ["lip"]
    assert labels.looked_classes("eyeshadow", None) == ["eyeshadowUpper", "eyeshadowUnder"]
    assert labels.looked_classes("eyeshadow", ("under",)) == ["eyeshadowUnder"]
    assert labels.looked_classes("eyeliner", ("upper", "waterline")) == ["eyelinerUpper"]


def test_step_label_ignores_the_whole_range_of_a_zone_found_only_in_some_windows():
    face = np.ones((SIZE, SIZE), dtype=bool)
    upper = cells((1, 1), (1, 2))
    combos = [
        {"eyeshadowUpper": upper, "eyeshadowUnder": cells((5, 5))},
        {"eyeshadowUpper": cells((1, 1)), "eyeshadowUnder": None},
    ]
    ranges = {
        "eyeshadowUpper": cells((1, 1), (1, 2), (1, 3)),
        "eyeshadowUnder": cells((5, 5), (5, 6)),
    }

    made = labels.step_label(combos, cells((7, 7)), face, ranges)

    assert made is not None
    label, stable, unstable = made
    assert (stable, unstable) == (["eyeshadowUpper"], ["eyeshadowUnder"])
    assert label[1, 1] == labels.CLASS_IDS["eyeshadowUpper"]
    assert label[1, 2] == labels.IGNORE
    assert label[1, 3] == 0
    assert label[5, 5] == labels.IGNORE and label[5, 6] == labels.IGNORE
    assert label[7, 7] == labels.IGNORE


def test_step_label_is_none_when_no_zone_was_found_in_every_window():
    face = np.ones((SIZE, SIZE), dtype=bool)
    combos = [{"lip": cells((1, 1))}, {"lip": None}]

    assert labels.step_label(combos, cells(), face, {"lip": cells((1, 1))}) is None


def test_saved_sample_reads_back_the_same_maps_label_and_strength(tmp_path):
    rng = np.random.default_rng(0)
    before = rng.integers(0, 256, (SIZE, SIZE, 3), dtype=np.uint8)
    after = rng.integers(0, 256, (SIZE, SIZE, 3), dtype=np.uint8)
    label = np.array(rng.integers(0, 8, (SIZE, SIZE)), dtype=np.uint8)
    label[0, 0] = labels.IGNORE
    strength = np.linspace(0, 1, SIZE * SIZE, dtype=np.float32).reshape(SIZE, SIZE)

    labels.save_sample(tmp_path / "가나", before, after, label, strength)

    assert (labels.read_png(tmp_path / "가나" / "before.png", color=True) == before).all()
    assert (labels.read_png(tmp_path / "가나" / "after.png", color=True) == after).all()
    assert (labels.read_png(tmp_path / "가나" / "label.png") == label).all()
    assert (labels.read_png(tmp_path / "가나" / "strength.png") == np.round(strength * 255)).all()


def test_list_is_written_in_name_order_and_missing_list_reads_empty(tmp_path):
    labels.write_list(tmp_path / "a", [{"name": "b"}, {"name": "a"}])

    assert [row["name"] for row in labels.read_list(tmp_path / "a")] == ["a", "b"]
    assert labels.read_list(tmp_path / "none") == []


def test_class_cells_count_each_class_and_ignored_cells():
    label = np.zeros((SIZE, SIZE), dtype=np.uint8)
    label[0, :3] = labels.CLASS_IDS["brow"]
    label[1, :2] = labels.IGNORE

    counts = labels.class_cells(label)

    assert (counts["brow"], counts["ignore"], counts["lip"]) == (3, 2, 0)
    assert counts["none"] == SIZE * SIZE - 5


def test_overlay_draws_the_outline_in_the_class_color_and_keeps_the_inside():
    image = np.full((40, 40, 3), 100, dtype=np.uint8)
    label = np.zeros((40, 40), dtype=np.uint8)
    label[10:30, 10:30] = labels.CLASS_IDS["lip"]

    out = labels.overlay(image, label)

    assert tuple(out[10, 20]) == labels.COLORS["lip"]
    assert tuple(out[20, 20]) == (100, 100, 100)
    assert tuple(out[2, 2]) == (100, 100, 100)


def test_bare_ranges_keep_groups_that_end_by_the_start_of_the_first_step_of_that_makeup():
    steps = [step("s1", "brow", 20, 30), step("s2", "lip", 50, 60), step("s3", "brow", 80, 90)]

    lip = plan.bare_ranges(steps, "lip")
    brow = plan.bare_ranges(steps, "brow")

    assert [(item["stepId"], item["group"]) for item in lip] == [
        ("s1", "before"),
        ("s1", "after"),
        ("s2", "before"),
    ]
    assert [(item["stepId"], item["group"]) for item in brow] == [("s1", "before")]


def test_bare_ranges_use_every_group_when_the_video_has_no_step_of_that_makeup():
    steps = [step("s1", "brow", 20, 30), step("s2", "lip", 50, 60)]

    assert len(plan.bare_ranges(steps, "blush")) == 4


def test_bare_ranges_drop_groups_that_overlap_another_analyzed_makeup_step():
    steps = [
        step("s1", "eyeshadow", 20, 30),
        step("s2", "eyeliner", 30, 40),
        step("s3", "foundation", 62, 66),
        step("s4", "lip", 70, 80),
    ]

    lip = plan.bare_ranges(steps, "lip")

    assert [(item["stepId"], item["group"]) for item in lip] == [
        ("s1", "before"),
        ("s2", "after"),
        ("s4", "before"),
    ]


SYNTH_DIR = Path(__file__).resolve().parents[1] / "tools" / "guide_area_training"


def test_job_seed_differs_by_split_and_keeps_the_train_seed(monkeypatch):
    monkeypatch.syspath_prepend(str(SYNTH_DIR))
    make_synth = importlib.import_module("make_synth")

    seeds = {split: make_synth.job_seed(split, 2, 5) for split in ("train", "validation", "test")}
    colors = {
        split: paint.make(
            np.random.default_rng(make_synth.job_seed(split, 0, 0)), "lip", "red"
        ).color
        for split in seeds
    }

    assert seeds["train"] == [make_synth.SEED, 0, 2, 5]
    assert len({tuple(seed) for seed in seeds.values()}) == 3
    assert len(set(colors.values())) == 3
    assert make_synth.job_seed("test", 2) == [make_synth.SEED, 2, 2]


def test_halves_split_times_in_order_and_put_the_middle_one_in_the_second_half():
    assert plan.halves([50, 10, 40, 20, 30]) == ([10, 20], [30, 40, 50])
    assert plan.halves([7]) == ([], [7])


def test_spread_picks_evenly_from_first_to_last_and_keeps_short_lists():
    assert plan.spread(list(range(10)), 4) == [0, 3, 6, 9]
    assert plan.spread([1, 2, 3], 8) == [1, 2, 3]


def test_fill_counts_give_more_synthetic_labels_to_parts_with_fewer_real_labels():
    counts = plan.fill_counts({"lip": 12, "brow": 4}, ["lip", "brow", "blush"], base=100)

    assert counts == {"lip": 100, "brow": 108, "blush": 112}


def test_every_style_paints_inside_the_range_the_service_looks_at_for_that_part():
    rng = np.random.default_rng(3)
    lips = polygon_mask(
        [(x, y) for x, y in map(tuple, mesh_uv()[list(REGION_POINTS["lipsOuter"])])],
        MAP_SIZE,
        MAP_SIZE,
        band=12,
    )
    ranges = {
        "lip": lips,
        "eyeshadowUpper": np.any([eyeshadow_range(e, "upper") for e in paint.EYES], axis=0),
        "eyeshadowUnder": np.any([eyeshadow_range(e, "under") for e in paint.EYES], axis=0),
        "eyelinerUpper": np.any([eyeliner_range(e, "upper") for e in paint.EYES], axis=0),
        "eyelinerUnder": np.any([eyeliner_range(e, "under") for e in paint.EYES], axis=0),
    }
    for part, styles in paint.STYLES.items():
        for style in styles:
            makeup = paint.make(rng, part, style)
            low, high = paint.STRENGTH_RANGES[part]
            assert low <= makeup.strength <= high
            for name, alpha in makeup.zones.items():
                assert name in labels.PART_CLASSES[part]
                assert alpha.shape == (MAP_SIZE, MAP_SIZE)
                assert 0.99 <= alpha.max() <= 1.0 and alpha.min() >= 0
                strong = alpha >= labels.ON_SHARE
                assert strong.any()
                if name in ranges:
                    assert (strong & ranges[name]).sum() >= 0.8 * strong.sum(), (part, style)


def test_blush_is_painted_on_both_cheeks_mirrored_and_high_sits_above_low():
    rng = np.random.default_rng(5)
    high = paint.make(rng, "blush", "high").zones["blush"]
    low = paint.make(rng, "blush", "low").zones["blush"]

    assert np.allclose(high[:, 1:], high[:, :0:-1], atol=1e-4)
    assert np.argmax(high.max(axis=1)) < np.argmax(low.max(axis=1))


def test_wing_only_eyeliner_stays_outside_the_eye_corners():
    rng = np.random.default_rng(7)
    alpha = paint.make(rng, "eyeliner", "wing").zones["eyelinerUpper"]
    eye = np.array(mesh_uv()[list(REGION_POINTS["leftEye"])])
    cols = np.nonzero((alpha[:, MAP_SIZE // 2 :] >= labels.ON_SHARE).any(axis=0))[0] + MAP_SIZE // 2

    assert cols.min() >= eye[:, 0].max() - 8


def test_to_photo_puts_the_map_alpha_back_where_flatten_reads_it():
    rng = np.random.default_rng(11)
    alpha = paint.make(rng, "lip", "red").alpha()
    face = map_face()

    moved = paint.to_photo(alpha, face, MAP_SIZE, MAP_SIZE)
    layer = np.round(moved * 255).astype(np.uint8)
    back = flatten(np.dstack([layer] * 3), face)[..., 0] / 255

    inside = face_cells()
    assert np.abs(back - alpha)[inside].max() < 0.2
    assert np.abs(back - alpha)[inside].mean() < 0.002


def test_to_photo_follows_the_face_when_the_photo_is_half_the_map_size():
    rng = np.random.default_rng(13)
    alpha = paint.make(rng, "blush", "high").alpha()

    moved = paint.to_photo(alpha, map_face(), MAP_SIZE // 2, MAP_SIZE // 2)

    rows, cols = np.unravel_index(np.argmax(alpha), alpha.shape)
    peak_rows, peak_cols = np.unravel_index(np.argmax(moved), moved.shape)
    assert abs(peak_rows - rows / 2) <= 3 and abs(peak_cols - cols / 2) <= 3


def test_tint_moves_painted_pixels_toward_the_color_and_leaves_the_rest():
    photo = np.full((6, 6, 3), 200, dtype=np.uint8)
    alpha = np.zeros((6, 6), dtype=np.float32)
    alpha[2, 2], alpha[3, 3] = 1.0, 0.5

    out = paint.tint(photo, alpha, (100, 20, 40))

    assert tuple(out[2, 2]) == (100, 20, 40)
    assert tuple(out[3, 3]) == (150, 110, 120)
    assert tuple(out[0, 0]) == (200, 200, 200)
    assert (photo == 200).all()


def test_tint_keeps_darker_skin_darker_under_the_makeup():
    photo = np.full((4, 4, 3), 200, dtype=np.uint8)
    photo[0, 0] = 150
    alpha = np.ones((4, 4), dtype=np.float32)

    out = paint.tint(photo, alpha, (100, 100, 100))

    assert out[0, 0, 0] < out[1, 1, 0]


def test_relight_scales_brightness_and_color_cast_and_clips():
    photo = np.full((2, 2, 3), 100, dtype=np.uint8)
    photo[0, 0] = 250

    out = paint.relight(photo, 1.1, (1.0, 0.9, 1.0))

    assert tuple(out[1, 1]) == (110, 99, 110)
    assert tuple(out[0, 0]) == (255, 248, 255)
