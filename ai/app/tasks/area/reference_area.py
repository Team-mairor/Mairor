"""BE가 넘긴 레퍼런스 사진으로 단계마다 가이드 영역을 만든다.

얼굴 점 찾기 → 사진 판정 → 가이드 영역 순서다. 사진 받기는 clients/frames.py가 먼저 한다.
가이드 영역은 사진마다 손·붓·자막 같은 것이 가린 칸을 빼고 만든다.
영역에 쓰는 사진은 분석하는 단계의 직전·직후 창 근처뿐이라, needed_frames로 그 사진만 골라
받고 얼굴 점을 찾는다.
단계별 영역은 step_bundles로 단계를 묶음으로 나눠 여러 줄이 동시에 만들 수 있다.
"""

import threading
from collections import Counter, deque
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
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
from app.tasks.area.direction_finder import middle_windows
from app.tasks.area.guide_area_builder import ORDERED_MAKEUPS, build_guide_area
from app.tasks.area.landmarks.face_finder import find_faces
from app.tasks.area.landmarks.frame_checker import RATIO_WINDOW_MS, check_frames
from app.tasks.area.landmarks.landmarks_builder import FaceFinder, build_landmarks
from app.tasks.area.landmarks.occlusion import OcclusionFinder, remember_by_frame
from app.tasks.area.landmarks.occlusion_finder import find_occlusion
from app.tasks.area.landmarks.reference_input import ReferenceInput, read_frame_rgb
from app.tasks.area.parts import (
    blush_area,
    brow_area,
    contour_area,
    eyeliner_area,
    eyeshadow_area,
    lip_area,
)
from app.tasks.area.parts.area_preparation import RememberedPhotos, step_bounds

OCCLUSION_KEEP = 128
FACE_MAP_KEEP = 128
WARM_AHEAD_STEPS = 1
WARM_MIN_LINES = 4
DIRECTION_PHOTOS = False
PART_WINDOWS: dict[Makeup, tuple[int | None, int]] = {
    "lip": (lip_area.BEFORE_WINDOW_MS, lip_area.AFTER_WINDOW_MS),
    "blush": (blush_area.BEFORE_WINDOW_MS, blush_area.AFTER_WINDOW_MS),
    "brow": (brow_area.BEFORE_WINDOW_MS, brow_area.AFTER_WINDOW_MS),
    "eyeshadow": (eyeshadow_area.BEFORE_WINDOW_MS, eyeshadow_area.AFTER_WINDOW_MS),
    "eyeliner": (eyeliner_area.BEFORE_WINDOW_MS, eyeliner_area.AFTER_WINDOW_MS),
    "contour": (contour_area.BEFORE_WINDOW_MS, contour_area.AFTER_WINDOW_MS),
}


def photo_ranges(steps: Sequence[GuideInputStep]) -> list[tuple[int, int]]:
    """영역 만들기에 필요한 사진의 시각 구간 (시작 ms, 끝 ms) 목록이다. 양 끝을 넣는다.

    부위 분석은 분석하는 단계(PART_WINDOWS에 있는 부위)의 직전 창과 직후 창 사진만 쓴다.
    PART_WINDOWS는 (직전 창, 직후 창) 길이(ms)이고 각 부위 분석의 창 값을 그대로 가져온다.
    직전 창이 None인 부위는 바른 뒤 사진만 쓴다.
    사진 판정은 얼굴 크기를 앞뒤 RATIO_WINDOW_MS 안 사진과 견주므로 창 양쪽에 그만큼 더한다.
    그래서 창 안 사진의 판정은 모든 사진으로 판정할 때와 같다.
    단계 시각은 build_guide_area처럼 초 × 1000을 반올림한 ms다.
    DIRECTION_PHOTOS가 참이면 바른 방향 찾기가 쓰는 단계 동안의 구간(direction_windows)도 넣는다.
    지금은 거짓이다. 처리기가 단계 동안의 사진을 뽑지 않고, 받으면 방향 찾기만큼 처리 시간이
    늘기 때문이다. 거짓이면 단계 동안의 사진을 받지 않아 화살표 없이 영역만 나간다.
    """
    return [
        (low - RATIO_WINDOW_MS, high + RATIO_WINDOW_MS)
        for step in steps
        for low, high in [
            *step_windows(step),
            *(direction_windows(step) if DIRECTION_PHOTOS else []),
        ]
    ]


def direction_windows(step: GuideInputStep) -> list[tuple[int, int]]:
    """바른 방향 찾기가 단계 동안 사진을 고르는 구간. 분석하지 않는 단계는 빈 목록이다."""
    if step.makeup not in PART_WINDOWS:
        return []
    return middle_windows(round(step.start_seconds * 1000), round(step.end_seconds * 1000))


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


def step_bundles(
    steps: Sequence[GuideInputStep], result: LandmarksResult
) -> list[list[GuideInputStep]]:
    """단계를 따로 만들어도 되는 묶음으로 나눠, 창 안 사진이 많은 묶음부터 돌려준다. 빈 묶음은 없다.

    단계 순서대로 앞 단계를 이어받는 부위(ORDERED_MAKEUPS)는 부위마다 한 묶음이다.
    아이라인은 앞 아이라인 단계에서 안내한 칸을 빼고, 눈썹은 못 찾으면 앞 눈썹 단계 영역을
    그대로 쓴다(build_guide_area). 묶음끼리는 서로의 결과를 모르므로 갈라지면 이어받지 못한다.
    아이라인과 눈썹은 서로의 결과를 쓰지 않아 두 묶음으로 둔다.
    다른 분석하는 단계는 하나가 한 묶음이다.
    사진 수는 영역 만들기 시간과 거의 비례해서, 오래 걸릴 묶음이 앞에 온다.
    분석하지 않는 단계는 사진을 쓰지 않아 한 묶음으로 맨 뒤에 둔다.
    """
    times = [row.timestamp_ms for row in result.frames]

    def photos(step: GuideInputStep) -> int:
        windows = step_windows(step)
        return sum(1 for time in times if any(low < time <= high for low, high in windows))

    chains = [[s for s in steps if s.makeup == makeup] for makeup in ORDERED_MAKEUPS]
    singles = [[s] for s in steps if s.makeup in PART_WINDOWS and s.makeup not in ORDERED_MAKEUPS]
    weighed = [(sum(photos(s) for s in bundle), bundle) for bundle in chains + singles if bundle]
    weighed.sort(key=lambda item: (-item[0], item[1][0].order))
    rest = [s for s in steps if s.makeup not in PART_WINDOWS]
    return [bundle for _, bundle in weighed] + ([rest] if rest else [])


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
    lines는 동시에 돌릴 줄 수다. 얼굴 점 찾기는 그만큼의 스레드가 사진을 나눠 맡고(build_landmarks),
    단계별 영역도 그만큼의 줄이 나눠 만든다(build_area_in_lines). 영역은 줄마다 기억을 따로 두고,
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
        landmarks = build_landmarks(manifest, load_frame, finder, workers=lines)
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


class LineWork:
    """줄들이 나눠 가질 일감. 묶음(step_bundles)과, 도는 중인 이어받는 묶음의 사진 미리 펴기다.

    이어받는 묶음(아이라인·눈썹)은 한 줄이 단계 순서대로 만들어야 해서 다른 줄이 대신 못 한다.
    그런데 그 시간의 대부분은 사진을 읽어 가림을 찾고 얼굴 지도에 펴는 일이고, 이 일은 단계 순서와
    상관없다. 그래서 다른 줄이 그 묶음의 사진을 미리 펴 둔다(지도 꾸러미를 줄들이 같이 쓴다).
    미리 펴기는 묶음이 지금 만드는 단계와 그다음 WARM_AHEAD_STEPS개 단계까지만 한다.
    너무 앞서 펴면 꾸러미가 기억하는 장수를 넘어, 쓰기 전에 밀려난다.
    줄은 미리 펼 사진이 있으면 그것부터, 없으면 남은 묶음 중 맨 앞을 가져간다.
    이어받는 묶음이 가장 오래 걸려서, 그 묶음을 돕는 일이 먼저다.
    warm이 False면 미리 펴기 없이 묶음만 나눠 준다.
    """

    def __init__(
        self,
        bundles: Sequence[list[GuideInputStep]],
        checked: LandmarksResult,
        warm: bool = True,
    ) -> None:
        self._turn = threading.Condition()
        self._bundles = deque(enumerate(bundles))
        self._rows = {
            index: [_window_rows(step, checked) for step in bundle]
            for index, bundle in enumerate(bundles)
            if warm and len(bundle) > 1
        }
        self._running: dict[int, int] = {}
        self._stopped = False

    def take(self) -> tuple[int, list[GuideInputStep]] | FrameLandmarks | None:
        """다음 일. 사진이면 미리 펼 사진, (번호, 묶음)이면 만들 묶음, None이면 할 일이 없다.

        남은 묶음은 없는데 다른 줄이 이어받는 묶음을 만드는 중이면, 그 묶음이 다음 단계로 넘어가
        미리 펼 사진이 생기거나 끝날 때까지 기다린다.
        """
        with self._turn:
            while not self._stopped:
                row = self._next_row()
                if row is not None:
                    return row
                if self._bundles:
                    index, bundle = self._bundles.popleft()
                    self._running[index] = 0
                    return index, bundle
                if not any(self._ahead(index) for index in self._running):
                    return None
                self._turn.wait()
            return None

    def step_done(self, index: int) -> None:
        """index번 묶음이 단계 하나를 끝냈다. 미리 펴기를 한 단계 앞으로 옮긴다."""
        with self._turn:
            self._running[index] += 1
            self._turn.notify_all()

    def bundle_done(self, index: int) -> None:
        """index번 묶음이 끝났다(오류로 끝나도 부른다). 그 묶음의 미리 펴기를 그만둔다."""
        with self._turn:
            self._running.pop(index, None)
            self._rows.pop(index, None)
            self._turn.notify_all()

    def stop(self) -> None:
        """오류가 났거나 취소됐다. 기다리는 줄을 깨워 더 가져가지 않게 한다."""
        with self._turn:
            self._stopped = True
            self._turn.notify_all()

    def _ahead(self, index: int) -> list[list[FrameLandmarks]]:
        """index번 묶음에서 아직 안 끝난 단계들의 남은 사진 목록."""
        return [rows for rows in self._rows.get(index, [])[self._running[index] :] if rows]

    def _next_row(self) -> FrameLandmarks | None:
        for index, done in self._running.items():
            for rows in self._rows.get(index, [])[done : done + 1 + WARM_AHEAD_STEPS]:
                if rows:
                    return rows.pop()
        return None


def _window_rows(step: GuideInputStep, checked: LandmarksResult) -> list[FrameLandmarks]:
    """단계의 직전·직후 창 안에서 판정을 통과한 사진. 시간 순이다."""
    windows = step_windows(step)
    return [
        row
        for row in checked.frames
        if row.status == "ok" and any(low < row.timestamp_ms <= high for low, high in windows)
    ]


def build_area_in_lines(
    video_id: str,
    steps: Sequence[GuideInputStep],
    checked: LandmarksResult,
    load_row: Callable[[FrameLandmarks], np.ndarray],
    occlusion: OcclusionFinder,
    on_step: Callable[[], None] | None,
    lines: int,
) -> GuideArea:
    """단계를 step_bundles 묶음으로 나눠 lines줄이 동시에 만들고 단계 순서대로 합친다.

    줄은 비는 대로 LineWork에서 다음 일을 가져간다. 묶음을 줄마다 미리 정해 두면 사진 수로 어림한
    시간이 틀릴 때 한 줄만 길어져, 줄을 늘려도 그 줄이 끝날 때까지 기다린다.
    지도 꾸러미(RememberedPhotos)는 줄들이 같이 쓴다. 그래야 다른 줄이 미리 편 사진을 이어받는
    묶음이 쓰고, 이웃 단계가 다른 줄에 가도 겹치는 사진을 한 번만 편다.
    기억하는 장수는 줄마다 FACE_MAP_KEEP장씩이다.
    가림 기억(remember_by_frame)은 같이 넣고 빼면 꼬일 수 있어 줄마다 따로 둔다.
    줄이 하나면 묶음으로 나누지 않고 그 자리에서 단계 순서대로 만든다.
    줄마다 지금 문맥을 복사해 넘겨, 단계 기록(area_step)이 이 작업의 기록 밑에 붙게 한다.
    단계마다 앞뒤 단계 시각(step_bounds)은 나누기 전 전체 단계로 정해 넘긴다.
    묶음에 든 단계만으로 정하면 다른 묶음에 간 이웃 단계를 못 봐서다.
    미리 펴기는 줄이 WARM_MIN_LINES개 이상일 때만 한다. 줄이 적으면 묶음만으로 줄이 다 차서
    빨라지지 않고, 미리 편 사진을 들고 있느라 메모리만 더 쓴다.
    미리 펴다 난 오류는 버린다. 그 사진을 쓰는 단계가 다시 펴다 같은 오류를 만나 그 단계만 실패한다.
    """
    bounds = step_bounds(steps)
    photos = RememberedPhotos(load_row, FACE_MAP_KEEP * max(1, lines))
    memory = threading.local()

    def own_occlusion() -> OcclusionFinder:
        if not hasattr(memory, "occlusion"):
            memory.occlusion = remember_by_frame(occlusion, OCCLUSION_KEEP)
        return memory.occlusion

    def build(group: list[GuideInputStep], tick: Callable[[], None] | None) -> GuideArea:
        return build_guide_area(
            video_id,
            group,
            checked,
            photos,
            on_step=tick,
            occlusion=own_occlusion(),
            bounds=bounds,
        )

    if lines <= 1:
        return build(list(steps), on_step)
    work = LineWork(step_bundles(steps, checked), checked, warm=lines >= WARM_MIN_LINES)

    def line() -> list[GuideArea]:
        areas = []
        try:
            while (job := work.take()) is not None:
                if isinstance(job, FrameLandmarks):
                    with suppress(Exception):
                        photos.face_maps(job, own_occlusion())
                    continue
                index, bundle = job

                def tick(index: int = index) -> None:
                    work.step_done(index)
                    if on_step is not None:
                        on_step()

                try:
                    areas.append(build(bundle, tick))
                finally:
                    work.bundle_done(index)
        except BaseException:
            work.stop()
            raise
        return areas

    with ThreadPoolExecutor(max_workers=lines) as pool:
        futures = [pool.submit(copy_context().run, line) for _ in range(lines)]
        areas = [area for future in futures for area in future.result()]
    merged = sorted((step for area in areas for step in area.steps), key=lambda step: step.order)
    return GuideArea(video_id=video_id, mesh_version=areas[0].mesh_version, steps=merged)
