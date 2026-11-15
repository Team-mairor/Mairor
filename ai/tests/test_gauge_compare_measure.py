import numpy as np
import pytest

from tools.gauge import color_match as cm
from tools.gauge import compare_color_match as ccm
from tools.gauge import compare_measure as tool
from tools.gauge import synthetic as syn


def test_chroma_scale_keeps_lightness_and_hue():
    color = (190, 40, 60)
    before = cm.lab_of(cm.linear_of_srgb(np.asarray(color, float)))

    after = cm.lab_of(cm.linear_of_srgb(np.asarray(tool.chroma_scale(color, 0.6), float)))

    assert after[0] == pytest.approx(before[0], abs=1.0)
    assert np.degrees(np.arctan2(after[2], after[1])) == pytest.approx(
        np.degrees(np.arctan2(before[2], before[1])), abs=2.0
    )
    assert np.hypot(after[1], after[2]) == pytest.approx(
        0.6 * np.hypot(before[1], before[2]), rel=0.05
    )


def test_user_variants_hold_amounts_turns_and_chroma_at_amount_one():
    variants = tool.user_variants()

    assert [k for kind, _, k in variants if kind == "amount"] == list(ccm.AMOUNTS)
    assert all(k == 1.0 for kind, _, k in variants if kind != "amount")


def test_side_masks_split_at_the_middle_of_the_map():
    alpha = np.ones((4, 4))

    halves = tool.side_masks(alpha)

    assert halves["left"][:, 2:].all() and not halves["left"][:, :2].any()
    assert np.array_equal(halves["left"] + halves["right"], alpha)


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        (ccm.Shot("go", "same", syn.Light("same"), syn.Camera("plain")), "identical"),
        (ccm.Shot("go", "same", syn.Light("warm8"), syn.Camera("plain")), "lightOnly"),
        (ccm.Shot("go", "darker", syn.Light("same"), syn.Camera("plain")), "toneOnly"),
        (ccm.Shot("go", "darker", syn.Light("warm8"), syn.Camera("plain")), "toneLight"),
        (ccm.Shot("seoyeon", "same", syn.Light("same"), syn.Camera("plain")), "faceChanged"),
    ],
)
def test_regime_splits_pairs_by_what_changed(user, expected):
    reference = ccm.Shot("go", "same", syn.Light("same"), syn.Camera("plain"))

    assert tool.regime(reference, user) == expected


def test_reference_index_matches_shape_pigment_strength_order():
    meta = np.array([[0, 0, 0, 0, 1, 1], [0, 1, 1, 0, 1, 1], [3, 0, 1, 0, 1, 1]], dtype=float)

    assert tool.reference_index(meta).tolist() == [0, 3, 13]


def test_amount_scores_reward_reading_each_amount_in_its_band():
    amount = np.array([0.5, 1.0, 2.0])

    right = tool.amount_scores(np.array([0.5, 1.0, 2.0]), amount, np.zeros(3))
    wrong = tool.amount_scores(np.array([1.0, 1.0, 1.0]), amount, np.zeros(3))

    assert right["bandHit"] == 1.0 and right["ratioError"] == 0.0
    assert wrong["bandHit"] == pytest.approx(1 / 3)
