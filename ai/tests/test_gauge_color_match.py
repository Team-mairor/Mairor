import numpy as np
import pytest

from app.tasks.area.parts.area_preparation import rgb_to_lab
from tools.gauge import color_match as cm
from tools.gauge import compare_color_match as tool
from tools.gauge import synthetic as syn

SKIN = (205, 160, 140)
LIP = (185, 105, 110)
PIGMENT = (190, 40, 60)
WHITE = (235, 228, 222)


def linear(rgb) -> np.ndarray:
    return cm.linear_of_srgb(np.asarray(rgb, dtype=np.float64))


def painted(before: np.ndarray, pigment: np.ndarray, amount: float) -> np.ndarray:
    return (1 - amount) * before + amount * pigment


def side(skin, before, amount, gain=(1.0, 1.0, 1.0), pigment=PIGMENT) -> cm.AreaSide:
    """조명 배수 gain 아래에서 before 색 칸에 pigment를 amount만큼 바른 영역 하나."""
    light = np.asarray(gain)
    raw_before = linear(before)
    raw_after = painted(raw_before, linear(pigment), amount)
    return cm.AreaSide(
        before=raw_before * light,
        after=raw_after * light,
        skin=linear(skin) * light,
        white=linear(WHITE) * light,
        ratio=raw_after / raw_before,
    )


def test_lab_of_matches_service_conversion():
    """서비스(rgb_to_lab)와 같은 Lab이어야 레퍼런스 쪽 효과 기록과 같은 눈금으로 견줄 수 있다."""
    rng = np.random.default_rng(3)
    rgb = rng.integers(0, 256, (200, 3)).astype(np.uint8)
    assert cm.lab_of(cm.linear_of_srgb(rgb)) == pytest.approx(rgb_to_lab(rgb), abs=1e-9)


def test_linear_of_lab_inverts_lab_of():
    """Lab에서 다시 선형 RGB로 돌아와야 효과를 다른 바탕에 얹은 색을 그림으로 그릴 수 있다."""
    rng = np.random.default_rng(4)
    rgb = rng.uniform(0.01, 1, (200, 3))
    assert cm.linear_of_lab(cm.lab_of(rgb)) == pytest.approx(rgb, abs=1e-9)


@pytest.mark.parametrize("space", cm.SPACES)
def test_full_adaptation_moves_source_onto_target(space):
    """밝기까지 맞추면 맨피부가 기준 피부와 똑같은 색이 되어야 한다."""
    source, target = linear((180, 140, 110)), linear((225, 190, 170))
    moved = cm.adaptation(source, target, space) @ source
    assert moved == pytest.approx(target, abs=1e-9)


@pytest.mark.parametrize("space", cm.SPACES)
def test_chroma_adaptation_keeps_lightness(space):
    """색만 맞추면 밝기(Y)는 원래 피부 그대로 남아 어두운 피부가 밝은 피부로 바뀌지 않는다."""
    source, target = linear((150, 110, 85)), linear((225, 190, 170))
    moved = cm.adaptation(source, target, space, "chroma") @ source
    luma = np.array([0.212671, 0.715160, 0.072169])
    assert moved @ luma == pytest.approx(source @ luma, rel=1e-9)
    chroma = moved / moved.sum()
    assert chroma == pytest.approx(target / target.sum(), abs=1e-9)


def test_compare_reads_identical_sides_as_same():
    """같은 화면·같은 화장이면 어느 방법이든 같은 화장(0)과 진하기 비율 1로 읽어야 한다."""
    one = side(SKIN, LIP, 0.4)
    for method in cm.all_methods():
        result = cm.compare(one, one, method)
        assert float(result.same) == pytest.approx(0, abs=1e-6), method.label
        assert float(result.ratio) == pytest.approx(1, abs=1e-6), method.label


@pytest.mark.parametrize("gain", [(0.7, 0.7, 0.7), (1.15, 1.0, 0.85), (0.63, 0.7, 0.77)])
def test_channel_light_is_removed_by_skin_and_local_matching(gain):
    """조명이 채널마다 곱하기만 하면 피부로 맞추는 방법은 같은 화장을 0으로 읽는다.

    맞추지 않으면 크게 읽는다.
    """
    reference = side(SKIN, LIP, 0.4)
    user = side(SKIN, LIP, 0.4, gain)
    assert float(cm.compare(reference, user, cm.MatchMethod("none")).same) > 2
    for name in ("skin", "skinEffect", "local"):
        result = cm.compare(reference, user, cm.MatchMethod(name))
        assert float(result.same) == pytest.approx(0, abs=1e-6), name


def test_more_paint_reads_as_larger_ratio():
    """같은 조명에서 더 많이 바르면 진하기 비율이 커져야 게이지가 위로 간다."""
    reference = side(SKIN, LIP, 0.4)
    ratios = [
        float(cm.compare(reference, side(SKIN, LIP, 0.4 * k), cm.MatchMethod("local")).ratio)
        for k in (0.5, 0.7, 1.0, 1.4, 2.0)
    ]
    assert ratios == sorted(ratios)
    assert ratios[2] == pytest.approx(1)


def test_local_matching_uses_cell_ratio_when_given():
    """칸마다 비율이 있으면 영역 색 비율 대신 그것을 쓴다.

    칸마다 다르게 바른 자국이 평균에 묻히지 않게 하려는 것이다.
    """
    one = side(SKIN, LIP, 0.4)
    other = cm.AreaSide(one.before, one.after, one.skin, one.white, ratio=np.array([1.0, 1.0, 1.0]))
    result = cm.compare(one, other, cm.MatchMethod("local"))
    assert float(result.ratio) == pytest.approx(0)


def test_compare_handles_many_areas_at_once():
    """여러 영역을 한 번에 견줘야 합성 시험 세트 수만 쌍을 빠르게 잴 수 있다."""
    reference = side(SKIN, LIP, 0.4)
    many = cm.AreaSide(
        *(
            np.stack([getattr(reference, f)] * 5)
            for f in ("before", "after", "skin", "white", "ratio")
        )
    )
    for method in cm.all_methods():
        result = cm.compare(many, many, method)
        assert result.same.shape == (5,)


def test_measure_side_skips_empty_area():
    """영역 칸이 없으면 값을 지어내지 않고 None이어야 한다."""
    face = np.full((8, 8, 3), 150, dtype=np.uint8)
    nothing = np.zeros((8, 8), dtype=bool)
    assert cm.measure_side(face, face, nothing, ~nothing) is None


def test_measure_side_reads_cell_ratio():
    """칸마다 바른 뒤 ÷ 바르기 전 비율의 가운데 값을 낸다."""
    before = np.full((8, 8, 3), 200, dtype=np.uint8)
    after = before.copy()
    after[:4] = (100, 200, 200)
    area = np.zeros((8, 8), dtype=bool)
    area[:4] = True
    result = cm.measure_side(before, after, area, ~area)
    assert result.ratio == pytest.approx(
        cm.linear_of_srgb(np.array([100.0, 200, 200]))
        / cm.linear_of_srgb(np.array([200.0, 200, 200]))
    )
    assert result.skin == pytest.approx(cm.linear_of_srgb(np.array([200.0, 200, 200])))


def test_plain_camera_and_same_tone_change_nothing():
    """기본 카메라·같은 피부톤은 지도를 바꾸지 않아야 조명만 바꾼 시험과 섞이지 않는다."""
    rng = np.random.default_rng(5)
    face = rng.integers(0, 256, (16, 16, 3)).astype(np.uint8)
    assert (syn.apply_camera(face, syn.Camera()) == face).all()
    assert (syn.shot(face, syn.Light(), syn.Camera()) == face).all()


def test_skin_tone_is_applied_before_makeup():
    """피부톤은 얼굴 자체라 화장 안료 색은 바꾸지 않는다.

    불투명하게 바른 칸은 피부톤과 상관없이 안료 색이다.
    """
    face = np.full((4, 4, 3), 200, dtype=np.uint8)
    mask = np.ones((4, 4))
    makeup = syn.Makeup("lip", mask, PIGMENT, 1.0)
    for tone in syn.SKIN_TONES:
        out = syn.shot(face, syn.Light(), syn.Camera(), (makeup,), tone)
        assert (out == np.array(PIGMENT, dtype=np.uint8)).all(), tone


def test_beauty_filter_is_not_a_channel_gain():
    """뷰티 필터(밝히기)는 채널 곱하기가 아니라서 어두운 칸과 밝은 칸의 바뀐 비율이 달라야 한다."""
    face = np.zeros((2, 1, 3), dtype=np.uint8)
    face[0, 0] = (60, 40, 30)
    face[1, 0] = (220, 180, 160)
    out = syn.apply_camera(face, syn.Camera(lift=0.1)).astype(float)
    dark = cm.linear_of_srgb(out[0, 0]) / cm.linear_of_srgb(face[0, 0].astype(float))
    light = cm.linear_of_srgb(out[1, 0]) / cm.linear_of_srgb(face[1, 0].astype(float))
    assert dark[0] > light[0] + 0.2


def test_regime_splits_skin_and_capture_changes():
    """장면 쌍을 피부가 같은지와 찍는 조건이 같은지로 나눠야 피부톤 문제를 따로 볼 수 있다."""
    plain, warm = syn.Camera(), syn.Camera("photoWarm", balance=(1.06, 1, 0.92))
    base = tool.Shot("a", "same", syn.Light(), plain)
    assert tool.regime(base, base) == "identical"
    assert tool.regime(base, tool.Shot("a", "same", syn.Light(), warm)) == "lightOnly"
    assert tool.regime(base, tool.Shot("a", "darker", syn.Light(), plain)) == "skinOnly"
    assert tool.regime(base, tool.Shot("b", "same", syn.LIGHTS[1], plain)) == "both"


def test_auc_counts_ties_as_half():
    """완전히 갈리면 1, 못 가르면 0.5다."""
    assert tool.auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert tool.auc(np.array([1.0, 1.0]), np.array([1.0, 1.0])) == 0.5


def test_rank_agreement_reads_blocks_of_amounts():
    """k 순서대로 커지면 1, 거꾸로면 -1이다."""
    up = np.array([0.5, 0.7, 1.0, 1.4, 2.0])
    assert tool.rank_agreement(np.concatenate([up, up])) == 1.0
    assert tool.rank_agreement(up[::-1].copy()) == -1.0


def test_turn_hue_keeps_lightness_and_chroma():
    """색감 시험용 안료는 색상 각도만 돌고 밝기·채도는 그대로여야 진하기와 섞이지 않는다."""
    original = cm.lab_of(linear(PIGMENT))
    turned = cm.lab_of(linear(tool.turn_hue(PIGMENT, 25)))
    assert turned[0] == pytest.approx(original[0], abs=1.0)
    assert np.hypot(*turned[1:]) == pytest.approx(np.hypot(*original[1:]), abs=2.0)
    angle = np.degrees(np.arctan2(turned[2], turned[1]) - np.arctan2(original[2], original[1]))
    assert angle == pytest.approx(25, abs=2.0)


DARKER_TONE = np.array([0.62, 0.5, 0.42])


def toned(
    side_: cm.AreaSide, tone: np.ndarray, pigment=PIGMENT, amount: float = 0.4
) -> cm.AreaSide:
    """같은 조명에서 피부만 tone배 어두운 사람이 같은 안료를 amount만큼 바른 영역.

    바르기 전 색과 맨피부가 tone배이고, 흰자는 피부톤과 상관없어 그대로다.
    """
    before = side_.before * tone
    after = painted(before, linear(pigment), amount)
    return cm.AreaSide(before, after, side_.skin * tone, side_.white, after / before)


def test_white_anchor_reads_same_amount_on_darker_skin_as_same():
    """피부톤이 달라도 같은 양이면 같다고 읽어야 한다.

    흰자 기준은 피부 차이를 조명으로 지우지 않는다.
    """
    reference = side(SKIN, LIP, 0.4)
    user = toned(reference, DARKER_TONE)
    white = cm.compare(reference, user, cm.COLOR_METHOD)
    by_skin = cm.compare(reference, user, cm.MatchMethod("local", target="user"))
    assert float(white.same) < 1.0
    assert float(white.same) < float(by_skin.same) / 2
    assert abs(np.log2(float(white.ratio))) < abs(np.log2(float(by_skin.ratio)))


def test_white_anchor_still_removes_colored_light():
    """흰자도 같은 조명을 받는다.

    밝기는 그대로이고 색만 다른 조명이 채널마다 곱해지면 흰자 색으로 지워진다.
    흰자가 완전한 회색이 아니라 흰자 밝기가 조금 달라지는 만큼만 남는다(ΔE 0.05 아래).
    """
    cast = np.array([0.9, 1.0, 1.12])
    cast = cast / float(cast @ cm.SRGB_TO_XYZ[1])
    reference = side(SKIN, LIP, 0.4)
    user = side(SKIN, LIP, 0.4, gain=tuple(cast))
    assert float(cm.compare(reference, user, cm.COLOR_METHOD).same) < 0.05


def test_white_anchor_ignores_white_brightness():
    """흰자 밝기는 시선 · 눈꺼풀 그늘로 흔들려 색만 맞춘다.

    사용자 흰자만 어둡게 잡혀도(같은 장면) 결과가 그대로이고, 밝기까지 맞추면 달라진다.
    """
    reference = side(SKIN, LIP, 0.4)
    user = side(SKIN, LIP, 0.4)
    shaded = cm.AreaSide(user.before, user.after, user.skin, user.white * 0.7, user.ratio)
    full = cm.MatchMethod("mix", weight=1.0, anchor="white")
    assert float(cm.compare(reference, shaded, cm.COLOR_METHOD).same) == pytest.approx(0, abs=1e-6)
    assert float(cm.compare(reference, shaded, full).same) > 1.0


def test_anchor_gain_keeps_brightness_by_degree():
    """밝기 배수를 full은 그대로, half는 제곱근만, chroma는 1로 둔다."""
    reference = np.array([0.8, 0.8, 0.8])
    user = reference * 0.5
    methods = {
        degree: cm.MatchMethod("mix", degree=degree, anchor="white")
        for degree in ("full", "half", "chroma")
    }
    gains = {degree: cm.anchor_gain(reference, user, method) for degree, method in methods.items()}
    assert gains["full"] == pytest.approx([0.5] * 3)
    assert gains["half"] == pytest.approx([0.5**0.5] * 3)
    assert gains["chroma"] == pytest.approx([1.0] * 3)


def test_white_anchor_needs_white_color():
    """흰자 기준인데 흰자 색이 없으면 맨피부로 몰래 바꾸지 않고 멈춘다."""
    one = side(SKIN, LIP, 0.4)
    blind = cm.AreaSide(one.before, one.after, one.skin)
    with pytest.raises(ValueError):
        cm.compare(blind, blind, cm.COLOR_METHOD)


def test_least_paint_finds_black_pigment_amount():
    """검정 안료는 모든 채널이 같은 비율로 어두워져 가장 적게 바른 양이 실제 양과 같다."""
    before = linear(SKIN)
    after = painted(before, np.zeros(3), 0.3)
    assert float(cm.least_paint(before, after - before)) == pytest.approx(0.3)


def test_least_paint_has_a_floor():
    """거의 안 바뀐 영역은 양을 0으로 두지 않아 안료 색이 무한히 멀어지지 않는다."""
    before = linear(SKIN)
    assert float(cm.least_paint(before, np.zeros(3))) == cm.LEAST_PAINT_MIN


def test_white_color_takes_bright_unclipped_eye_pixels():
    """눈 구멍 안 밝은 칸(흰자)만 쓰고, 하얗게 날아간 반사광과 어두운 눈동자는 뺀다."""
    face = np.zeros((4, 8, 3), dtype=np.uint8)
    holes = np.zeros((4, 8), dtype=bool)
    holes[1:3] = True
    face[1, :] = (60, 40, 30)
    face[2, :6] = (200, 190, 185)
    face[2, 6:] = (255, 255, 255)
    picked = cm.white_cells(face, holes)
    assert picked[2, :6].sum() >= 1
    assert not picked[2, 6:].any()
    assert not picked[1].any()
    assert cm.white_color(face, holes) == pytest.approx(linear((200, 190, 185)))


@pytest.mark.parametrize("makeup", ["lip", "blush", "eyeshadow", "contour", "highlight"])
def test_colored_makeup_uses_white_anchor_mix(makeup):
    """색 있는 화장은 피부톤을 지우지 않는 흰자 기준 혼합 모델로 견준다."""
    assert cm.method_for(makeup) == cm.COLOR_METHOD


@pytest.mark.parametrize("makeup", ["brow", "eyeliner"])
def test_dark_makeup_uses_local_ratio(makeup):
    """검정·갈색 화장은 실제 카메라 비교에서 버틴 자리마다 비율(사용자 바탕)로 견준다."""
    assert cm.method_for(makeup) == cm.DARK_METHOD
