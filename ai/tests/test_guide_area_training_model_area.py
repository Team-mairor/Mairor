import numpy as np
import onnxruntime
import pytest

from app.tasks.area.common.face_map import MAP_SIZE, face_cells
from app.tasks.area.parts import (
    blush_area,
    brow_area,
    eyeliner_area,
    eyeshadow_area,
    lip_area,
)
from tools.guide_area_training import labels, model_area

PATCHED = {
    lip_area: ("lip_area_on_maps", "check_lip_area"),
    blush_area: ("blush_reddening", "check_blush_area"),
    brow_area: ("brow_darkening", "check_brow_area"),
    eyeshadow_area: ("eyeshadow_reddening", "check_eyeshadow_area"),
    eyeliner_area: ("zone_change", "check_eyeliner_area"),
}


def square(top: int, left: int, size: int) -> np.ndarray:
    mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    mask[top : top + size, left : left + size] = True
    return mask


def lip_square() -> np.ndarray:
    row, col = np.argwhere(lip_area.lip_range()).mean(axis=0).astype(int)
    return square(row - 10, col - 10, 20)


class FakeSession:
    def __init__(self, class_id: int) -> None:
        self.class_id = class_id
        self.calls = 0

    def run(self, outputs, feeds):
        self.calls += 1
        scores = np.zeros((1, 8, MAP_SIZE, MAP_SIZE), dtype=np.float32)
        scores[0, self.class_id] = 1.0
        return [scores]


class FakeModel:
    def __init__(self, classes: np.ndarray) -> None:
        self.classes = classes

    def predict(self, before: np.ndarray, after: np.ndarray) -> np.ndarray:
        return self.classes


@pytest.fixture
def restore_parts(monkeypatch):
    """install은 부위 모듈 함수를 바꾸므로, 테스트가 끝나면 원래 함수로 되돌린다."""
    for module, names in PATCHED.items():
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name))
    return monkeypatch


@pytest.mark.parametrize(
    ("method", "rule", "model", "expected"),
    [
        ("model", "a", "b", "b"),
        ("model", "a", None, None),
        ("and", "a", "b", "a&b"),
        ("and", None, "b", None),
        ("or", "a", "b", "a|b"),
        ("or", None, "b", "b"),
        ("rule_gate", "a", "b", "b"),
        ("rule_gate", None, "b", None),
        ("model_gate", "a", "b", "a"),
        ("model_gate", None, "b", "b"),
        ("model_gate", "a", None, None),
    ],
)
def test_combine_joins_rule_and_model_cells_by_method(method, rule, model, expected):
    a, b = square(0, 0, 4), square(2, 2, 4)
    masks = {"a": a, "b": b, "a&b": a & b, "a|b": a | b, None: None}

    out = model_area.combine(method, masks[rule], masks[model])

    if expected is None:
        assert out is None
    else:
        assert np.array_equal(out, masks[expected])


def test_combine_treats_an_empty_overlap_as_not_found():
    out = model_area.combine("and", square(0, 0, 4), square(10, 10, 4))

    assert out is None


def test_drop_small_uses_the_part_min_piece_like_the_service():
    """립은 MIN_PIECE_CELLS(300)보다 작은 조각을 버리고, 기준이 없는 눈썹은 그대로 둔다."""
    mask = square(0, 0, 17) | square(100, 100, 18)

    lip = model_area.drop_small(mask, "lip")
    brow = model_area.drop_small(mask, "brow")

    assert not lip[0:17, 0:17].any()
    assert lip[100:118, 100:118].all()
    assert np.array_equal(brow, mask)


def test_class_mask_removes_unknown_cells_and_returns_none_when_nothing_is_left():
    classes = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    classes[square(200, 200, 20)] = labels.CLASS_IDS["lip"]
    unknown = square(200, 200, 20)

    assert model_area.class_mask(classes, "lip", "lip", None, None).sum() == 400
    assert model_area.class_mask(classes, "lip", "lip", None, unknown) is None


def test_predict_keeps_the_result_in_the_store_so_another_process_skips_the_model(
    tmp_path, monkeypatch
):
    """같은 모델로 도는 다른 방식(and·or 등)은 저장된 결과를 읽어 모델을 다시 돌리지 않는다."""
    first, second = FakeSession(3), FakeSession(5)
    sessions = iter([first, second])
    monkeypatch.setattr(onnxruntime, "InferenceSession", lambda *args, **kwargs: next(sessions))
    before = np.zeros((MAP_SIZE, MAP_SIZE, 3), dtype=np.uint8)
    after = np.full((MAP_SIZE, MAP_SIZE, 3), 9, dtype=np.uint8)

    made = model_area.OnnxModel(tmp_path / "final.onnx", 1, tmp_path).predict(before, after)
    again = model_area.OnnxModel(tmp_path / "final.onnx", 1, tmp_path).predict(before, after)

    assert (first.calls, second.calls) == (1, 0)
    assert np.array_equal(made, again)
    assert (made[face_cells()] == 3).all()
    assert (made[~face_cells()] == 0).all()
    assert len(list((tmp_path / "final").glob("*.npz"))) == 1


def test_install_model_finds_the_lip_the_model_painted_when_the_rule_finds_nothing(
    restore_parts,
):
    """사진 고르기·지도 만들기는 서비스 그대로 두고, 칸 찾기만 모델 결과로 바뀐다."""
    blob = lip_square()
    classes = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    classes[blob] = labels.CLASS_IDS["lip"]
    restore_parts.setattr(model_area, "OnnxModel", lambda *args: FakeModel(classes))
    maps = np.zeros((MAP_SIZE, MAP_SIZE, 3), dtype=np.uint8)

    model_area.install("model", "unused.onnx")
    found = lip_area.check_lip_area(lip_area.lip_area_on_maps(maps, maps))

    assert found.reason is None
    assert np.array_equal(found.mask, blob)


def test_install_and_keeps_the_rule_reason_when_the_rule_finds_nothing(restore_parts):
    classes = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    classes[lip_square()] = labels.CLASS_IDS["lip"]
    restore_parts.setattr(model_area, "OnnxModel", lambda *args: FakeModel(classes))
    maps = np.zeros((MAP_SIZE, MAP_SIZE, 3), dtype=np.uint8)

    model_area.install("and", "unused.onnx")
    found = lip_area.check_lip_area(lip_area.lip_area_on_maps(maps, maps))

    assert found.mask is None
    assert found.reason == "lipColorNotFound"


def test_install_keeps_map_functions_returning_rule_values_for_the_metric_tools(restore_parts):
    """잡음 도구는 지도 함수 값을 숫자 표로 바로 쓰므로, 모델을 끼워도 그대로 돌아야 한다."""
    from tools import noise_metric

    classes = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    classes[lip_square()] = labels.CLASS_IDS["lip"]
    restore_parts.setattr(model_area, "OnnxModel", lambda *args: FakeModel(classes))
    maps = np.zeros((MAP_SIZE, MAP_SIZE, 3), dtype=np.uint8)
    afters = {ms: [(maps, None)] for ms in set(eyeliner_area.AFTER_SLICE_MS.values())}

    model_area.install("model", "unused.onnx")
    measures = [
        noise_metric.measure_lip(maps, maps, "lipsOuter"),
        noise_metric.measure_blush(maps, maps, blush_area.CHEEKS[0]),
        noise_metric.measure_brow(maps, maps, brow_area.BROWS[0]),
        noise_metric.measure_eyeshadow(maps, maps, eyeshadow_area.EYES[0]),
        noise_metric.measure_eyeliner(maps, afters, eyeliner_area.EYES[0]),
    ]

    assert isinstance(brow_area.brow_darkening(maps, maps), np.ndarray)
    assert [m is not None for m in measures] == [True] * 5
    assert measures[0].found is True
    assert [m.found for m in measures[1:]] == [False] * 4


def test_check_rejects_values_not_made_by_the_map_functions(restore_parts):
    restore_parts.setattr(model_area, "OnnxModel", lambda *args: FakeModel(np.zeros(1)))

    model_area.install("model", "unused.onnx")

    with pytest.raises(LookupError):
        lip_area.check_lip_area(lip_square())


@pytest.fixture
def restore_pairing(monkeypatch):
    """install_each_side는 짝 맞추기·하위 단계 함수를 바꾸므로, 끝나면 되돌린다."""
    from app.tasks.area import guide_area_builder
    from tools import output_area

    names = {
        brow_area: ("symmetric_brows",),
        blush_area: ("paired_blush",),
        eyeshadow_area: ("paired_eyeshadow",),
        eyeliner_area: ("paired_eyeliner",),
        guide_area_builder: (
            "symmetric_brows",
            "paired_blush",
            "paired_eyeshadow",
            "paired_eyeliner",
            "pair_sub_step",
            "eyeliner_sub_step",
        ),
        output_area: (
            "symmetric_brows",
            "paired_blush",
            "paired_eyeshadow",
            "paired_eyeliner",
            "pair_sub_step",
        ),
    }
    for module, attrs in names.items():
        for attr in attrs:
            monkeypatch.setattr(module, attr, getattr(module, attr))
    monkeypatch.setitem(output_area.PAIR_RULES, "blush", output_area.PAIR_RULES["blush"])
    return guide_area_builder


def test_each_side_writes_only_the_cheek_that_was_found(restore_pairing):
    """서비스는 한 볼만 찾으면 기본 가이드지만, 좌우 따로는 찾은 볼만 영역을 적는다."""
    builder = restore_pairing
    left, right = blush_area.CHEEKS
    areas = {
        left: blush_area.BlushArea(mask=blush_area.cheek_range(left), peak=5.0),
        right: blush_area.BlushArea(mask=None, reason="blushColorNotFound"),
    }
    service = builder.pair_sub_step(
        "s1-1", "blush", areas, builder.paired_blush(areas), "blushColorNotFound", False, 2.0
    )

    model_area.install_each_side()
    each = builder.pair_sub_step(
        "s1-1", "blush", areas, builder.paired_blush(areas), "blushColorNotFound", False, 2.0
    )

    assert service.status == "template"
    assert each.status == "extracted"
    assert [guide_set.region for guide_set in each.guide_sets] == [left]


def test_each_side_writes_only_the_eye_whose_line_was_found(restore_pairing):
    builder = restore_pairing
    left, right = eyeliner_area.EYES
    line = eyeliner_area.eyeliner_range(left, "upper")
    masks = {left: line, right: np.zeros_like(line)}

    model_area.install_each_side()
    sub_step = builder.eyeliner_sub_step("s1-1", masks)

    assert sub_step.status == "extracted"
    assert [guide_set.region for guide_set in sub_step.guide_sets] == [left]


def test_each_side_line_sub_step_accepts_masks_of_one_eye(restore_pairing):
    """잡음 도구는 아이라인을 눈 하나씩 재서 짝 결과에 그 눈만 들어 있다."""
    builder = restore_pairing
    left = eyeliner_area.EYES[0]

    model_area.install_each_side()
    line = eyeliner_area.eyeliner_range(left, "upper")
    sub_step = builder.eyeliner_sub_step("s1-1", {left: line})

    assert [guide_set.region for guide_set in sub_step.guide_sets] == [left]


def test_install_rejects_an_unknown_method():
    with pytest.raises(ValueError):
        model_area.install("vote", "unused.onnx")


def test_unknown_union_joins_per_zone_unknown_cells():
    upper, under = square(0, 0, 4), square(10, 10, 4)

    out = model_area.unknown_union({"upper": upper, "under": under, "inner": None})

    assert np.array_equal(out, upper | under)
    assert model_area.unknown_union(None) is None
    assert model_area.unknown_union({"upper": None}) is None
