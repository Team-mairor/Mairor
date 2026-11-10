from bisect import bisect_left, bisect_right
from math import degrees
from statistics import median

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import Face, FrameLandmarks, LandmarksResult
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.landmarks_builder import face_width_px

MIN_FACE_WIDTH_PX = 256
MAX_TURN_DEG = 20
MAX_FACE_COUNT = 1
FACE_RATIO_RANGE = (0.8, 1.2)
RATIO_WINDOW_MS = 1000
DIGITS = 2


def check_frames(result: LandmarksResult) -> LandmarksResult:
    """얼굴이 있는 사진마다 부위 분석에 써도 되는지 판정한 결과를 돌려준다.

    사진 한 장 전체에 해당해서 어느 부위에도 못 쓰는 사진만 rejected로 바꾸고 이유를 붙인다.
    얼굴 가로가 MIN_FACE_WIDTH_PX보다 작으면 faceTooSmall, 좌우·위아래 각도가 MAX_TURN_DEG를
    넘으면 faceTurned, 찾은 얼굴이 MAX_FACE_COUNT개보다 많으면 multipleFaces다.
    여러 명이 나오면 가장 큰 얼굴이 사진마다 다른 사람일 수 있어서다.
    얼굴 크기 비율(faceWidthRatio)이 FACE_RATIO_RANGE 밖이면 faceSizeJump다.
    비율은 앞뒤 RATIO_WINDOW_MS 안 사진의 얼굴 가로 중앙값과 견준다.
    편집으로 확대한 구간은 그 안에서 견주어 살리고,
    혼자 튀는 사진(손이 가린 얼굴을 잘못 잡은 사진 등)만 드러낸다.
    앞뒤에 얼굴 있는 사진이 없으면 result 전체 중앙값과 견준다.
    서비스는 영역에 쓰는 사진만 받으므로(reference_area.needed_frames) 이때는 받은 사진 전체다.
    부위가 화면 밖인지는 부위마다 다르게 쓰이므로 탈락시키지 않고, 부위마다 화면 밖 점 수를
    outside_count_name(부위) 값으로 적는다. 각 부위 분석이 사진을 고를 때 자기 부위 값을 본다.
    흐린 사진은 가린 칸과 얼굴 지도가 있어야 재므로 부위 분석(area_preparation.drop_blurry)이 뺀다.
    부위별 점 번호는 점 번호부 region_points.REGION_POINTS에서 가져온다.
    """
    checked = [_check(row) if _has_face(row) else row for row in result.frames]
    sized = sorted(
        (row.timestamp_ms, row.measures["faceWidthPx"])
        for row in checked
        if "faceWidthPx" in row.measures
    )
    if sized:
        times = [time for time, _ in sized]
        widths = [width for _, width in sized]
        checked = [_with_ratio(row, times, widths) for row in checked]
    return result.model_copy(update={"frames": checked})


def outside_count_name(region: RegionName) -> str:
    """부위의 화면 밖 점 수를 적는 measures 이름. 예: leftCheek → leftCheekOutsideCount."""
    return f"{region}OutsideCount"


def _has_face(row: FrameLandmarks) -> bool:
    return row.face is not None and row.status in ("ok", "rejected")


def _check(row: FrameLandmarks) -> FrameLandmarks:
    face = row.face
    measures = {
        "faceWidthPx": face_width_px(face, row.image_size.width),
        "yawDeg": degrees(face.pose.yaw),
        "pitchDeg": degrees(face.pose.pitch),
        **{
            outside_count_name(region): float(_outside_count(face, points))
            for region, points in REGION_POINTS.items()
        },
    }
    reasons = _reasons(measures, row.face_count)
    rounded = {name: round(value, DIGITS) for name, value in measures.items()}
    return row.model_copy(
        update={"status": "rejected" if reasons else "ok", "reasons": reasons, "measures": rounded}
    )


def _reasons(measures: dict[str, float], face_count: int) -> list[str]:
    reasons = []
    if measures["faceWidthPx"] < MIN_FACE_WIDTH_PX:
        reasons.append("faceTooSmall")
    if max(abs(measures["yawDeg"]), abs(measures["pitchDeg"])) > MAX_TURN_DEG:
        reasons.append("faceTurned")
    if face_count > MAX_FACE_COUNT:
        reasons.append("multipleFaces")
    return reasons


def _outside_count(face: Face, indices: tuple[int, ...]) -> int:
    points = [face.landmarks[i] for i in indices]
    return sum(1 for p in points if not (0 <= p.x <= 1 and 0 <= p.y <= 1))


def _with_ratio(row: FrameLandmarks, times: list[int], widths: list[float]) -> FrameLandmarks:
    """얼굴 크기 비율을 적고, FACE_RATIO_RANGE 밖이면 faceSizeJump로 rejected를 만든다.

    times·widths는 얼굴이 있는 사진의 시각(ms)과 얼굴 가로이고 시각 순으로 정렬돼 있다.
    """
    if "faceWidthPx" not in row.measures:
        return row
    low = bisect_left(times, row.timestamp_ms - RATIO_WINDOW_MS)
    high = bisect_right(times, row.timestamp_ms + RATIO_WINDOW_MS)
    near = [
        width
        for time, width in zip(times[low:high], widths[low:high], strict=True)
        if time != row.timestamp_ms
    ]
    middle = median(near) if near else median(widths)
    ratio = round(row.measures["faceWidthPx"] / middle, DIGITS)
    update = {"measures": {**row.measures, "faceWidthRatio": ratio}}
    lowest, highest = FACE_RATIO_RANGE
    if not lowest <= ratio <= highest:
        update |= {"status": "rejected", "reasons": [*row.reasons, "faceSizeJump"]}
    return row.model_copy(update=update)
