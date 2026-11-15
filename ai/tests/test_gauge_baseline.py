import math

import cv2
import numpy as np
import pytest

from app.tasks.area.common.face_map import face_cells
from app.tasks.area.parts.makeup_effect import delta_e_2000
from tools.gauge import baseline as bl
from tools.gauge import synthetic as syn

SIZE = 256
SKIN = (205, 160, 140)
LIP = (185, 105, 110)


def flat_face() -> np.ndarray:
    """얼굴 칸은 피부색 하나, 눈 구멍 밖 입술 칸은 입술색, 얼굴 밖은 흰색인 256칸 지도.

    사람 얼굴 사진은 저장소에 넣지 않아서, 규칙이 지켜지는지 보는 시험은 이 지도로 한다.
    """
    face = cv2.resize(face_cells().astype(np.uint8), (SIZE, SIZE), interpolation=cv2.INTER_NEAREST)
    out = np.full((SIZE, SIZE, 3), 255, dtype=np.uint8)
    out[face > 0] = SKIN
    lips = cv2.resize(lip_pixels().astype(np.uint8), (SIZE, SIZE), interpolation=cv2.INTER_NEAREST)
    out[lips > 0] = LIP
    return out


def lip_pixels() -> np.ndarray:
    from app.tasks.area.common.face_map import MAP_SIZE, map_points
    from app.tasks.area.common.region_mask import polygon_mask
    from app.tasks.area.common.region_points import REGION_POINTS

    return polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)


def cheek_mask() -> np.ndarray:
    from app.tasks.area.parts.blush_area import cheek_range

    both = cheek_range("leftCheek") | cheek_range("rightCheek")
    return cv2.resize(both.astype(np.uint8), (SIZE, SIZE), interpolation=cv2.INTER_AREA) > 0


def to_grid(mask: np.ndarray) -> np.ndarray:
    small = cv2.resize(mask.astype(np.float32), (bl.GRID, bl.GRID), interpolation=cv2.INTER_AREA)
    return small >= 0.5


def baseline_of(face_map: np.ndarray) -> bl.Baseline:
    return bl.build_baseline([bl.grid_lab(face_map)])


def unmade_reading(current: np.ndarray, base: bl.Baseline, made, method) -> float:
    """화장하지 않은 칸에서 읽히는 화장 효과 크기(ΔE2000)의 가운데 값. 0이어야 맞다."""
    est = current - bl.light_change(current, base, made, method)
    cells = base.cells & bl.skin_cells() & (np.ones_like(base.cells) if made is None else ~made)
    return float(np.median(bl.delta_e_map(est, base.lab)[cells]))


def test_delta_e_map_matches_single_formula():
    """칸마다 재는 ΔE2000이 레퍼런스 쪽 delta_e_2000과 같아야 두 쪽 진하기를 견줄 수 있다."""
    rng = np.random.default_rng(7)
    first = np.c_[rng.uniform(0, 100, 300), rng.uniform(-70, 70, 300), rng.uniform(-70, 70, 300)]
    second = first + rng.normal(0, 10, first.shape)
    expected = [delta_e_2000(a, b) for a, b in zip(first, second, strict=True)]
    assert bl.delta_e_map(first, second) == pytest.approx(expected, abs=1e-9)


def test_grid_lab_leaves_eye_holes_empty():
    """눈 구멍은 깜빡일 때마다 색이 바뀌어 기준에서 빠져야 한다."""
    lab = bl.grid_lab(flat_face())
    assert np.isnan(lab[~bl.measured_cells()]).all()
    assert not np.isnan(lab[bl.measured_cells()]).any()


def test_grid_lab_keeps_lip_color_apart_from_skin():
    """입술도 화장하는 자리라 기준에 들어가고, 피부와 다른 색으로 남아야 한다."""
    lab = bl.grid_lab(flat_face())
    lip_map = cv2.resize(lip_pixels().astype(np.uint8), (SIZE, SIZE)) > 0
    lips = to_grid(lip_map) & bl.measured_cells()
    skin = bl.skin_cells()
    assert np.median(lab[lips][:, 1]) > np.median(lab[skin][:, 1]) + 5


def test_baseline_median_ignores_one_hand_frame():
    """기준 사진 중 한 장에 손이 지나가도 가운데 값이라 기준이 흔들리지 않아야 한다."""
    face = flat_face()
    hand = face.copy()
    hand[100:180, 60:200] = (90, 70, 60)
    base = bl.build_baseline([bl.grid_lab(m) for m in (face, face, hand, face, face)])
    clean = baseline_of(face)
    assert np.nanmax(bl.delta_e_map(base.lab, clean.lab)[base.cells]) < 1e-6
    assert base.frames == 5


@pytest.mark.parametrize("light", [syn.LIGHTS[1], syn.LIGHTS[3], syn.LIGHTS[4], syn.LIGHTS[7]])
@pytest.mark.parametrize("method", ["foreheadChin", "skin", "local"])
def test_even_light_change_is_removed(light, method):
    """얼굴 전체가 고르게 어두워지거나 누레지면 세 보정 모두 안 바른 칸을 0 가까이로 돌려야 한다."""
    face = flat_face()
    base = baseline_of(face)
    current = bl.grid_lab(syn.apply_light(face, light))
    assert unmade_reading(current, base, None, "none") > 1.5
    assert unmade_reading(current, base, None, method) < 0.6


def test_one_side_shade_needs_local_correction():
    """한쪽만 그늘지면 값 하나로 빼는 보정은 두 볼이 달리 읽힌다.

    자리마다 빼는 보정만 두 볼 모두 0에 가깝다.
    """
    face = flat_face()
    base = baseline_of(face)
    current = bl.grid_lab(syn.apply_light(face, syn.Light("shade", shade=0.4, shade_side="left")))
    left = np.zeros((bl.GRID, bl.GRID), bool)
    left[:, bl.GRID // 2 + 4 :] = True
    right = np.zeros_like(left)
    right[:, : bl.GRID // 2 - 4] = True
    cells = base.cells & bl.skin_cells()

    def side(method, half):
        est = current - bl.light_change(current, base, None, method)
        return float(np.median(bl.delta_e_map(est, base.lab)[cells & half]))

    assert side("skin", left) > 2 or side("skin", right) > 2
    assert side("local", left) < 1.5
    assert side("local", right) < 1.5


def test_makeup_cells_must_be_left_out_of_light():
    """바른 칸을 조명 재기에서 빼야 화장 효과가 조명으로 지워지지 않는다."""
    face = flat_face()
    base = baseline_of(face)
    blush = syn.Makeup("blush", cheek_mask(), (235, 120, 135), 0.3)
    truth = bl.grid_lab(syn.apply_makeup(face, [blush]))
    current = bl.grid_lab(syn.scene(face, syn.LIGHTS[4], [blush]))
    made = to_grid(cheek_mask()) & base.cells
    with_out = bl.makeup_effect(current, base, made) + base.lab
    blind = bl.makeup_effect(current, base, None) + base.lab
    error_out = np.median(bl.delta_e_map(with_out, truth)[made])
    error_blind = np.median(bl.delta_e_map(blind, truth)[made])
    assert error_out < 1.0
    assert error_blind > error_out


def test_step_start_base_counts_only_this_step():
    """단계 시작 기준에는 앞 단계 화장이 들어 있어, 이번 단계에서 더한 만큼만 읽혀야 한다.

    맨얼굴 기준으로 재면 앞 단계 블러셔까지 더해져 레퍼런스(직전 → 직후)와 값이 달라진다.
    """
    face = flat_face()
    cheeks = cheek_mask()
    first = syn.Makeup("blush", cheeks, (235, 120, 135), 0.25)
    second = syn.Makeup("blush2", cheeks, (200, 90, 110), 0.2)
    bare = baseline_of(face)
    step_start = baseline_of(syn.apply_makeup(face, [first]))
    after = syn.apply_makeup(face, [first, second])
    current = bl.grid_lab(syn.apply_light(after, syn.LIGHTS[4]))
    made = to_grid(cheeks) & step_start.cells
    truth = bl.grid_lab(after)
    added = bl.delta_e_map(truth, step_start.lab)[made]
    on_step = bl.makeup_effect(current, step_start, made) + step_start.lab
    on_bare = bl.makeup_effect(current, bare, made) + bare.lab
    from_step = bl.delta_e_map(on_step, step_start.lab)
    from_bare = bl.delta_e_map(on_bare, bare.lab)
    assert np.median(from_step[made]) == pytest.approx(np.median(added), abs=0.6)
    assert np.median(from_bare[made]) > np.median(added) + 2


def test_margin_keeps_spilled_makeup_out_of_light(monkeypatch):
    """가이드보다 조금 넓게 바른 화장도 둘레 여유 칸 덕분에 조명으로 읽히지 않아야 한다.

    여유 칸이 없으면 넘친 화장이 조명 변화로 읽혀 그만큼 화장 효과가 지워진다.
    """
    face = flat_face()
    base = baseline_of(face)
    guide = cheek_mask()
    spilled = cv2.dilate(guide.astype(np.uint8), np.ones((17, 17), np.uint8)) > 0
    blush = syn.Makeup("blush", spilled, (235, 120, 135), 0.3)
    truth = bl.grid_lab(syn.apply_makeup(face, [blush]))
    current = bl.grid_lab(syn.scene(face, syn.LIGHTS[1], [blush]))
    made = to_grid(guide) & base.cells

    def error():
        kept = bl.makeup_effect(current, base, made) + base.lab
        return float(np.median(bl.delta_e_map(kept, truth)[made]))

    with_margin = error()
    monkeypatch.setattr(bl, "ZONE_MARGIN_CELLS", 0)
    without_margin = error()
    assert with_margin < 1.0
    assert without_margin > with_margin + 2


def test_whole_face_makeup_is_read_as_light_by_every_correction():
    """얼굴 전체를 바꾸는 화장(파운데이션)은 매번 피부로 조명을 재는 보정에서는 0으로 지워진다.

    그래서 기준은 시작에 한 번만 잡고, 얼굴 전체 단계는 조명 보정 없이(none) 본다.
    """
    face = flat_face()
    base = baseline_of(face)
    whole = syn.Makeup("foundation", np.ones((SIZE, SIZE), bool), (230, 190, 160), 0.35)
    current = bl.grid_lab(syn.apply_makeup(face, [whole]))
    assert unmade_reading(current, base, None, "none") > 1.5
    for method in ("skin", "local"):
        assert unmade_reading(current, base, None, method) < 0.3


def test_drift_reports_darker_camera():
    """카메라가 어두워지면 drift의 밝기가 음수, 크기가 0보다 커야 측정 불가로 넘길 수 있다."""
    face = flat_face()
    base = baseline_of(face)
    same = bl.drift(bl.grid_lab(face), base)
    darker = bl.drift(bl.grid_lab(syn.apply_light(face, syn.LIGHTS[2])), base)
    assert same.size == pytest.approx(0, abs=1e-6)
    assert darker.lightness < -5
    assert darker.size > 3
    assert darker.cells == int((base.cells & bl.skin_cells()).sum())


def test_drift_without_free_skin_is_unknown():
    """조명을 잴 맨피부가 없으면(얼굴 전체가 바른 칸) 크기를 모른다고 돌려준다."""
    face = flat_face()
    base = baseline_of(face)
    result = bl.drift(bl.grid_lab(face), base, np.ones((bl.GRID, bl.GRID), bool))
    assert result.cells == 0
    assert math.isnan(result.size)


@pytest.mark.parametrize(
    ("yaw", "pitch", "roll", "eyes", "ok"),
    [
        (0.0, 0.0, 0.0, 0.3, True),
        (0.21, 0.0, 0.0, 0.3, False),
        (0.0, -0.21, 0.0, 0.3, False),
        (0.0, 0.0, 0.16, 0.3, False),
        (0.0, 0.0, 0.0, 0.15, False),
    ],
)
def test_good_frame_uses_fe_front_rule(yaw, pitch, roll, eyes, ok):
    """기준 사진은 FE 얼굴 등록과 같은 정면 기준(0.2·0.15 라디안)에 눈을 뜬 사진만 쓴다."""
    quality = bl.FrameQuality(yaw=yaw, pitch=pitch, roll=roll, eyes=eyes)
    assert bl.good_frame(quality) is ok


def test_low_camera_pose_counts_as_front_around_own_center():
    """카메라가 눈보다 낮아 정면이 pitch −0.23인 사람도 기준 사진이 모여야 한다(시연 태블릿).

    카메라 정면(0) 기준이면 빠지고, 그 사람 정면(pitch_center) 기준이면 들어간다.
    """
    pitches = [-0.23 + 0.01 * (i % 3) for i in range(20)]
    start = [bl.FrameQuality(yaw=0.0, pitch=p, roll=0.0, eyes=0.3) for p in pitches]
    center = bl.pitch_center(start)
    assert center == pytest.approx(-0.22, abs=0.02)
    assert not bl.good_frame(start[0])
    assert all(bl.good_frame(q, center) for q in start)
    looking_up = bl.FrameQuality(yaw=0.0, pitch=center + 0.25, roll=0.0, eyes=0.3)
    assert not bl.good_frame(looking_up, center)


def test_pitch_center_ignores_turned_or_closed_eye_frames():
    """정면을 정할 때 고개를 옆으로 돌렸거나 눈을 감은 사진은 세지 않는다."""
    frames = [bl.FrameQuality(yaw=0.0, pitch=-0.2, roll=0.0, eyes=0.3) for _ in range(5)]
    frames += [bl.FrameQuality(yaw=0.6, pitch=0.3, roll=0.0, eyes=0.3) for _ in range(20)]
    frames += [bl.FrameQuality(yaw=0.0, pitch=0.3, roll=0.0, eyes=0.05) for _ in range(20)]
    assert bl.pitch_center(frames) == pytest.approx(-0.2)
    assert bl.pitch_center(frames[5:]) is None


def test_shade_side_follows_person_left():
    """본인 왼쪽 그늘은 얼굴 지도 오른쪽 절반(x > 0.5)을 어둡게 해야 좌우가 FE와 맞는다."""
    gain = syn.light_gain(syn.Light("shade", shade=0.4, shade_side="left"), 64)
    assert gain[0, -1, 0] < gain[0, 0, 0]
    assert gain[0, 0, 0] == pytest.approx(1.0)
