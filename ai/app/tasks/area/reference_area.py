"""BE가 넘긴 레퍼런스 사진으로 단계마다 가이드 영역을 만든다.

얼굴 점 찾기 → 사진 판정 → 가이드 영역 순서다. 사진 받기는 clients/frames.py가 먼저 한다.
"""

from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np

from app.clients.frames import frame_file_name
from app.core.tracing import set_output, traced
from app.schemas.guide import GuideInput
from app.schemas.guide_area import GuideArea
from app.schemas.guide_job import ReferenceFrames
from app.schemas.landmarks import FrameLandmarks
from app.schemas.manifest import Frame, Manifest, Step, VideoSource
from app.tasks.area.guide_area_builder import build_guide_area
from app.tasks.area.landmarks.face_finder import find_faces
from app.tasks.area.landmarks.frame_checker import check_frames
from app.tasks.area.landmarks.landmarks_builder import FaceFinder, build_landmarks
from app.tasks.area.landmarks.reference_input import ReferenceInput, read_frame_rgb


def reference_manifest(guide_input: GuideInput, frames: ReferenceFrames) -> Manifest:
    """요청의 가이드 입력과 사진 목록을 영역 분석이 읽는 매니페스트 모양으로 바꾼다.

    사진 위치는 작업 폴더 안의 frame_file_name이다.
    """
    source = frames.source
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
            for item in frames.items
        ],
    )


def build_reference_area(
    guide_input: GuideInput,
    frames: ReferenceFrames,
    folder: Path,
    *,
    on_landmarks: Callable[[], None] | None = None,
    on_area_step: Callable[[], None] | None = None,
    finder: FaceFinder = find_faces,
) -> GuideArea:
    """folder에 받아 둔 사진으로 가이드 영역을 만든다.

    CPU를 오래 쓰는 동기 작업이라 부르는 쪽이 스레드에서 돌린다.
    받지 못한 사진은 파일이 없어 얼굴 점 결과에서 error가 된다.
    on_landmarks는 사진 1장의 얼굴 점을 찾아 볼 때마다, on_area_step은 단계 하나의 영역을
    끝낼 때마다 부른다.
    finder는 시험할 때 가짜로 바꿔 끼우는 자리다.
    """
    manifest = reference_manifest(guide_input, frames)
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
        checked = check_frames(landmarks, load_row)
        set_output(span, dict(Counter(row.status for row in checked.frames)))
    with traced("build_guide_area", {"steps": len(guide_input.steps)}) as span:
        area = build_guide_area(
            guide_input.video_id, guide_input.steps, checked, load_row, on_step=on_area_step
        )
        statuses = Counter(sub.status for step in area.steps for sub in step.sub_steps)
        set_output(span, dict(statuses))
    return area
