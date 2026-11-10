"""지표 도구(잡음·안정성·시간·경계)를 그대로 돌리며 구간별 시간·호출 수·메모리를 잰다 (개발용).

지표 도구 코드는 고치지 않는다. 도구 main을 그대로 부르되, 사진 읽기·가림 표 읽기·얼굴 지도 펴기·
가린 칸 지도 펴기·중앙값 지도·분할 모델·나가는 영역 만들기·저장 지도 읽기·쓰기 함수와
부위마다 재는 함수를 시계로 감싼 판으로 잠깐 바꿔 끼웠다가 끝나면 되돌린다.
서비스 부위 찾기가 안에서 부르는 area_preparation의 같은 함수도 같이 감싼다.
시계는 tools/profile_guide_area.py의 Recorder를 쓴다.
도구 결과(noise.json 등)는 도구가 늘 두던 곳에 그대로 저장되고, 구간 기록은 그 옆
profile_<도구>.json에 둔다. 충전 중이 아니면 같은 코드도 느려져 전후 비교가 흔들리므로
전원 연결 여부도 적는다.
기준값을 바꿔 다시 재는 빠른 판도 잴 수 있게 --set·--tag를 받는다(tools/metric_settings.py).
--set은 도구를 불러오기 전에 넣고, 구간 기록은 --tag 폴더에 둔다.

실행 (ai/ 폴더에서):
uv run python tools/profile_metrics.py <noise|stability|timing|boundary> <샘플 폴더> [도구 인자...]
    [--set <모듈>.<상수>=<값> ...] [--tag <이름>]
예: uv run python tools/profile_metrics.py noise samples/local_03_seq --occlusion before334
"""

import ctypes
import importlib
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.tasks.area.parts import area_preparation
from tools.metric_settings import (
    SETTINGS_USAGE,
    apply_settings,
    split_settings,
    split_tag,
    tagged_dir,
)
from tools.occlusion_tables import output_dir, split_occlusion
from tools.profile_guide_area import MB, MemorySampler, Recorder

TOOLS = ("noise", "stability", "timing", "boundary")
USAGE = (
    "사용법: uv run python tools/profile_metrics.py <noise|stability|timing|boundary>"
    f" <샘플 폴더> [도구 인자...] {SETTINGS_USAGE}"
)
PROFILE_FILE = "profile_{tool}.json"
PART_PREFIX = "part:"
PIECES = {
    "read_frame_rgb": "readPhoto",
    "flatten": "flatten",
    "flatten_mask": "flattenMask",
    "known_median_map": "median",
    "output_area": "output",
    "read_maps": "storeRead",
    "write_maps": "storeWrite",
    "read_median": "medianRead",
    "write_median": "medianWrite",
}
PART_STEPS = {
    "noise": "measure_part",
    "stability": "measure_part_step",
    "timing": "measure_step",
    "boundary": "measure_part",
}
LABELS = {
    "noise": "잡음",
    "stability": "안정성",
    "timing": "시간",
    "boundary": "경계",
    "readPhoto": "사진 읽기",
    "occlusionTable": "가림 표 읽기",
    "flatten": "얼굴 지도 펴기",
    "flattenMask": "가린 칸 지도 펴기",
    "median": "중앙값 지도",
    "parse": "분할 모델",
    "output": "나가는 영역 만들기",
    "storeRead": "저장 지도 읽기",
    "storeWrite": "저장 지도 쓰기",
    "medianRead": "저장 대표 지도 읽기",
    "medianWrite": "저장 대표 지도 쓰기",
    "other": "그 밖(도구 자체)",
}


def frame_key(_reference: object, frame: Any, *_args: object) -> int:
    return frame.frame_index


def face_key(_image: object, face: object, *_args: object, **_kwargs: object) -> int:
    return id(face)


def row_key(row: Any, *_args: object) -> int:
    return row.frame_index


KEYS: dict[str, Callable[..., Any]] = {
    "read_frame_rgb": frame_key,
    "flatten": face_key,
    "flatten_mask": face_key,
}


def label(name: str) -> str:
    """구간 이름을 사람이 읽는 이름으로 바꾼다. 부위 구간은 「부위 계산: 이름」이다."""
    if name.startswith(PART_PREFIX):
        return f"부위 계산: {name[len(PART_PREFIX) :]}"
    return LABELS.get(name, name)


def part_lap(recorder: Recorder, measure: Callable[..., Any]) -> Callable[..., Any]:
    """첫 인자로 부위(Part)를 받는 재기 함수를 부위 이름 구간(part:<이름>)으로 잰다."""

    @wraps(measure)
    def timed(part: Any, *args: Any, **kwargs: Any) -> Any:
        with recorder.lap(f"{PART_PREFIX}{part.name}"):
            return measure(part, *args, **kwargs)

    return timed


def timed_table_finder(recorder: Recorder, table_finder: Callable[..., Any]) -> Callable[..., Any]:
    """가림 표 찾기 함수를 만드는 함수를 감싸, 만든 찾기 함수를 occlusionTable 구간으로 잰다."""

    @wraps(table_finder)
    def make(*args: Any, **kwargs: Any) -> Any:
        finder = table_finder(*args, **kwargs)
        if finder is None:
            return None
        return recorder.wrap("occlusionTable", finder, row_key)

    return make


def timed_parser(recorder: Recorder, onnx_parser: Callable[..., Any]) -> Callable[..., Any]:
    """분할 모델을 여는 함수를 감싸, 연 모델의 분할 함수를 parse 구간으로 잰다."""

    @wraps(onnx_parser)
    def make(*args: Any, **kwargs: Any) -> Any:
        return recorder.wrap("parse", onnx_parser(*args, **kwargs), face_key)

    return make


def owners(module: ModuleType) -> list[ModuleType]:
    """구간 함수를 바꿔 끼울 모듈들. 도구, 잡음 도구, 디스크 저장, area_preparation이다.

    시간 도구는 잡음 도구의 flats_to_map을 쓰고, 그 안에서 잡음 도구 이름 자리의
    known_median_map을 부르므로 잡음 도구 모듈도 같이 바꾼다.
    """
    found = [
        module,
        sys.modules.get("tools.noise_metric"),
        sys.modules.get("tools.face_map_store"),
        area_preparation,
    ]
    unique: list[ModuleType] = []
    for owner in found:
        if owner is not None and all(owner is not seen for seen in unique):
            unique.append(owner)
    return unique


@contextmanager
def patched(recorder: Recorder, tool: str, module: ModuleType) -> Iterator[None]:
    """도구와 서비스 모듈의 구간 함수를 recorder로 재는 판으로 바꿔 끼우고, 끝나면 되돌린다."""
    originals: list[tuple[object, str, Any]] = []

    def put(owner: object, name: str, replacement: Any) -> None:
        originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, replacement)

    try:
        for owner in owners(module):
            for name, piece in PIECES.items():
                if hasattr(owner, name):
                    put(owner, name, recorder.wrap(piece, getattr(owner, name), KEYS.get(name)))
        if hasattr(module, "table_finder"):
            put(module, "table_finder", timed_table_finder(recorder, module.table_finder))
        if hasattr(module, "onnx_parser"):
            put(module, "onnx_parser", timed_parser(recorder, module.onnx_parser))
        step = PART_STEPS[tool]
        put(module, step, part_lap(recorder, getattr(module, step)))
        yield
    finally:
        for owner, name, original in reversed(originals):
            setattr(owner, name, original)


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def power_status() -> dict[str, Any]:
    """전원 연결 여부(acPower)와 배터리 %(batteryPercent). 모르면 None이다. 윈도우에서만 잰다."""
    unknown: dict[str, Any] = {"acPower": None, "batteryPercent": None}
    if sys.platform != "win32":
        return unknown
    status = _PowerStatus()
    if not ctypes.WinDLL("kernel32").GetSystemPowerStatus(ctypes.byref(status)):
        return unknown
    return {
        "acPower": {0: False, 1: True}.get(status.ACLineStatus),
        "batteryPercent": None if status.BatteryLifePercent == 255 else status.BatteryLifePercent,
    }


def run_tool(
    tool: str, module: ModuleType, args: list[str]
) -> tuple[Recorder, MemorySampler, float]:
    """도구 main을 args 명령 인자로 돌리며 잰다. (구간 기록, 메모리 기록, 전체 초)를 돌려준다.

    도구를 불러오는 시간은 넣지 않는다. 끝나면 sys.argv를 원래대로 돌린다.
    """
    recorder = Recorder()
    saved = sys.argv
    sys.argv = [f"tools/{tool}_metric.py", *args]
    try:
        with patched(recorder, tool, module), MemorySampler(recorder) as memory:
            start = time.perf_counter()
            with recorder.lap(tool):
                module.main()
            total = time.perf_counter() - start
    finally:
        sys.argv = saved
    return recorder, memory, total


def profile_report(
    recorder: Recorder, tool: str, memory: MemorySampler, total: float, conditions: dict[str, Any]
) -> dict[str, Any]:
    """profile_<도구>.json에 넣을 내용. 조건·전체 시간·메모리·구간 표·부위 표다.

    pieces는 자체 시간 큰 순서이고 마지막 other는 도구 자신의 자체 시간이라,
    pieces의 selfSeconds를 모두 더하면 도구 전체 시간과 같다.
    parts는 부위마다 안쪽 구간까지 넣은 시간이다.
    """
    laps = {name: lap for (stage, name), lap in recorder.laps.items() if stage == tool}
    whole = laps[tool]
    pieces = [
        {
            "name": name,
            "calls": lap.calls,
            "distinct": len(lap.distinct) if lap.distinct else None,
            "seconds": round(lap.seconds, 3),
            "selfSeconds": round(lap.self_seconds, 3),
        }
        for name, lap in laps.items()
        if name != tool
    ]
    pieces.sort(key=lambda piece: piece["selfSeconds"], reverse=True)
    pieces.append(
        {
            "name": "other",
            "calls": whole.calls,
            "distinct": None,
            "seconds": round(whole.self_seconds, 3),
            "selfSeconds": round(whole.self_seconds, 3),
        }
    )
    parts = [
        {"part": name[len(PART_PREFIX) :], "calls": lap.calls, "seconds": round(lap.seconds, 3)}
        for name, lap in laps.items()
        if name.startswith(PART_PREFIX)
    ]
    start, peak = memory.start_bytes, memory.peaks.get("all")
    return {
        "conditions": conditions,
        "totalSeconds": round(total, 3),
        "startMemoryMb": None if start is None else round(start / MB),
        "peakMemoryMb": None if peak is None else round(peak / MB),
        "pieces": pieces,
        "parts": parts,
    }


def print_report(data: dict[str, Any]) -> None:
    """profile_<도구>.json 내용을 사람이 읽는 표로 찍는다."""
    tool = data["conditions"]["tool"]
    print(
        f"[{label(tool)}] 전체 {data['totalSeconds']:.1f}초, 최대 메모리 {data['peakMemoryMb']}MB"
    )
    for piece in data["pieces"]:
        distinct = "" if piece["distinct"] is None else f", 서로 다른 것 {piece['distinct']}"
        print(
            f"  {label(piece['name'])}: 자체 {piece['selfSeconds']:.1f}초"
            f" (안쪽 포함 {piece['seconds']:.1f}초, 호출 {piece['calls']}{distinct})"
        )
    for part in data["parts"]:
        print(f"  부위 {part['part']}: 안쪽 포함 {part['seconds']:.1f}초 (호출 {part['calls']})")


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in TOOLS:
        print(USAGE)
        sys.exit(1)
    tool, args = sys.argv[1], sys.argv[2:]
    args, texts = split_settings(args)
    rest, occlusion_name = split_occlusion(args)
    rest, tag = split_tag(rest)
    if texts and tag is None:
        raise SystemExit("--set을 주면 기준 결과를 덮지 않게 --tag <이름>도 줘야 합니다")
    settings = apply_settings(texts)
    folder = Path(rest[0])
    conditions = {
        "tool": tool,
        "args": args,
        "settings": [
            {"module": s.module, "name": s.name, "value": s.value, "before": s.before}
            for s in settings
        ],
        "platform": sys.platform,
        "cpuCount": os.cpu_count(),
        "power": power_status(),
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    module = importlib.import_module(f"tools.{tool}_metric")
    recorder, memory, total = run_tool(tool, module, args)
    conditions["powerAtEnd"] = power_status()
    data = profile_report(recorder, tool, memory, total, conditions)
    path = tagged_dir(output_dir(folder, occlusion_name), tag) / PROFILE_FILE.format(tool=tool)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(data)
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
