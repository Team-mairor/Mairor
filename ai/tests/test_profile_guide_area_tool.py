import os
import threading

import numpy as np
import onnxruntime
import pytest

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, Point, Pose
from app.schemas.manifest import Manifest
from app.tasks.area import area_work, guide_area_builder, reference_area
from app.tasks.area.parts import area_preparation
from tools.profile_guide_area import (
    MB,
    Recorder,
    limit_cores,
    onnx_threads,
    patched,
    reference_frames,
    stage_report,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def nested_area(clock: FakeClock) -> Recorder:
    """영역 10초 = 자체 1 + 사진 읽기 3 + 립 6(자체 2 + 안쪽 지도 펴기 4)."""
    recorder = Recorder(clock)
    with recorder.lap("area"):
        clock.advance(1)
        with recorder.lap("readPhoto", key=7):
            clock.advance(3)
        with recorder.lap("lip"):
            clock.advance(2)
            with recorder.lap("flatten", key="face"):
                clock.advance(4)
    return recorder


def make_row(frame_index: int) -> FrameLandmarks:
    points = [Point(x=(i % 30) / 30, y=(i // 30) / 20, z=0.0) for i in range(478)]
    return FrameLandmarks(
        frame_index=frame_index,
        timestamp_ms=frame_index * 500,
        step_id=None,
        image_size=ImageSize(width=10, height=10),
        status="ok",
        face_count=1,
        face=Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0)),
    )


def test_inner_time_is_taken_out_of_outer_piece():
    recorder = nested_area(FakeClock())

    laps = recorder.laps
    assert laps[("area", "area")].seconds == 10
    assert laps[("area", "lip")].seconds == 6
    assert laps[("area", "lip")].self_seconds == 2
    assert laps[("area", "flatten")].self_seconds == 4
    assert sum(lap.self_seconds for (stage, _), lap in laps.items() if stage == "area") == 10
    assert recorder.current_stage is None


def test_same_piece_is_split_by_stage_and_counts_distinct_targets():
    recorder = Recorder(FakeClock())
    with recorder.lap("landmarks"):
        for index in (1, 2, 3):
            with recorder.lap("readPhoto", key=index):
                pass
    with recorder.lap("area"):
        for index in (1, 1, 2):
            with recorder.lap("readPhoto", key=index):
                pass

    assert recorder.laps[("landmarks", "readPhoto")].calls == 3
    assert recorder.laps[("area", "readPhoto")].calls == 3
    assert len(recorder.laps[("area", "readPhoto")].distinct) == 2


def test_stage_report_pieces_add_up_to_stage_time():
    recorder = nested_area(FakeClock())

    [area] = stage_report(recorder, {"area": 300 * MB})

    assert area["stage"] == "area"
    assert area["peakMemoryMb"] == 300
    assert [piece["name"] for piece in area["pieces"]] == ["flatten", "readPhoto", "lip", "other"]
    assert area["pieces"][-1]["selfSeconds"] == 1
    assert sum(piece["selfSeconds"] for piece in area["pieces"]) == area["seconds"]


def test_reference_frames_point_to_photo_server_like_be_request():
    manifest = Manifest.model_validate(
        {
            "videoId": "test_01",
            "source": {"width": 1920, "height": 1080, "fps": 60, "durationSeconds": 10},
            "steps": [
                {"stepId": "s1", "order": 1, "startSeconds": 1, "endSeconds": 5, "makeup": "lip"}
            ],
            "frames": [
                {
                    "frameIndex": 0,
                    "timestampMs": 0,
                    "stepId": None,
                    "path": "frames/000000.jpg",
                    "width": 1920,
                    "height": 1080,
                },
                {
                    "frameIndex": 90,
                    "timestampMs": 1500,
                    "stepId": "s1",
                    "path": "frames/000090.jpg",
                    "width": 1920,
                    "height": 1080,
                },
            ],
        }
    )

    frames = reference_frames(manifest, "http://127.0.0.1:8123")

    assert frames.source.fps == 60
    assert [str(item.url) for item in frames.items] == [
        "http://127.0.0.1:8123/frames/000000.jpg",
        "http://127.0.0.1:8123/frames/000090.jpg",
    ]
    assert [(item.frame_index, item.step_id) for item in frames.items] == [(0, None), (90, "s1")]


def test_patched_records_service_calls_and_puts_functions_back():
    places = [
        (area_work, "download_frames"),
        (reference_area, "build_landmarks"),
        (reference_area, "read_frame_rgb"),
        (reference_area, "remember_by_frame"),
        (area_preparation, "flatten"),
        (guide_area_builder, "find_lip_area"),
        (guide_area_builder, "points_to_anchors"),
    ]
    originals = [getattr(module, name) for module, name in places]
    recorder = Recorder()
    photo = np.zeros((10, 10, 3), dtype=np.uint8)

    with patched(recorder):
        assert all(
            getattr(module, name) is not original
            for (module, name), original in zip(places, originals, strict=True)
        )
        with recorder.lap("area"):
            area_preparation.rows_to_known_map([make_row(1), make_row(2)], lambda row: photo)

    assert all(
        getattr(module, name) is original
        for (module, name), original in zip(places, originals, strict=True)
    )
    flatten = recorder.laps[("area", "flatten")]
    assert flatten.calls == 2
    assert len(flatten.distinct) == 2


def test_limit_cores_without_count_keeps_every_core_and_rejects_too_many():
    total = os.cpu_count() or 1

    assert limit_cores(0) == list(range(total))
    with pytest.raises(ValueError):
        limit_cores(total + 1)


def test_onnx_threads_set_worker_count_only_while_inside(monkeypatch):
    """서버처럼 잴 때만 가림 찾기 모델 일꾼 수를 정하고, 끝나면 원래 모델 열기로 돌아간다."""
    opened = []

    def fake_session(path, sess_options=None, **kwargs):
        opened.append(sess_options)
        return path

    monkeypatch.setattr(onnxruntime, "InferenceSession", fake_session)

    with onnx_threads(1):
        onnxruntime.InferenceSession("model.onnx", providers=["CPUExecutionProvider"])
    onnxruntime.InferenceSession("model.onnx")
    with onnx_threads(None):
        onnxruntime.InferenceSession("model.onnx")

    inside, after, untouched = opened
    assert (inside.intra_op_num_threads, inside.inter_op_num_threads) == (1, 1)
    assert after is None
    assert untouched is None


def test_laps_from_line_threads_belong_to_the_open_stage():
    """영역을 두 줄로 만들 때 줄마다 다른 스레드에서 잰 구간도 영역 만들기에 들어간다."""
    recorder = Recorder(FakeClock())

    def line() -> None:
        with recorder.lap("areaLine"):
            with recorder.lap("flatten", key=1):
                pass

    with recorder.lap("area"):
        threads = [threading.Thread(target=line) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert recorder.laps[("area", "areaLine")].calls == 2
    assert recorder.laps[("area", "flatten")].calls == 2
    assert ("areaLine", "areaLine") not in recorder.laps
    assert recorder.current_stage is None
