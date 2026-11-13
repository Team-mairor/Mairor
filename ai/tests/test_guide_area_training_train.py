import numpy as np
import pytest

torch = pytest.importorskip("torch")

from tools.guide_area_training import labels, train  # noqa: E402

SIZE = 64


def write_sample(folder, before, after, label):
    labels.save_sample(folder, before, after, label)
    return folder


def flat(value):
    return np.full((SIZE, SIZE, 3), value, dtype=np.uint8)


def test_stack_maps_puts_before_in_first_three_layers_and_after_in_last_three():
    stacked = train.stack_maps(flat(0), flat(255))

    assert stacked.shape == (6, SIZE, SIZE)
    assert stacked.dtype == np.uint8
    assert (stacked[:3] == 0).all()
    assert (stacked[3:] == 255).all()


def test_to_input_scales_brightness_per_sample_clips_and_normalizes():
    maps = torch.from_numpy(np.stack([train.stack_maps(flat(100), flat(200))] * 2))

    x = train.to_input(maps, torch.tensor([1.0, 1.5]), "cpu")

    assert x.shape == (2, 6, SIZE, SIZE)
    assert np.allclose(x[0, :3, 0, 0], (100 / 255 - train.MEAN) / train.STD, atol=1e-6)
    assert np.allclose(x[1, :3, 0, 0], (150 / 255 - train.MEAN) / train.STD, atol=1e-6)
    assert np.allclose(x[1, 3:, 0, 0], (1 - train.MEAN) / train.STD, atol=1e-6)


def test_to_input_matches_the_old_cpu_calculation():
    before = np.random.default_rng(0).integers(0, 256, (SIZE, SIZE, 3), dtype=np.uint8)
    after = np.random.default_rng(1).integers(0, 256, (SIZE, SIZE, 3), dtype=np.uint8)
    gain = 1.12
    old = [
        (np.clip(image.astype(np.float32) * gain, 0, 255) / 255 - train.MEAN) / train.STD
        for image in (before, after)
    ]
    old = np.concatenate(old, axis=2).transpose(2, 0, 1)

    new = train.to_input(
        torch.from_numpy(train.stack_maps(before, after))[None], torch.tensor([gain]), "cpu"
    )

    assert np.allclose(new[0].numpy(), old, atol=1e-5)


def test_shrink_keeps_class_numbers_and_ignore_when_label_is_made_smaller():
    label = np.zeros((SIZE, SIZE), dtype=np.uint8)
    label[:, : SIZE // 2] = labels.CLASS_IDS["eyelinerUnder"]
    label[: SIZE // 2, SIZE // 2 :] = labels.IGNORE

    small = train.shrink(label, SIZE // 2, label=True)

    assert set(np.unique(small)) == {0, labels.CLASS_IDS["eyelinerUnder"], labels.IGNORE}


def test_pairs_reads_one_sample_as_six_layers_with_label_numbers_unchanged(tmp_path):
    label = np.zeros((SIZE, SIZE), dtype=np.uint8)
    label[10:20, 10:20] = labels.CLASS_IDS["lip"]
    label[0, :] = labels.IGNORE
    folder = write_sample(tmp_path / "one", flat(100), flat(140), label)

    maps, target, gain, source = train.Pairs([(folder, 1)], SIZE, augment=False)[0]

    assert maps.shape == (6, SIZE, SIZE)
    assert maps.dtype == torch.uint8
    assert np.array_equal(target.numpy(), label)
    assert gain == 1.0
    assert source == 1


def test_pairs_flip_moves_label_together_with_both_maps(tmp_path, monkeypatch):
    before, after = flat(100), flat(100)
    after[:, :8] = 200
    label = np.zeros((SIZE, SIZE), dtype=np.uint8)
    label[:, :8] = labels.CLASS_IDS["blush"]
    folder = write_sample(tmp_path / "one", before, after, label)
    monkeypatch.setattr(train.random, "random", lambda: 0.0)
    monkeypatch.setattr(train.random, "uniform", lambda low, high: 0.0)

    maps, target, gain, _ = train.Pairs([(folder, 0)], SIZE, augment=True)[0]

    assert (target[:, -8:] == labels.CLASS_IDS["blush"]).all()
    assert (target[:, :8] == 0).all()
    assert maps[3, 0, -1] > maps[3, 0, 0]
    assert maps[0, 0, -1] == maps[0, 0, 0]
    assert gain == 1.0


def test_loss_ignores_unknown_cells():
    label = torch.zeros((1, 4, 4), dtype=torch.int64)
    label[0, 0, 0] = labels.IGNORE
    right = torch.zeros((1, train.NUM_CLASSES, 4, 4))
    right[:, 0] = 20.0
    wrong_only_in_unknown = right.clone()
    wrong_only_in_unknown[0, :, 0, 0] = 0.0
    wrong_only_in_unknown[0, 3, 0, 0] = 20.0
    weights = train.class_weights(3.0, "cpu")

    assert train.loss_fn((wrong_only_in_unknown,), label, weights) == train.loss_fn(
        (right,), label, weights
    )


def test_loss_counts_a_missed_painted_cell_more_than_a_falsely_painted_cell():
    weights = train.class_weights(3.0, "cpu")
    says_none = torch.zeros((1, train.NUM_CLASSES, 1, 1))
    says_none[:, 0] = 2.0
    says_lip = torch.zeros((1, train.NUM_CLASSES, 1, 1))
    says_lip[:, 1] = 2.0
    lip = torch.full((1, 1, 1), labels.CLASS_IDS["lip"], dtype=torch.int64)
    none = torch.zeros((1, 1, 1), dtype=torch.int64)
    both = torch.cat([lip, none])

    missed = train.loss_fn((torch.cat([says_none, says_none]),), both, weights)
    falsely = train.loss_fn((torch.cat([says_lip, says_lip]),), both, weights)

    assert missed > falsely


def test_overlap_cells_leaves_unknown_cells_out_of_both_counts():
    label = torch.tensor([[1, 1, labels.IGNORE, 0]])
    pred = torch.tensor([[1, 0, 1, 1]])

    both, either = train.overlap_cells(pred, label)

    assert both[0].item() == 1
    assert either[0].item() == 3
    assert both[1:].sum().item() == 0


def test_score_averages_only_classes_that_appeared_and_reports_clean_false_positive():
    both = np.array([5, 0, 0, 0, 0, 0, 0])
    either = np.array([10, 4, 0, 0, 0, 0, 0])

    result = train.score(both, either, wrong=2, clean=100)

    assert result["classIoU"]["lip"] == 0.5
    assert result["classIoU"]["blush"] == 0.0
    assert result["classIoU"]["brow"] is None
    assert result["meanIoU"] == 0.25
    assert result["cleanFalsePositive"] == 0.02


def test_score_has_no_clean_false_positive_when_there_is_no_clean_sample():
    zeros = np.zeros(len(train.PAINTED))

    result = train.score(zeros, zeros, wrong=0, clean=0)

    assert result["cleanFalsePositive"] is None
    assert result["meanIoU"] == 0.0


@pytest.mark.parametrize(
    ("share", "real", "synth", "expected"),
    [
        (0.5, 3, 10, [2, 2, 2, 2]),
        (0.25, 3, 10, [1, 1, 1, 1]),
        (0.125, 3, 10, [0, 1, 0, 1]),
        (0.0, 3, 10, [0, 0, 0, 0]),
        (1.0, 3, 10, [4, 4, 4, 4]),
        (0.5, 0, 10, [0, 0, 0, 0]),
        (0.0, 3, 0, [4, 4, 4, 4]),
    ],
)
def test_real_count_spreads_real_samples_over_batches_and_falls_back_to_what_exists(
    share, real, synth, expected
):
    assert [train.real_count(step, 4, share, real, synth) for step in range(4)] == expected


@pytest.mark.parametrize("name", ["bisenet", "small"])
def test_both_start_models_take_six_layers_and_answer_one_number_per_cell(name):
    model = train.build_model(name, pretrained=None).eval()

    with torch.no_grad():
        outputs = model(torch.zeros((1, 6, SIZE, SIZE)))

    assert outputs[0].shape == (1, train.NUM_CLASSES, SIZE, SIZE)


def test_widened_first_layer_answers_like_the_original_when_before_equals_after():
    original = torch.nn.Conv2d(3, 4, kernel_size=7, stride=2, padding=3, bias=False)
    wide = train.widen_input(original)
    picture = torch.rand((1, 3, 16, 16))

    assert torch.allclose(wide(torch.cat([picture, picture], dim=1)), original(picture), atol=1e-5)


def test_evaluate_scores_by_source_and_counts_clean_samples(tmp_path):
    lip = np.zeros((SIZE, SIZE), dtype=np.uint8)
    lip[:8, :] = labels.CLASS_IDS["lip"]
    clean = np.zeros((SIZE, SIZE), dtype=np.uint8)
    items = [
        (write_sample(tmp_path / "real", flat(100), flat(140), lip), 0),
        (write_sample(tmp_path / "synth", flat(100), flat(100), clean), 1),
    ]

    class AlwaysLip(torch.nn.Module):
        def forward(self, x):
            out = torch.zeros((x.shape[0], train.NUM_CLASSES, SIZE, SIZE))
            out[:, labels.CLASS_IDS["lip"]] = 1.0
            return (out,)

    loader = torch.utils.data.DataLoader(train.Pairs(items, SIZE, augment=False), batch_size=2)
    result = train.evaluate(AlwaysLip(), loader, "cpu")

    assert result["real"]["classIoU"]["lip"] == 8 / SIZE
    assert result["real"]["cleanFalsePositive"] is None
    assert result["synth"]["cleanFalsePositive"] == 1.0
    assert result["all"]["cleanFalsePositive"] == 1.0


def test_lr_scale_warms_up_then_stays_flat_or_falls_to_zero_with_cosine():
    total = 10_000
    warm = train.WARMUP_STEPS

    assert train.lr_scale(0, total, "constant") == pytest.approx(1 / warm)
    assert train.lr_scale(warm, total, "constant") == 1.0
    assert train.lr_scale(total - 1, total, "constant") == 1.0
    assert train.lr_scale(total // 2, total, "cosine") == pytest.approx(0.5, abs=1e-3)
    assert train.lr_scale(total, total, "cosine") == pytest.approx(0.0, abs=1e-9)


def test_preloaded_pairs_give_the_same_sample_as_reading_each_time(tmp_path, monkeypatch):
    label = np.zeros((SIZE, SIZE), dtype=np.uint8)
    label[:, :8] = labels.CLASS_IDS["brow"]
    after = flat(120)
    after[:, :8] = 30
    folder = write_sample(tmp_path / "one", flat(100), after, label)
    monkeypatch.setattr(train.random, "random", lambda: 0.0)
    monkeypatch.setattr(train.random, "uniform", lambda low, high: 0.1)

    read = train.Pairs([(folder, 0)], SIZE, augment=True)[0]
    kept = train.Pairs([(folder, 0)], SIZE, augment=True, preload=True, threads=2)

    for left, right in zip(read[:2], kept[0][:2], strict=True):
        assert torch.equal(left, right)
    assert read[2] == kept[0][2]
    assert torch.equal(kept[0][0], kept[0][0])
    assert (kept[0][1][:, -8:] == labels.CLASS_IDS["brow"]).all()
