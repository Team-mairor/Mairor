"""BE가 넘긴 레퍼런스 사진으로 단계마다 가이드 영역을 만든다.

얼굴 점 찾기 → 사진 판정 → 가이드 영역 순서다. 사진 받기는 clients/frames.py가 먼저 한다.
가이드 영역은 사진마다 손·붓·자막 같은 것이 가린 칸을 빼고 만든다.
영역에 쓰는 사진은 분석하는 단계의 직전·직후 창 근처뿐이라, needed_frames로 그 사진만 골라
받고 얼굴 점을 찾는다.
단계별 영역은 split_steps로 단계를 여러 줄로 나눠 동시에 만들 수 있다.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path

import numpy as np

from app.clients.frames import frame_file_name
from app.core.tracing import set_output, traced
from app.schemas.guide import GuideInput, GuideInputStep
from app.schemas.guide_area import GuideArea
from app.schemas.guide_job import FrameSource, ReferenceFrame
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.schemas.manifest import Frame, Makeup, Manifest, Step, VideoSource
from app.tasks.area.guide_area_builder import build_guide_area
from app.tasks.area.landmarks.face_finder import find_faces
from app.tasks.area.landmarks.frame_checker import RATIO_WINDOW_MS, check_frames
from app.tasks.area.landmarks.landmarks_builder import FaceFinder, build_landmarks
from app.tasks.area.landmarks.occlusion import OcclusionFinder, remember_by_frame
from app.tasks.area.landmarks.occlusion_finder import find_occlusion
from app.tasks.area.landmarks.reference_input import ReferenceInput, read_frame_rgb
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import RememberedPhotos, step_bounds

OCCLUSION_KEEP = 64
FACE_MAP_KEEP = 64
PART_WINDOWS: dict[Makeup, tuple[int | None, int]] = {
    "lip": (lip_area.BEFORE_WINDOW_MS, lip_area.AFTER_WINDOW_MS),
    "blush": (blush_area.BEFORE_WINDOW_MS, blush_area.AFTER_WINDOW_MS),
    "brow": (brow_area.BEFORE_WINDOW_MS, brow_area.AFTER_WINDOW_MS),
    "eyeshadow": (eyeshadow_area.BEFORE_WINDOW_MS, eyeshadow_area.AFTER_WINDOW_MS),
    "eyeliner": (eyeliner_area.BEFORE_WINDOW_MS, eyeliner_area.AFTER_WINDOW_MS),
}


def photo_ranges(steps: Sequence[GuideInputStep]) -> list[tuple[int, int]]:
    """영역 만들기에 필요한 사진의 시각 구간 (시작 ms, 끝 ms) 목록이다. 양 끝을 넣는다.

    부위 분석은 분석하는 단계(PART_WINDOWS에 있는 부위)의 직전 창과 직후 창 사진만 쓴다.
    PART_WINDOWS는 (직전 창, 직후 창) 길이(ms)이고 각 부위 분석의 창 값을 그대로 가져온다.
    직전 창이 None인 부위는 바른 뒤 사진만 쓴다.
    사진 판정은 얼굴 크기를 앞뒤 RATIO_WINDOW_MS 안 사진과 견주므로 창 양쪽에 그만큼 더한다.
    그래서 창 안 사진의 판정은 모든 사진으로 판정할 때와 같다.
    단계 시각은 build_guide_area처럼 초 × 1000을 반올림한 ms다.
    """
    return [
        (low - RATIO_WINDOW_MS, high + RATIO_WINDOW_MS)
        for step in steps
        for low, high in step_windows(step)
    ]


def step_windows(step: GuideInputStep) -> list[tuple[int, int]]:
    """부위 분석이 사진을 고르는 직전·직후 창 (시작 ms, 끝 ms). 분석하지 않는 단계는 빈 목록이다."""
    if step.makeup not in PART_WINDOWS:
        return []
    before, after = PART_WINDOWS[step.makeup]
    start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
    windows = [(end, end + after)]
    if before is not None:
        windows.insert(0, (start - before, start))
    return windows


def split_steps(
    steps: Sequence[GuideInputStep], result: LandmarksResult, lines: int
) -> list[list[GuideInputStep]]:
    """단계를 lines줄로 나눠, 줄마다 동시에 영역을 만들 수 있게 한다. 빈 줄은 뺀다.

    아이라인은 앞 아이라인 단계에서 안내한 칸을 이어받으므로(build_guide_area) 모두 첫 줄에 둔다.
    다른 분석하는 단계는 창 안 사진이 많은 것부터, 그때까지 사진 수가 가장 적은 줄에 넣는다.
    사진 수는 영역 만들기 시간과 거의 비례한다.
    분석하지 않는 단계는 사진을 쓰지 않아 마지막 줄에 둔다.
    """
    if lines <= 1:
        return [list(steps)]
    times = [row.timestamp_ms for row in result.frames]

    def photos(step: GuideInputStep) -> int:
        windows = step_windows(step)
        return sum(1 for time in times if any(low < time <= high for low, high in windows))

    groups: list[list[GuideInputStep]] = [[] for _ in range(lines)]
    loads = [0] * lines
    for step in steps:
        if step.makeup == "eyeliner":
            groups[0].append(step)
            loads[0] += photos(step)
    analyzed = [s for s in steps if s.makeup in PART_WINDOWS and s.makeup != "eyeliner"]
    for step in sorted(analyzed, key=lambda s: (-photos(s), s.order)):
        lightest = loads.index(min(loads))
        groups[lightest].append(step)
        loads[lightest] += photos(step)
    groups[-1] += [s for s in steps if s.makeup not in PART_WINDOWS]
    return [group for group in groups if group]


def needed_frames(
    steps: Sequence[GuideInputStep], items: Sequence[ReferenceFrame]
) -> list[ReferenceFrame]:
    """items 중 영역 만들기에 필요한 사진(photo_ranges 안)만 순서대로 남긴다. 0장일 수 있다.

    분석하는 단계가 없거나 창 근처에 사진이 없으면 빈 목록이다.
    그러면 얼굴 점을 찾을 사진이 없어, 분석하는 단계는 쓸 사진 없음(noUsableFrame)이 된다.
    """
    ranges = photo_ranges(steps)
    return [item for item in items if any(low <= item.timestamp_ms <= high for low, high in ranges)]


def reference_manifest(
    guide_input: GuideInput, source: FrameSource, items: Sequence[ReferenceFrame]
) -> Manifest:
    """요청의 가이드 입력과 사진 목록을 영역 분석이 읽는 매니페스트 모양으로 바꾼다.

    source는 요청 사진 목록의 영상 정보, items는 그중 받은 사진이다.
    사진 위치는 작업 폴더 안의 frame_file_name이다.
    """
    return Manifest(
        video_id=guide_input.video_id,
        source=VideoSource(
            width=source.width,
            height=source.height,
            fps=source.fps,
            duration_seconds=guide_input.duration_seconds,
        ),
        steps=[
            Step(
                step_id=step.step_id,
                order=step.order,
                start_seconds=step.start_seconds,
                end_seconds=step.end_seconds,
                makeup=step.makeup,
            )
            for step in guide_input.steps
        ],
        frames=[
            Frame(
                frame_index=item.frame_index,
                timestamp_ms=item.timestamp_ms,
                step_id=item.step_id,
                path=frame_file_name(item.frame_index),
                width=item.width,
                height=item.height,
            )
            for item in items
        ],
    )


def build_reference_area(
    guide_input: GuideInput,
    source: FrameSource,
    items: Sequence[ReferenceFrame],
    folder: Path,
    *,
    on_landmarks: Callable[[], None] | None = None,
    on_area_step: Callable[[], None] | None = None,
    finder: FaceFinder = find_faces,
    occlusion: OcclusionFinder = find_occlusion,
    lines: int = 1,
) -> GuideArea:
    """folder에 받아 둔 items 사진으로 가이드 영역을 만든다.

    source는 요청 사진 목록의 영상 정보이고, items는 needed_frames로 고른 사진이다(0장일 수 있음).
    CPU를 오래 쓰는 동기 작업이라 부르는 쪽이 스레드에서 돌린다.
    받지 못한 사진은 파일이 없어 얼굴 점 결과에서 error가 된다.
    on_landmarks는 사진 1장의 얼굴 점을 찾아 볼 때마다, on_area_step은 단계 하나의 영역을
    끝낼 때마다 부른다.
    finder·occlusion은 시험할 때 가짜로 바꿔 끼우는 자리다.
    occlusion은 작업마다 remember_by_frame으로 감싸, 좌우 짝 부위가 같은 사진을
    두 번 찾지 않게 한다. 직전·직후 창 사진이 한 단계에 수십 장이라
    최근 OCCLUSION_KEEP장을 기억한다.
    같은 까닭으로 사진을 얼굴 지도에 편 결과도 RememberedPhotos로 최근 FACE_MAP_KEEP장을 기억해,
    좌우 짝 부위가 같은 사진을 다시 읽고 펴지 않게 한다.
    lines는 단계별 영역을 나눠 동시에 만들 줄 수다(split_steps). 줄마다 기억을 따로 두고,
    끝나면 단계 순서대로 합친다. 1이면 한 줄로 차례로 만든다.
    """
    manifest = reference_manifest(guide_input, source, items)
    reference = ReferenceInput(folder, manifest)
    by_index = {frame.frame_index: frame for frame in manifest.frames}

    def load_frame(frame: Frame) -> np.ndarray:
        try:
            return read_frame_rgb(reference, frame)
        finally:
            if on_landmarks is not None:
                on_landmarks()

    def load_row(row: FrameLandmarks) -> np.ndarray:
        return read_frame_rgb(reference, by_index[row.frame_index])

    with traced("face_landmarks", {"frames": len(manifest.frames)}) as span:
        landmarks = build_landmarks(manifest, load_frame, finder)
        set_output(span, dict(Counter(row.status for row in landmarks.frames)))
    with traced("check_frames", {"frames": len(landmarks.frames)}) as span:
        checked = check_frames(landmarks)
        set_output(
            span,
            {
                "status": dict(Counter(row.status for row in checked.frames)),
                "reasons": dict(
                    Counter(reason for row in checked.frames for reason in row.reasons)
                ),
            },
        )
    with traced("build_guide_area", {"steps": len(guide_input.steps), "lines": lines}) as span:
        area = build_area_in_lines(
            guide_input.video_id,
            guide_input.steps,
            checked,
            load_row,
            occlusion,
            on_area_step,
            lines,
        )
        statuses = Counter(sub.status for step in area.steps for sub in step.sub_steps)
        set_output(span, dict(statuses))
    return area


def build_area_in_lines(
    video_id: str,
    steps: Sequence[GuideInputStep],
    checked: LandmarksResult,
    load_row: Callable[[FrameLandmarks], np.ndarray],
    occlusion: OcclusionFinder,
    on_step: Callable[[], None] | None,
    lines: int,
) -> GuideArea:
    """단계를 split_steps로 나눈 줄마다 동시에 build_guide_area를 돌리고 단계 순서대로 합친다.

    줄마다 지도 꾸러미(RememberedPhotos)와 가림 기억(remember_by_frame)을 따로 둔다.
    같은 기억을 두 줄이 같이 넣고 빼면 꼬일 수 있어서다. 줄이 하나면 그 자리에서 바로 만든다.
    줄마다 지금 문맥을 복사해 넘겨, 단계 기록(area_step)이 이 작업의 기록 밑에 붙게 한다.
    단계마다 앞뒤 단계 시각(step_bounds)은 나누기 전 전체 단계로 정해 넘긴다.
    줄에 든 단계만으로 정하면 다른 줄에 간 이웃 단계를 못 봐서다.
    """
    bounds = step_bounds(steps)

    def build(group: list[GuideInputStep]) -> GuideArea:
        return build_guide_area(
            video_id,
            group,
            checked,
            RememberedPhotos(load_row, FACE_MAP_KEEP),
            on_step=on_step,
            occlusion=remember_by_frame(occlusion, OCCLUSION_KEEP),
            bounds=bounds,
        )

    groups = split_steps(steps, checked, lines)
    if len(groups) == 1:
        return build(groups[0])
    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        futures = [pool.submit(copy_context().run, build, group) for group in groups]
        areas = [future.result() for future in futures]
    merged = sorted((step for area in areas for step in area.steps), key=lambda step: step.order)
    return GuideArea(video_id=video_id, mesh_version=areas[0].mesh_version, steps=merged)
