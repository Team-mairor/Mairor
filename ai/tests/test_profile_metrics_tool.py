import sys
from dataclasses import dataclass
from types import ModuleType

import numpy as np

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, Point, Pose
from app.tasks.area.parts import area_preparation
from tools.profile_guide_area import MemorySampler, Recorder
from tools.profile_metrics import label, patched, power_status, profile_report, run_tool


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass(frozen=True)
class FakePart:
    name: str


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


def fake_tool() -> ModuleType:
    """지표 도구처럼 사진 읽기·가림 표·부위 재기 함수를 이름 자리에 둔 가짜 도구.

    measure_part는 진짜 도구처럼 서비스 rows_to_known_map을 불러,
    area_preparation 안의 지도 펴기까지 재는지 볼 수 있게 한다.
    """
    module = ModuleType("tools.fake_metric")
    photo = np.zeros((10, 10, 3), dtype=np.uint8)
    module.seen_argv = []

    def read_frame_rgb(_reference, _frame):
        return photo

    def table_finder(_folder, name):
        if name is None:
            return None
        return lambda row, image: np.zeros(image.shape[:2], dtype=bool)

    def measure_part(part, rows):
        occlusion = module.table_finder("folder", "t")
        return area_preparation.rows_to_known_map(rows, lambda row: photo, occlusion)

    def main():
        module.seen_argv.append(list(sys.argv))
        module.measure_part(FakePart("lip"), [make_row(1), make_row(2)])

    module.read_frame_rgb = read_frame_rgb
    module.table_finder = table_finder
    module.measure_part = measure_part
    module.main = main
    return module


def test_patched_times_tool_and_service_functions_and_puts_them_back():
    """도구 이름 자리와 서비스 area_preparation 자리를 둘 다 재야 부위 찾기 안의 지도 펴기가 잡힌다.

    끝나면 원래 함수로 돌아가야 다음 도구나 시험이 시계 붙은 판을 쓰지 않는다.
    """
    module = fake_tool()
    places = [
        (module, "read_frame_rgb"),
        (module, "table_finder"),
        (module, "measure_part"),
        (area_preparation, "flatten"),
        (area_preparation, "flatten_mask"),
        (area_preparation, "known_median_map"),
    ]
    originals = [getattr(owner, name) for owner, name in places]
    recorder = Recorder()

    with patched(recorder, "noise", module):
        assert all(
            getattr(owner, name) is not original
            for (owner, name), original in zip(places, originals, strict=True)
        )
        with recorder.lap("noise"):
            module.main()

    assert all(
        getattr(owner, name) is original
        for (owner, name), original in zip(places, originals, strict=True)
    )
    laps = recorder.laps
    assert laps[("noise", "part:lip")].calls == 1
    assert laps[("noise", "flatten")].calls == 2
    assert len(laps[("noise", "flatten")].distinct) == 2
    assert laps[("noise", "flattenMask")].calls == 2
    assert laps[("noise", "occlusionTable")].calls == 2
    assert laps[("noise", "median")].calls == 1


def test_report_pieces_add_up_to_tool_time_and_parts_keep_inner_time():
    """구간 자체 시간을 다 더하면 도구 전체 시간이 되어야 어디서 시간이 새는지 빠짐없이 보인다.

    부위 표는 안쪽 구간(지도 펴기 등)까지 넣은 시간이라, 부위끼리 견줄 때 쓴다.
    도구 10초 = 자체 1 + 사진 읽기 2 + 립 7(자체 3 + 안쪽 지도 펴기 4).
    """
    clock = FakeClock()
    recorder = Recorder(clock)
    with recorder.lap("noise"):
        clock.advance(1)
        with recorder.lap("readPhoto", key=1):
            clock.advance(2)
        with recorder.lap("part:lip"):
            clock.advance(3)
            with recorder.lap("flatten", key="face"):
                clock.advance(4)
    memory = MemorySampler(recorder)

    data = profile_report(recorder, "noise", memory, 10.0, {"tool": "noise"})

    assert [piece["name"] for piece in data["pieces"]] == [
        "flatten",
        "part:lip",
        "readPhoto",
        "other",
    ]
    assert sum(piece["selfSeconds"] for piece in data["pieces"]) == 10
    assert data["parts"] == [{"part": "lip", "calls": 1, "seconds": 7}]
    assert data["totalSeconds"] == 10
    assert label("part:lip") == "부위 계산: lip"


def test_run_tool_passes_arguments_to_tool_main_and_restores_argv():
    """도구 main은 sys.argv로 인자를 읽으므로, 재는 동안만 도구 인자로 바꾸고 끝나면 돌려놓는다."""
    module = fake_tool()
    saved = list(sys.argv)

    recorder, _memory, total = run_tool("noise", module, ["samples/x", "--occlusion", "t"])

    assert module.seen_argv == [["tools/noise_metric.py", "samples/x", "--occlusion", "t"]]
    assert sys.argv == saved
    assert recorder.laps[("noise", "noise")].calls == 1
    assert total >= 0


def test_power_status_always_has_both_fields():
    """충전 여부를 모르는 컴퓨터에서도 칸은 있어야 결과 파일 모양이 같다."""
    status = power_status()

    assert set(status) == {"acPower", "batteryPercent"}
    assert status["acPower"] in (True, False, None)
