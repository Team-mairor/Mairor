import numpy as np

from tools.gauge import color_match as cm
from tools.gauge import compare_color_match as ccm
from tools.gauge import compare_substitute as cs
from tools.gauge import measure as ms
from tools.gauge import synthetic as syn


def flat_face() -> np.ndarray:
    """피부색 한 가지에 두 눈 구멍만 흰자색인 256 얼굴 지도."""
    face = np.full((ccm.SIZE, ccm.SIZE, 3), (200, 150, 130), dtype=np.uint8)
    face[syn.eye_holes(ccm.SIZE)] = (225, 215, 210)
    return face


def test_catalog_pairs_spread_references_and_skip_the_reference_itself():
    colors = ["#C02030", "#D04040", "#E06060", "#F08080", "#A01020", "#B03040"]

    pairs = cs.catalog_pairs(colors)

    assert 1 <= len(pairs) <= cs.CATALOG_REFERENCES
    for ref, subs in pairs:
        assert ref not in subs and len(subs) == len(colors) - 1


def test_synthetic_plan_has_every_substitute_kind_for_each_reference():
    plan = cs.plan_pairs(None)

    assert len(plan) == sum(len(ccm.PIGMENTS[p]) for p in cs.PARTS) * len(cs.SUBS)
    assert {row[3] for row in plan} == {"same", "hue", "chroma", "light"}


def test_same_product_in_the_same_shot_reads_one_and_scores_come_out():
    """같은 얼굴 · 같은 조건 · 같은 제품을 같은 진하기로 바르면 measure 비율이 1이어야
    비교 도구를 믿는다.
    """
    faces = {"flat": flat_face()}
    plan = [row for row in cs.plan_pairs(None) if row[0] == "lip:red" and row[1] == 0][:3]
    areas = cs.area_weights(ccm.makeup_shapes())
    refs = cs.reference_rows(faces, areas, plan)
    users = cs.user_rows(faces, areas, plan, cs.user_shots(["flat"])[:1])

    table = cs.pair_table(refs, users, ["flat"])
    pick = (
        (table["referenceShot"] == "flat|same|plain")
        & (table["kind"] == cs.SUB_KINDS.index("same"))
        & (table["k"] == 1.0)
        & (table["wrong"] == 0)
    )
    result = cs.scores(table)

    before = (table["referenceShot"] == "flat|same|plain") & (table["k"] == 0.0)

    assert np.allclose(table["reference_ratio"][pick], 1.0, atol=0.03)
    assert np.allclose(table["reference_ratio"][before], 0.0, atol=0.03)
    assert set(result["strength"]) == set(cs.STRENGTH_OPTIONS) | {
        f"rule{int(noise)}" for noise in cs.NOISES
    }
    assert "near1noise0" in result["color"]


def test_compare_rows_reads_the_same_values_as_measure_side():
    """비교 도구가 measure.measure_side를 그대로 써야 FE가 쓸 비율과 같은 값으로 후보를 고른다."""
    before = np.array([[0.42, 0.28, 0.22], [0.42, 0.28, 0.22]])
    after = 0.8 * before + 0.2 * np.array([[0.5, 0.05, 0.08], [0.1, 0.07, 0.06]])
    white = np.array([[0.6, 0.5, 0.47], [0.6, 0.5, 0.47]])
    reference = cm.AreaSide(before, after, before, white)
    user = cm.AreaSide(before * 1.02, (0.85 * before + 0.15 * after) * 1.02, before * 1.02, white)

    out = cs.compare_rows(reference, user, ["lip", "brow"])

    for i, makeup in enumerate(["lip", "brow"]):
        side = ms.measure_side(
            cm.AreaSide(before[i], after[i], before[i], white[i]),
            cm.AreaSide(user.before[i], user.after[i], user.skin[i], user.white[i]),
            makeup,
            ms.MIN_AREA_CELLS,
        )
        assert out["ratio"][i] == side.ratio
        assert (np.isnan(out["hue"][i]) and side.hue is None) or out["hue"][i] == side.hue
