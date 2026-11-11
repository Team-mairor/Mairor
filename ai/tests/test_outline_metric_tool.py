import math

import numpy as np

from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import lip_area
from app.tasks.area.parts.blush_area import BlushArea, cheek_range
from app.tasks.area.parts.lip_area import LipArea
from tools import outline_metric, output_area

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def circle(count: int, radius: float = 40.0) -> list[tuple[float, float]]:
    return [
        (
            100 + radius * math.cos(2 * math.pi * i / count),
            100 + radius * math.sin(2 * math.pi * i / count),
        )
        for i in range(count)
    ]


def lips() -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)


def test_smooth_points_follow_the_fe_curve_formula():
    """FE traceSmooth 식을 손으로 푼 값과 견준다.

    정사각형 아랫변은 p0=(0,10), p1=(0,0), p2=(10,0), p3=(10,10)이라 조절점이 (5/3, −5/3)과
    (25/3, −5/3)이고, 가운데(t=0.5)는 (p1 + 3·c1 + 3·c2 + p2) ÷ 8 = (5, −1.25)다.
    식의 1/6이나 조절점 방향이 FE와 다르면 이 값이 달라져서 고른 경우다.
    """
    curve = output_area.smooth_points(SQUARE)

    assert np.allclose(curve[output_area.CURVE_STEPS // 2], (5.0, -1.25))


def test_smooth_points_keep_every_given_point():
    """FE 곡선은 모든 점을 지나므로, 곡선 위 점들 가운데 원래 점이 순서대로 다 있어야 한다."""
    curve = output_area.smooth_points(SQUARE)

    assert np.allclose(curve[:: output_area.CURVE_STEPS], SQUARE)


def dented_circle(count: int = 48, radius: float = 40.0) -> list[tuple[float, float]]:
    """둥근 테두리 한 곳이 점 여러 개에 걸쳐 부드럽게 안쪽으로 들어간 모양(입술 산처럼 큰 오목)."""
    points = []
    for i in range(count):
        angle = 2 * math.pi * i / count
        offset = (angle + math.pi) % (2 * math.pi) - math.pi
        r = radius * (1 - 0.3 * math.exp(-((offset / 0.5) ** 2)))
        points.append((100 + r * math.cos(angle), 100 + r * math.sin(angle)))
    return points


def test_curve_shape_does_not_depend_on_how_many_points():
    """같은 원을 점 12개로 보내든 72개로 보내든 화면 곡선은 같은 원이라 값이 같아야 한다.

    점 위에서 꺾임 평균을 재면 점 개수에 따라 10배 넘게 달라져,
    점 간격이 다른 다듬기 후보를 공정하게 견줄 수 없어서 고른 경우다.
    """
    sparse, dense = outline_metric.curve_shape(circle(12)), outline_metric.curve_shape(circle(72))

    assert sparse[1] == dense[1] == 0
    assert abs(sparse[0] - 1) < 0.02
    assert abs(dense[0] - 1) < 0.02


def stairs(step: float) -> list[tuple[float, float]]:
    """한 칸이 step칸인 계단 20개를 내려가고 왼쪽 위로 돌아오는 테두리."""
    return [(step * (i // 2 + i % 2), step * (i // 2)) for i in range(40)] + [(0.0, 20.0 * step)]


def test_staircase_outline_wiggles_and_a_round_one_does_not():
    """3칸짜리 계단을 따라 그린 화면 곡선은 계단마다 1칸 넘게 출렁인다.

    둥근 테두리는 출렁이지 않는다. 매끈함 지표가 눈에 보이는 계단을 잡아야
    테두리 다듬기 세기를 지표로 고를 수 있어서 고른 경우다.
    """
    ratio, wiggles = outline_metric.curve_shape(stairs(3.0))

    assert wiggles >= 10
    assert ratio > 1.5
    assert outline_metric.curve_shape(circle(36))[1] == 0


def test_tiny_one_cell_stairs_are_not_counted():
    """1칸짜리 계단이 만드는 흔들림은 1칸보다 낮아 화면에서 안 보이므로 세지 않는다.

    각도로만 거르면 점이 촘촘한 테두리에서 이런 잔흔들림이 수십 번 세어져,
    그림으로는 더 매끈한데 숫자는 나빠지는 일이 생겨서 고른 경우다.
    """
    assert outline_metric.curve_shape(stairs(1.0))[1] <= 2


def test_one_big_dent_counts_as_two_turns_of_direction():
    """입술 산처럼 크게 오목한 곳 하나는 방향이 두 번 바뀔 뿐이다.

    진짜 모양의 오목함은 적게, 계단 출렁임은 많이 세야
    매끈하게 다듬으면서 큰 모양을 지킨 후보를 고를 수 있어서 고른 경우다.
    """
    assert outline_metric.curve_shape(dented_circle())[1] == 2


def test_point_crowded_near_a_corner_makes_the_fe_curve_overshoot():
    """모서리 바로 옆(2칸)에 점이 하나 더 있으면 FE 곡선은 그 모서리에서 바깥으로 휘청인다.

    점만 이으면 볼록한 사각형이라 출렁임이 없지만, 화면 곡선에는 1칸 넘는 출렁임이 생긴다.
    점이 아니라 화면 곡선 위에서 재야 사용자가 보는 흔들림을 세서 고른 경우다.
    """
    points = [(0.0, 0.0), (100.0, 0.0), (100.0, 2.0), (100.0, 100.0), (0.0, 100.0)]

    assert outline_metric.curve_shape(points)[1] >= 2


def test_even_spacing_scores_near_zero_and_crowded_points_do_not():
    """FE는 모든 점을 지나는 곡선을 그린다.

    점이 한쪽에 몰리면 곡선이 출렁이므로 몰린 점을 잡아야 해서 고른 경우다.
    """
    crowded = [
        (0.0, 0.0),
        (1.0, 0.0),
        (2.0, 0.0),
        (3.0, 0.0),
        (40.0, 0.0),
        (40.0, 40.0),
        (0.0, 40.0),
    ]

    assert outline_metric.spacing_cv(circle(36)) < 1e-6
    assert outline_metric.spacing_cv(crowded) > 0.5


def test_thickness_is_the_fe_thin_area_formula():
    """FE thin-area.ts는 넓이 × 2 ÷ 둘레를 얼굴 지도 0~1 좌표로 잰다.

    길이 400칸·두께 4칸 띠는 2 × 1,600 ÷ 808칸 ÷ MAP_SIZE로 기준 0.015보다 얇다.
    아이라인처럼 얇은 띠를 FE와 똑같이 얇다고 봐야
    화면에 그려지는 모양을 맞게 말할 수 있어서 고른 경우다.
    """
    band = [(100.0, 100.0), (500.0, 100.0), (500.0, 104.0), (100.0, 104.0)]

    assert math.isclose(outline_metric.thickness_uv(band), 2 * 1600 / 808 / MAP_SIZE)
    assert outline_metric.measure_side([band], None, None)["thin"] is True


def test_area_change_counts_added_cells_and_moved_cells():
    """넓이 차는 칸이 늘거나 준 비율, 어긋남은 위치가 달라진 칸까지 센다.

    넓이는 같은데 자리가 옮겨진 경우는 넓이 차만으로 못 잡아서,
    둘을 함께 둔 이유를 보여 주려고 고른 경우다.
    """
    outlined = np.zeros((20, 20), dtype=bool)
    outlined[0:10, 0:10] = True
    wider = np.zeros_like(outlined)
    wider[0:10, 0:12] = True
    moved = np.zeros_like(outlined)
    moved[0:10, 5:15] = True

    assert outline_metric.area_change(wider, outlined) == {"areaChange": 0.2, "mismatch": 0.2}
    assert outline_metric.area_change(moved, outlined) == {"areaChange": 0.0, "mismatch": 1.0}


def test_lip_outline_is_measured_from_what_the_service_sends():
    """서비스가 보내는 하위 단계로 잰다.

    입술 점 테두리를 그대로 찾았다면 테두리로 바꿔도 넓이가 거의 같고 얇지 않다.
    """
    rows, sub_step, _ = outline_metric.measure_step(
        "lip", ("lipsOuter",), {"lipsOuter": LipArea(mask=lip_area._lips())}, None
    )

    assert sub_step.status == "extracted"
    assert rows[0]["polygons"] == 1
    assert rows[0]["thin"] is False
    assert abs(rows[0]["areaChange"]) < 0.05


def test_cheek_not_found_is_still_measured_because_the_service_draws_it():
    """서비스는 한쪽 볼만 찾아도 뒤집어 양쪽에 그리므로, 못 찾은 볼도 테두리 값이 있어야 한다."""
    areas = {
        "leftCheek": BlushArea(mask=cheek_range("leftCheek")),
        "rightCheek": BlushArea(mask=None, reason="blushColorNotFound"),
    }

    rows, _, _ = outline_metric.measure_step("blush", ("leftCheek", "rightCheek"), areas, None)

    assert [row["polygons"] for row in rows] == [1, 1]
    assert all(row["areaChange"] is not None for row in rows)
