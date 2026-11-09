"""가이드 영역 생성을 서비스 입구 그대로 돌리며 구간별 시간·호출 수·메모리를 잰다 (개발용).

샘플 폴더의 사진을 이 컴퓨터에서만 열리는 임시 웹 서버로 내주고,
area_work.build_area_from_frames가 BE 요청을 받았을 때처럼 주소로 사진을 받아 영역을 만들게 한다.
서비스 코드는 고치지 않는다. 구간 함수들을 시계로 감싼 판으로 잠깐 바꿔 끼웠다가 끝나면 되돌린다.
결과 폴더에 guide_area.json(전후 비교 기준)과 profile.json(구간 기록)을 저장한다.

운영 AI 서버는 2코어라, 기본으로 이 프로세스를 앞쪽 논리 코어 2개에만 돌게 묶는다(--cores).
라이브러리 스레드 수는 기본값 그대로 둔다. 다만 onnxruntime·OpenCV는 이 컴퓨터의 코어 수로
일꾼을 정해, 코어를 묶은 채 그대로 두면 일꾼이 코어보다 많아진다. 서버처럼 재려면
--ort-threads·--cv-threads로 서버에서 고를 일꾼 수를 정한다. MediaPipe는 정하는 칸이 없다.

실행 (ai/ 폴더에서):
uv run python tools/profile_guide_area.py samples/local_03_seq <결과 폴더>
    [--manifest <manifest.json>] [--guide-input <guide_input.json>] [--cores 2]
    [--ort-threads 1] [--cv-threads 2] [--lines 1]
영역 만들기를 여러 줄로 돌리면(--lines 2) 구간 시간은 줄마다 따로 재서,
안쪽 합이 영역 시간보다 크다.
"""

import argparse
import asyncio
import ctypes
import json
import os
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Hashable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial, wraps
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

import cv2
import onnxruntime

from app.core.config import Settings
from app.schemas.guide import GuideInput
from app.schemas.guide_area import GuideArea
from app.schemas.guide_job import FrameSource, ReferenceFrame, ReferenceFrames
from app.schemas.manifest import Manifest
from app.tasks.area import area_work, guide_area_builder, reference_area
from app.tasks.area.parts import area_preparation

PROFILE_FILE = "profile.json"
AREA_FILE = "guide_area.json"
WORK_FOLDER = "work"
DEFAULT_CORES = 2
SAMPLE_SECONDS = 0.2
MB = 1024 * 1024

STAGES = ("download", "landmarks", "check", "area")
LABELS = {
    "download": "사진 받기",
    "landmarks": "얼굴 점",
    "check": "사진 판정",
    "area": "영역 만들기",
    "areaLine": "영역 줄(build_guide_area)",
    "readPhoto": "사진 읽기",
    "faceModel": "얼굴 점 모델",
    "occlusionLookup": "가림 찾기 요청",
    "occlusionModel": "가림 찾기 모델",
    "flatten": "얼굴 지도 펴기",
    "flattenMask": "가린 칸 지도 펴기",
    "lip": "부위 찾기: 립",
    "blush": "부위 찾기: 블러셔",
    "brow": "부위 찾기: 눈썹",
    "eyeshadow": "부위 찾기: 아이섀도",
    "eyeliner": "부위 찾기: 아이라인",
    "outline": "결과 만들기: 테두리·얼굴 주소",
    "other": "그 밖",
}
PART_FINDERS = {
    "lip": "find_lip_area",
    "blush": "find_blush_area",
    "brow": "find_brow_area",
    "eyeshadow": "find_eyeshadow_area",
    "eyeliner": "find_eyeliner_area",
}
OUTLINE_FUNCTIONS = ("mask_outline", "mask_outlines", "simplify_outline", "points_to_anchors")


@dataclass
class Lap:
    """한 구간 이름의 기록. seconds는 안쪽 구간까지 넣은 시간, self_seconds는 뺀 시간이다."""

    calls: int = 0
    seconds: float = 0.0
    self_seconds: float = 0.0
    distinct: set[Hashable] = field(default_factory=set)


class Recorder:
    """구간 이름별 호출 수·걸린 시간과 서로 다른 대상 수를 모은다.

    구간 안에서 다른 구간이 불리면 안쪽 시간은 바깥 구간의 self_seconds에서 뺀다.
    그래서 큰 구간 하나 안의 self_seconds를 모두 더하면 큰 구간 시간과 같다.
    기록은 (큰 구간, 이름)별로 나눠, 같은 사진 읽기라도 얼굴 점·판정·영역 중 어디서 불렸는지 가른다.
    큰 구간은 차례로 하나씩 돈다. 영역을 여러 줄로 만들면 줄마다 다른 스레드에서 기록하므로,
    열린 구간은 스레드마다 따로 쌓고 기록은 잠가서 더한다. 다른 스레드에서 처음 열린 구간은
    그때 열려 있는 큰 구간에 속한다. 그때는 줄들이 동시에 돌아 안쪽 합이 큰 구간보다 클 수 있다.
    """

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self.clock = clock
        self.laps: dict[tuple[str, str], Lap] = defaultdict(Lap)
        self.notes: dict[str, Any] = {}
        self.current_stage: str | None = None
        self._lock = threading.Lock()
        self._local = threading.local()

    def _opened(self) -> list[tuple[str, float, list[float], str]]:
        """이 스레드에서 열려 있는 (이름, 시작, 안쪽 시간, 큰 구간) 목록."""
        if not hasattr(self._local, "opened"):
            self._local.opened = []
        return self._local.opened

    @contextmanager
    def lap(self, name: str, key: Hashable | None = None) -> Iterator[None]:
        """name 구간 하나를 잰다. key가 있으면 서로 다른 대상 수를 세는 데 쓴다."""
        opened = self._opened()
        top = not opened and self.current_stage is None
        if top:
            self.current_stage = name
        if opened:
            stage = opened[0][3]
        else:
            stage = name if top else self.current_stage or name
        inner = [0.0]
        start = self.clock()
        opened.append((name, start, inner, stage))
        try:
            yield
        finally:
            opened.pop()
            took = self.clock() - start
            with self._lock:
                record = self.laps[(stage, name)]
                record.calls += 1
                record.seconds += took
                record.self_seconds += took - inner[0]
                if key is not None:
                    record.distinct.add(key)
            if opened:
                opened[-1][2][0] += took
            elif top:
                self.current_stage = None

    def wrap(
        self,
        name: str,
        func: Callable[..., Any],
        key: Callable[..., Hashable] | None = None,
    ) -> Callable[..., Any]:
        """func를 부를 때마다 name 구간으로 재는 함수. key는 func의 인자로 대상을 고른다."""

        @wraps(func)
        def timed(*args: Any, **kwargs: Any) -> Any:
            with self.lap(name, None if key is None else key(*args, **kwargs)):
                return func(*args, **kwargs)

        return timed

    def wrap_async(
        self, name: str, func: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        """wrap과 같되 기다리는 함수(async)를 잰다."""

        @wraps(func)
        async def timed(*args: Any, **kwargs: Any) -> Any:
            with self.lap(name):
                return await func(*args, **kwargs)

        return timed


@contextmanager
def patched(recorder: Recorder) -> Iterator[None]:
    """서비스 모듈의 구간 함수들을 recorder로 재는 판으로 바꿔 끼우고, 끝나면 원래대로 돌린다.

    서비스가 다른 모듈에서 가져다 쓰는 이름 자리를 바꾼다. 얼굴 점 모델과 가림 찾기 모델은
    build_reference_area의 기본 인자라 직접 바꿀 수 없어, 그것을 넘겨받는
    build_landmarks와 remember_by_frame 자리에서 감싼다.
    """
    originals: list[tuple[object, str, Any]] = []

    def put(module: object, name: str, replacement: Any) -> None:
        originals.append((module, name, getattr(module, name)))
        setattr(module, name, replacement)

    def frame_key(_reference: object, frame: Any) -> int:
        return frame.frame_index

    def row_key(row: Any, *_args: object) -> int:
        return row.frame_index

    def face_key(_image: object, face: object) -> int:
        return id(face)

    real_landmarks = reference_area.build_landmarks
    real_check = reference_area.check_frames
    real_remember = reference_area.remember_by_frame

    def timed_landmarks(manifest: Any, load_photo: Any, finder: Any) -> Any:
        with recorder.lap("landmarks"):
            return real_landmarks(manifest, load_photo, recorder.wrap("faceModel", finder))

    def timed_remember(find: Any, keep: int) -> Any:
        model = recorder.wrap("occlusionModel", find, row_key)
        return recorder.wrap("occlusionLookup", real_remember(model, keep), row_key)

    try:
        put(area_work, "download_frames", _timed_download(recorder, area_work.download_frames))
        put(reference_area, "build_landmarks", timed_landmarks)
        put(reference_area, "check_frames", recorder.wrap("check", real_check))
        put(
            reference_area,
            "build_area_in_lines",
            recorder.wrap("area", reference_area.build_area_in_lines),
        )
        put(
            reference_area,
            "build_guide_area",
            recorder.wrap("areaLine", reference_area.build_guide_area),
        )
        put(
            reference_area,
            "read_frame_rgb",
            recorder.wrap("readPhoto", reference_area.read_frame_rgb, frame_key),
        )
        put(reference_area, "remember_by_frame", timed_remember)
        put(
            area_preparation,
            "flatten",
            recorder.wrap("flatten", area_preparation.flatten, face_key),
        )
        put(
            area_preparation,
            "flatten_mask",
            recorder.wrap("flattenMask", area_preparation.flatten_mask, face_key),
        )
        for name, function in PART_FINDERS.items():
            put(
                guide_area_builder,
                function,
                recorder.wrap(name, getattr(guide_area_builder, function)),
            )
        for function in OUTLINE_FUNCTIONS:
            put(
                guide_area_builder,
                function,
                recorder.wrap("outline", getattr(guide_area_builder, function)),
            )
        yield
    finally:
        for module, name, original in reversed(originals):
            setattr(module, name, original)


def _timed_download(
    recorder: Recorder, download: Callable[..., Awaitable[list[int]]]
) -> Callable[..., Awaitable[list[int]]]:
    """사진 받기를 재고, 요청한 장 수와 못 받은 장 수를 recorder.notes에 적는다."""

    @wraps(download)
    async def timed(frames: Any, *args: Any, **kwargs: Any) -> list[int]:
        with recorder.lap("download"):
            missing = await download(frames, *args, **kwargs)
        recorder.notes["requestedPhotos"] = len(frames)
        recorder.notes["missingPhotos"] = len(missing)
        return missing

    return timed


class _MemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def process_memory_bytes() -> int | None:
    """이 프로세스가 지금 쓰는 실제 메모리(바이트). 재지 못하는 OS면 None이다.

    윈도우는 작업 집합(RAM에 올라와 있는 크기), 리눅스는 /proc/self/statm의 상주 크기다.
    MediaPipe·onnxruntime처럼 파이썬 밖에서 잡은 메모리도 들어간다.
    """
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_MemoryCounters),
            ctypes.c_ulong,
        ]
        counters = _MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    statm = Path("/proc/self/statm")
    if statm.is_file():
        return int(statm.read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    return None


class MemorySampler:
    """SAMPLE_SECONDS마다 프로세스 메모리를 재서 큰 구간별 최대값을 모은다 (with로 켜고 끈다)."""

    def __init__(self, recorder: Recorder, interval: float = SAMPLE_SECONDS) -> None:
        self.recorder = recorder
        self.interval = interval
        self.start_bytes = process_memory_bytes()
        self.peaks: dict[str, int] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> "MemorySampler":
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            used = process_memory_bytes()
            if used is None:
                return
            stage = self.recorder.current_stage or "idle"
            self.peaks[stage] = max(self.peaks.get(stage, 0), used)
            self.peaks["all"] = max(self.peaks.get("all", 0), used)


def limit_cores(count: int) -> list[int]:
    """이 프로세스를 앞쪽 count개 논리 코어에서만 돌게 묶고 묶인 코어 번호를 돌려준다.

    count가 0이면 묶지 않고 모든 코어 번호를 돌려준다.
    윈도우 0·1번 논리 코어는 보통 물리 코어 하나의 두 스레드라, 2 vCPU 서버(m6i.large)와 비슷하다.
    """
    total = os.cpu_count() or 1
    if count <= 0:
        return list(range(total))
    if count > total:
        raise ValueError(f"코어는 {total}개까지 묶을 수 있습니다: {count}")
    cores = list(range(count))
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        if not kernel32.SetProcessAffinityMask(kernel32.GetCurrentProcess(), (1 << count) - 1):
            raise OSError("코어를 묶지 못했습니다")
        return cores
    os.sched_setaffinity(0, cores)
    return sorted(os.sched_getaffinity(0))


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        """사진 수천 장의 요청 줄을 화면에 찍지 않는다."""


@contextmanager
def photo_server(root: Path) -> Iterator[str]:
    """root 폴더를 이 컴퓨터에서만 열리는 임시 웹 서버로 내주고 주소 앞부분을 돌려준다.

    with가 끝나면 서버를 끈다.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def reference_frames(manifest: Manifest, base_url: str) -> ReferenceFrames:
    """manifest 사진을 BE 요청의 사진 목록 모양으로 바꾼다. 주소는 base_url 아래 manifest 경로다."""
    return ReferenceFrames(
        source=FrameSource(
            width=manifest.source.width,
            height=manifest.source.height,
            fps=manifest.source.fps,
        ),
        items=[
            ReferenceFrame(
                frame_index=frame.frame_index,
                timestamp_ms=frame.timestamp_ms,
                step_id=frame.step_id,
                url=f"{base_url}/{frame.path}",
                width=frame.width,
                height=frame.height,
            )
            for frame in manifest.frames
        ],
    )


def stage_report(recorder: Recorder, peaks: dict[str, int]) -> list[dict[str, Any]]:
    """큰 구간마다 시간·최대 메모리와 안쪽 구간 기록을 표 모양으로 만든다.

    안쪽 구간은 self_seconds 큰 순서이고, 마지막 other는 큰 구간 자신의 self_seconds다.
    그래서 pieces의 selfSeconds를 모두 더하면 큰 구간 seconds와 같다.
    """
    report = []
    for stage in STAGES:
        whole = recorder.laps.get((stage, stage))
        if whole is None:
            continue
        pieces = [
            {
                "name": name,
                "calls": lap.calls,
                "distinct": len(lap.distinct) if lap.distinct else None,
                "seconds": round(lap.seconds, 3),
                "selfSeconds": round(lap.self_seconds, 3),
            }
            for (owner, name), lap in recorder.laps.items()
            if owner == stage and name != stage
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
        peak = peaks.get(stage)
        report.append(
            {
                "stage": stage,
                "seconds": round(whole.seconds, 3),
                "peakMemoryMb": None if peak is None else round(peak / MB),
                "pieces": pieces,
            }
        )
    return report


@contextmanager
def onnx_threads(count: int | None) -> Iterator[None]:
    """count가 있으면 그동안 여는 onnxruntime 모델의 일꾼(intra-op 스레드) 수를 count로 정한다.

    서비스(occlusion_finder._session)는 일꾼 수를 정하지 않아 onnxruntime이 물리 코어 수를 고른다.
    모델은 처음 쓸 때 한 번 열리므로 측정을 시작하기 전에 들어가야 한다.
    노드 사이 일꾼(inter-op)은 1명이다. 끝나면 onnxruntime.InferenceSession을 원래대로 돌린다.
    """
    if count is None:
        yield
        return
    real = onnxruntime.InferenceSession

    def session(path: Any, sess_options: Any = None, **kwargs: Any) -> Any:
        options = sess_options or onnxruntime.SessionOptions()
        options.intra_op_num_threads = count
        options.inter_op_num_threads = 1
        return real(path, sess_options=options, **kwargs)

    onnxruntime.InferenceSession = session
    try:
        yield
    finally:
        onnxruntime.InferenceSession = real


def run(
    guide_input: GuideInput, manifest: Manifest, photo_root: Path, settings: Settings
) -> tuple[GuideArea, Recorder, MemorySampler, float]:
    """사진을 임시 웹 서버로 내주고 서비스 입구로 영역을 만들며 잰다.

    (영역, 구간 기록, 메모리 기록, 전체 초)를 돌려준다.
    """
    recorder = Recorder()
    with photo_server(photo_root) as base_url, patched(recorder):
        frames = reference_frames(manifest, base_url)
        with MemorySampler(recorder) as memory:
            start = time.perf_counter()
            area = asyncio.run(area_work.build_area_from_frames(guide_input, frames, settings))
            total = time.perf_counter() - start
    return area, recorder, memory, total


def profile_data(
    recorder: Recorder,
    memory: MemorySampler,
    total: float,
    conditions: dict[str, Any],
) -> dict[str, Any]:
    """profile.json에 넣을 내용. 조건·전체 시간·메모리·큰 구간 표다."""
    start = memory.start_bytes
    peak = memory.peaks.get("all")
    return {
        "conditions": conditions,
        "totalSeconds": round(total, 3),
        "startMemoryMb": None if start is None else round(start / MB),
        "peakMemoryMb": None if peak is None else round(peak / MB),
        "notes": recorder.notes,
        "stages": stage_report(recorder, memory.peaks),
    }


def print_report(data: dict[str, Any]) -> None:
    """profile.json 내용을 사람이 읽는 표로 찍는다."""
    print(f"전체 {data['totalSeconds']:.1f}초, 최대 메모리 {data['peakMemoryMb']}MB")
    for stage in data["stages"]:
        name = LABELS[stage["stage"]]
        print(f"\n[{name}] {stage['seconds']:.1f}초, 최대 메모리 {stage['peakMemoryMb']}MB")
        for piece in stage["pieces"]:
            distinct = "" if piece["distinct"] is None else f", 서로 다른 것 {piece['distinct']}"
            print(
                f"  {LABELS[piece['name']]}: 자체 {piece['selfSeconds']:.1f}초"
                f" (안쪽 포함 {piece['seconds']:.1f}초, 호출 {piece['calls']}{distinct})"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="가이드 영역 생성 구간별 시간·메모리 재기")
    parser.add_argument("sample", type=Path, help="manifest 사진 경로의 기준 폴더")
    parser.add_argument("out", type=Path, help="guide_area.json·profile.json을 저장할 폴더")
    parser.add_argument("--manifest", type=Path, help="기본은 <sample>/manifest.json")
    parser.add_argument("--guide-input", type=Path, help="기본은 <sample>/guide_input.json")
    parser.add_argument(
        "--cores", type=int, default=DEFAULT_CORES, help="묶을 논리 코어 수, 0은 안 묶음"
    )
    parser.add_argument("--ort-threads", type=int, help="가림 찾기 모델 일꾼 수, 없으면 기본값")
    parser.add_argument("--cv-threads", type=int, help="OpenCV 일꾼 수, 없으면 기본값")
    parser.add_argument("--lines", type=int, default=1, help="영역 만들기 줄 수 (area_lines)")
    args = parser.parse_args()

    cores = limit_cores(args.cores)
    if args.cv_threads is not None:
        cv2.setNumThreads(args.cv_threads)
    manifest_path = args.manifest or args.sample / "manifest.json"
    guide_input_path = args.guide_input or args.sample / "guide_input.json"
    manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    guide_input = GuideInput.model_validate_json(guide_input_path.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    settings = Settings(_env_file=None, area_work_dir=args.out / WORK_FOLDER, area_lines=args.lines)

    with onnx_threads(args.ort_threads):
        area, recorder, memory, total = run(guide_input, manifest, args.sample, settings)

    conditions = {
        "platform": sys.platform,
        "cpuCount": os.cpu_count(),
        "cores": cores,
        "opencvThreads": cv2.getNumThreads(),
        "onnxThreads": args.ort_threads,
        "lines": args.lines,
        "videoId": guide_input.video_id,
        "steps": len(guide_input.steps),
        "photos": len(manifest.frames),
        "manifest": str(manifest_path),
        "guideInput": str(guide_input_path),
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    data = profile_data(recorder, memory, total, conditions)
    (args.out / AREA_FILE).write_text(
        area.model_dump_json(by_alias=True, indent=2), encoding="utf-8"
    )
    (args.out / PROFILE_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print_report(data)
    print(f"\n저장: {args.out / AREA_FILE}, {args.out / PROFILE_FILE}")


if __name__ == "__main__":
    main()
