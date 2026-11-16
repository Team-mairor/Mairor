"""영상(시험 영상 · 실기기 녹화)을 0.2초마다 다시 돌려 게이지 값 · 문구와 단계 끝 평가를 내는 도구.

두 단계로 나뉜다.

1. extract: 영상에서 measure.MEASURE_INTERVAL_MS마다 사진을 뽑아 얼굴 지도(MAP_SIZE) · 가린
   몫(COVER_GRID칸) · 사진 상태(얼굴 수 · 고개 · 눈 뜬 정도 · 얼굴 폭 · 얼굴 밝기)를 저장한다.
   얼굴 찾기 · 지도 펴기 · 가림 찾기는 서비스 코드(face_finder · face_map · occlusion_finder)를
   그대로 쓰고, 얼굴 폭 · 밝기는 FE와 같은 뜻(얼굴 윤곽 점 가로 ÷ 영상 가로, 얼굴 점 네모를 25%
   줄인 16 × 16 평균 밝기)이다. 영상을 구간으로 나눠 여러 프로세스가 뽑고(workers), 결과 폴더에
   maps.npy · cover.npy · info.json과 칸 색 표 grid128.npy · grid64.npy를 만든다. 얼굴 사진이 든
   결과라 저장소 밖에 둔다.
2. run: 뽑은 폴더 · 가이드 결과(guide_area.json) · 단계 시각(manifest.json의 steps)으로 하위
   단계마다 브라우저와 같은 순서로 게이지와 단계 끝 평가를 돌린다(replay). 레퍼런스 본인이 사용자
   역할이라 하위 단계를 시작할 때 막대는 0 근처, 끝에서는 위치선(비율 1) 근처여야 한다.
   - 단계 시작 기준: 단계 시작 앞 START_LEAD_MS 안에서 쓸 수 있는 사진(stability.frame_reason,
     조명 판정 없이) 마지막 baseline.START_FRAMES장. NEXT_START_MIN_FRAMES장보다 적으면 그 하위
     단계는 재지 않는다(noStart).
   - 막대: 단계 시작부터 끝 뒤 END_TAIL_MS까지 MEASURE_INTERVAL_MS마다 최근 MEDIAN_WINDOW_MS 동안
     쓸 수 있는 사진의 칸 색 가운데 값으로 measure.measure를 내고 GaugeStabilizer로 다듬는다. 가린
     몫이 COVER_CELL 이상인 칸은 그 사진에서 비운다.
   - 바뀌지 않아야 할 곡선(control): 같은 시각에 그 단계에서 바르지 않는 다른 부위 영역을 같은
     방법으로 잰다. 그 단계 영역과 CONTROL_GAP_CELLS칸 안에 닿는 영역은 뺀다.
   - 단계 끝 평가: 단계 끝 뒤 END_LAG_MS에 「다음」을 눌렀다고 보고 stability.next_start_picks로
     끝 기준을 잡아 step_evaluation.evaluate를 한 번 한다. 영상 단계표의 끝 시각은 대략이라(립
     단계는 4초뿐), 끝 바로 뒤로 잡으면 아직 바르는 중인 사진이 끝 기준이 된다.

설정 값은 부를 때마다 모듈 상수에서 읽어 넘긴다. 그래서 설정 탐색(tune.py)이 상수를 바꾸면 그대로
따른다. 결과는 하위 단계마다 시각 · 잰 비율 · 보인 막대 · 문구 · 숨김 이유와 단계 끝 평가가 든
JSON이다.

python tools/gauge/replay_video.py extract <영상> <결과 폴더> [--workers N]
python tools/gauge/replay_video.py run <결과 폴더> <guide_area.json> <manifest.json> <출력 json>
"""

import argparse
import json
import math
import sys
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))

import cv2
import numpy as np

from app.schemas.guide_area import AreaSubStep, GuideArea, RegionName
from app.schemas.landmarks import FrameLandmarks, ImageSize
from app.tasks.area.common.face_map import flatten, flatten_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import area_preparation as ap
from tools.gauge import baseline as bl
from tools.gauge import color_match as cm
from tools.gauge import measure as ms
from tools.gauge import stability as st
from tools.gauge import step_evaluation as se

MAP_SIZE = 256
COVER_GRID = 128
GRIDS = (128, 64)
PART_SECONDS = 30.0
COVER_CELL = 0.5
START_LEAD_MS = 5000
END_TAIL_MS = 3000
END_LAG_MS = 3000
CONTROL_GAP_CELLS = 4
CONTROLS_PER_STEP = 3
OVAL = sorted(set(REGION_POINTS["faceOval"]))


@dataclass(frozen=True)
class Recording:
    """extract로 뽑은 영상 하나.

    times는 사진마다 시각(ms), infos는 사진 상태, slots는 얼굴 지도 번호(얼굴이 하나가 아니면 −1),
    grids는 칸 크기마다 칸 색 Lab 표(얼굴 지도 번호 순서), cover는 COVER_GRID칸 가린 몫(0~1),
    white는 영상 앞쪽 맨얼굴 사진의 흰자 색(선형 RGB, 못 재면 None)이다. far_check가 거짓이면 얼굴
    폭 판정(far)을 하지 않는다. 유튜브 레퍼런스 영상은 얼굴이 화면 폭의 20% 안팎이라 사용자 캠
    기준(stability.FACE_WIDTH_MIN)에 늘 걸리기 때문이다.
    """

    times: np.ndarray
    infos: list[dict]
    slots: np.ndarray
    grids: dict[int, np.ndarray]
    cover: np.ndarray
    white: np.ndarray | None
    far_check: bool = True


def face_brightness(rgb: np.ndarray, face) -> float | None:
    """FE faceBrightness와 같은 얼굴 밝기(0~255). 얼굴 점 네모를 25% 안쪽으로 줄여 16 × 16
    평균이다."""
    height, width = rgb.shape[:2]
    xs = np.array([p.x for p in face.landmarks])
    ys = np.array([p.y for p in face.landmarks])
    dx, dy = (xs.max() - xs.min()) * 0.25, (ys.max() - ys.min()) * 0.25
    x0, y0 = max(0.0, xs.min() + dx) * width, max(0.0, ys.min() + dy) * height
    x1, y1 = min(width, (xs.max() - dx) * width), min(height, (ys.max() - dy) * height)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    crop = rgb[int(y0) : int(math.ceil(y1)), int(x0) : int(math.ceil(x1))].astype(np.float32)
    small = cv2.resize(crop, (16, 16), interpolation=cv2.INTER_AREA)
    return float((0.299 * small[..., 0] + 0.587 * small[..., 1] + 0.114 * small[..., 2]).mean())


def shot_of(
    rgb: np.ndarray, index: int, moment_ms: int
) -> tuple[dict, np.ndarray | None, np.ndarray | None]:
    """사진 한 장의 상태, 얼굴 지도(MAP_SIZE), 가린 몫(COVER_GRID, 0~255). 얼굴이 하나가 아니면
    지도는 None."""
    from app.tasks.area.landmarks.face_finder import find_faces
    from app.tasks.area.landmarks.occlusion_finder import find_occlusion

    height, width = rgb.shape[:2]
    faces = find_faces(rgb)
    info: dict = {"t": moment_ms, "faces": len(faces)}
    if len(faces) != 1:
        return info, None, None
    face = faces[0]
    row = FrameLandmarks(
        frame_index=index,
        timestamp_ms=moment_ms,
        step_id=None,
        image_size=ImageSize(width=width, height=height),
        status="ok",
        face_count=1,
        face=face,
    )
    full = flatten(rgb, face)
    hidden = flatten_mask(find_occlusion(row, rgb), face)
    share = cv2.resize(
        hidden.astype(np.float32), (COVER_GRID, COVER_GRID), interpolation=cv2.INTER_AREA
    )
    info.update(
        yaw=face.pose.yaw,
        pitch=face.pose.pitch,
        roll=face.pose.roll,
        eyes=ap.eye_openness(row),
        faceWidth=float(np.ptp([face.landmarks[i].x for i in OVAL])),
        brightness=face_brightness(rgb, face),
    )
    small = cv2.resize(full, (MAP_SIZE, MAP_SIZE), interpolation=cv2.INTER_AREA)
    return info, small, np.round(share * 255).astype(np.uint8)


def extract_part(job: tuple[str, float, float, int, str]) -> str:
    """영상 구간 하나(시작 초 이상 끝 초 미만)를 뽑아 조각 npz로 저장하고 그 경로를 돌려준다."""
    from app.tasks.area.landmarks.occlusion_finder import load_occlusion_model

    video, begin, end, interval_ms, out = job
    cv2.setNumThreads(1)
    load_occlusion_model(1)
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = interval_ms / 1000
    moments = np.arange(math.ceil(begin / step) * step, end - 1e-9, step)
    wanted = {}
    for moment in moments:
        index = int(round(moment * fps))
        if index < count:
            wanted.setdefault(index, int(round(moment * 1000)))
    infos, maps, covers = [], [], []
    if wanted:
        first, last = min(wanted), max(wanted)
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)
        for index in range(first, last + 1):
            if not cap.grab():
                break
            if index not in wanted:
                continue
            ok, bgr = cap.retrieve()
            if not ok:
                continue
            info, small, share = shot_of(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), index, wanted[index])
            if small is not None:
                info["slot"] = len(maps)
                maps.append(small)
                covers.append(share)
            infos.append(info)
    np.savez(
        out,
        maps=np.stack(maps) if maps else np.zeros((0, MAP_SIZE, MAP_SIZE, 3), np.uint8),
        cover=np.stack(covers) if covers else np.zeros((0, COVER_GRID, COVER_GRID), np.uint8),
        info=np.array(json.dumps(infos)),
    )
    return out


def _grid_rows(face_map: np.ndarray) -> list[np.ndarray]:
    return [bl.grid_lab(face_map, grid).astype(np.float32) for grid in GRIDS]


def extract(video: Path, out: Path, workers: int, interval_ms: int | None = None) -> None:
    """영상을 구간으로 나눠 뽑고 한 폴더로 모은다(모듈 설명 1번)."""
    interval_ms = interval_ms or ms.MEASURE_INTERVAL_MS
    cap = cv2.VideoCapture(str(video))
    seconds = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    parts = out / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    jobs = []
    begin = 0.0
    while begin < seconds:
        end = min(seconds, begin + PART_SECONDS)
        jobs.append((str(video), begin, end, interval_ms, str(parts / f"part_{len(jobs):04d}.npz")))
        begin = end
    with Pool(workers) as pool:
        pool.map(extract_part, jobs, chunksize=1)
    merge(out, workers)


def merge(out: Path, workers: int) -> None:
    """조각 npz(out/parts)를 시각 순서로 모아 maps.npy · cover.npy · info.json · 칸 색 표를
    만든다."""
    parts = out / "parts"
    paths = sorted(str(path) for path in parts.glob("part_*.npz"))
    infos, maps, covers = [], [], []
    for path in paths:
        with np.load(path) as data:
            part_maps, part_cover = data["maps"], data["cover"]
            part_infos = json.loads(str(data["info"]))
        for info in part_infos:
            if "slot" in info:
                slot = info["slot"]
                info["slot"] = len(maps)
                maps.append(part_maps[slot])
                covers.append(part_cover[slot])
            infos.append(info)
    maps_array = np.stack(maps)
    np.save(out / "maps.npy", maps_array)
    np.save(out / "cover.npy", np.stack(covers))
    (out / "info.json").write_text(json.dumps(infos), encoding="utf-8")
    with Pool(workers) as pool:
        rows = pool.map(_grid_rows, list(maps_array), chunksize=32)
    for position, grid in enumerate(GRIDS):
        np.save(out / f"grid{grid}.npy", np.stack([row[position] for row in rows]))


def load(folder: Path, white_hex: str | None = None, far_check: bool = True) -> Recording:
    """extract 결과 폴더를 읽는다. 칸 색 표는 메모리에 다 올리지 않고 필요할 때 읽는다.

    white_hex를 주면 그 흰자를 쓰고, 없으면 앞쪽 정면 · 눈 뜬 사진 baseline.START_FRAMES장의 흰자
    가운데 값이다.
    """
    infos = json.loads((folder / "info.json").read_text(encoding="utf-8"))
    times = np.array([info["t"] for info in infos], dtype=np.float64)
    slots = np.array([info.get("slot", -1) for info in infos], dtype=np.int64)
    grids = {
        grid: np.load(folder / f"grid{grid}.npy", mmap_mode="r")
        for grid in GRIDS
        if (folder / f"grid{grid}.npy").exists()
    }
    cover = np.load(folder / "cover.npy", mmap_mode="r")
    if white_hex is not None:
        white = cm.linear_of_srgb(ms._hex_rgb(white_hex))
    else:
        white = _early_white(folder, infos)
    return Recording(times, infos, slots, grids, cover, white, far_check)


def _early_white(folder: Path, infos: Sequence[dict]) -> np.ndarray | None:
    maps = np.load(folder / "maps.npy", mmap_mode="r")
    holes = _eye_holes(maps.shape[1])
    found = []
    for info in infos:
        if "slot" not in info:
            continue
        quality = bl.FrameQuality(info["yaw"], info["pitch"], info["roll"], info["eyes"])
        if not bl.good_frame(quality):
            continue
        white = cm.white_color(np.asarray(maps[info["slot"]]), holes)
        if white is not None:
            found.append(white)
        if len(found) >= bl.START_FRAMES:
            break
    return np.median(found, axis=0) if found else None


def _eye_holes(size: int) -> np.ndarray:
    from tools.gauge.synthetic import eye_holes

    return eye_holes(size)


def frame_state(
    info: dict, area_cover: float, drift: float | None, far_check: bool = True
) -> st.FrameState:
    """사진 상태(info)를 stability.FrameState로. far_check가 거짓이면 얼굴 폭을 1로 둔다."""
    if info.get("faces") != 1 or "slot" not in info:
        return st.FrameState(faces=int(info.get("faces", 0)))
    return st.FrameState(
        faces=1,
        yaw=info["yaw"],
        pitch=info["pitch"],
        roll=info["roll"],
        eyes=info["eyes"],
        face_width=info["faceWidth"] if far_check else 1.0,
        brightness=info.get("brightness"),
        drift=drift,
        area_cover=area_cover,
    )


def grid_of(recording: Recording, slot: int, grid: int) -> np.ndarray:
    """얼굴 지도 번호 slot의 칸 색 Lab 표. 가린 몫이 COVER_CELL 이상인 칸은 비운다(NaN)."""
    lab = np.array(recording.grids[grid][slot], dtype=np.float64)
    hidden = np.asarray(recording.cover[slot], dtype=np.float32) / 255
    if grid != COVER_GRID:
        hidden = cv2.resize(hidden, (grid, grid), interpolation=cv2.INTER_AREA)
    lab[hidden >= COVER_CELL] = np.nan
    return lab


def cover_share(recording: Recording, slot: int, cells: np.ndarray) -> float:
    """영역 칸(cells) 중 가린 몫(0~1). 칸 크기가 COVER_GRID와 다르면 맞춰 줄인다."""
    if not cells.any():
        return 0.0
    hidden = np.asarray(recording.cover[slot], dtype=np.float32) / 255
    if cells.shape[0] != COVER_GRID:
        hidden = cv2.resize(hidden, cells.shape[::-1], interpolation=cv2.INTER_AREA)
    return float(hidden[cells].mean())


@dataclass(frozen=True)
class Target:
    """잴 영역 하나(지금 하위 단계 또는 control). areas는 (부위, 칸 표)이고 gauge는 그 하위 단계
    기준이다."""

    sub_step_id: str
    makeup: str
    areas: list[tuple[RegionName | None, np.ndarray]]
    gauge: object


def targets_of(guide: GuideArea, grid: int) -> list[tuple[str, Target]]:
    """가이드 결과에서 잴 수 있는 하위 단계(영역 · 게이지 기준 값이 있음)를 (단계 번호,
    Target)으로."""
    out = []
    for step in guide.steps:
        for sub in step.sub_steps:
            if not _measurable(sub):
                continue
            areas = [(gs.region, ms.area_cells(gs, grid)) for gs in sub.guide_sets]
            out.append((step.step_id, Target(sub.sub_step_id, step.makeup, areas, sub.gauge)))
    return out


def _measurable(sub: AreaSubStep) -> bool:
    return (
        sub.status == "extracted"
        and bool(sub.guide_sets)
        and sub.gauge is not None
        and sub.gauge.color is not None
    )


def start_baseline(
    recording: Recording, target: Target, made: np.ndarray, start_ms: float, grid: int
) -> bl.Baseline | None:
    """단계 시작 기준(모듈 설명 2번). 쓸 사진이 NEXT_START_MIN_FRAMES장보다 적으면 None."""
    picks = []
    lead = (recording.times >= start_ms - START_LEAD_MS) & (recording.times <= start_ms)
    for index in np.nonzero(lead)[0]:
        slot = int(recording.slots[index])
        state = frame_state(
            recording.infos[index],
            0.0 if slot < 0 else cover_share(recording, slot, made),
            None,
            recording.far_check,
        )
        if slot >= 0 and st.frame_reason(state, target.makeup) is None:
            picks.append(slot)
    picks = picks[-bl.START_FRAMES :]
    if len(picks) < st.NEXT_START_MIN_FRAMES:
        return None
    return bl.build_baseline([grid_of(recording, slot, grid) for slot in picks])


def measure_now(
    current: np.ndarray,
    start: bl.Baseline,
    target: Target,
    made: np.ndarray,
    white: np.ndarray | None,
) -> ms.Measure:
    """칸 색 가운데 값(current)으로 하위 단계 게이지 값 한 번. 설정은 모듈 상수에서 읽는다."""
    sides = []
    for region, cells in target.areas:
        user, count = user_side(current, start, cells, made, white)
        sides.append((region, user, count))
    return ms.measure(target.gauge, target.makeup, sides, combine=ms.COMBINE)


def user_side(
    current: np.ndarray,
    start: bl.Baseline,
    cells: np.ndarray,
    made: np.ndarray,
    white: np.ndarray | None,
) -> tuple[cm.AreaSide | None, int]:
    """measure.user_side와 같은 계산에 조명 빼기 방법(baseline.LIGHT_METHOD)을 그때 값으로
    넘긴다."""
    now = current - bl.light_change(current, start, made, bl.LIGHT_METHOD)
    pick = cells & start.cells & ~np.isnan(current).any(axis=-1)
    count = int(pick.sum())
    if count < ms.MIN_AREA_CELLS:
        return None, count
    before, after = start.lab[pick], now[pick]
    if ms.CENTER == "mean":
        before_lab, after_lab = before.mean(axis=0), after.mean(axis=0)
    elif ms.CENTER == "changed":
        size = np.linalg.norm(after - before, axis=-1)
        keep = size >= np.quantile(size, 1 - ms.CHANGED_SHARE)
        before_lab, after_lab = np.median(before[keep], axis=0), np.median(after[keep], axis=0)
    elif isinstance(ms.CENTER, str) and ms.CENTER.startswith("top"):
        share = int(ms.CENTER[3:]) / 100
        size = np.linalg.norm(after - before, axis=-1)
        keep = size >= np.quantile(size, 1 - share)
        before_lab, after_lab = np.median(before[keep], axis=0), np.median(after[keep], axis=0)
    else:
        before_lab, after_lab = np.median(before, axis=0), np.median(after, axis=0)
    before_linear = np.clip(cm.linear_of_lab(before_lab), 0, None)
    side = cm.AreaSide(
        before=before_linear,
        after=np.clip(cm.linear_of_lab(after_lab), 0, None),
        skin=before_linear,
        white=white,
    )
    return side, count


def frames_median(frames: Sequence[np.ndarray]) -> np.ndarray:
    """measure.frames_median과 같은 값(칸마다 가운데 값, 빈 칸은 그 장만 뺌)을 빨리 낸다.

    빈 칸(NaN)이 없는 칸은 np.median, 몇 장만 빈 칸만 np.nanmedian, 모두 빈 칸은 NaN이다.
    """
    stack = np.stack(frames)
    if len(frames) == 1:
        return stack[0].astype(np.float64)
    flat = stack.reshape(len(frames), -1)
    holes = np.isnan(flat)
    empty = holes.all(axis=0)
    partial = holes.any(axis=0) & ~empty
    out = np.full(flat.shape[1], np.nan)
    full = ~holes.any(axis=0)
    out[full] = np.median(flat[:, full], axis=0)
    if partial.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            out[partial] = np.nanmedian(flat[:, partial], axis=0)
    return out.reshape(stack.shape[1:])


def free_cells(start: bl.Baseline, made: np.ndarray) -> np.ndarray:
    """조명 판정(baseline.drift)에 쓰는 맨피부 칸(지금 사진의 빈 칸은 뺄 때 따로 뺀다)."""
    return start.cells & bl.skin_cells(start.lab.shape[0]) & ~bl.grow(made)


def drift_size(lab: np.ndarray, start: bl.Baseline, free: np.ndarray) -> float | None:
    """baseline.drift(lab, start, made).size와 같은 값을 맨피부 칸만 골라 빨리 낸다. 칸이 없으면
    None."""
    pick = free & ~np.isnan(lab).any(axis=-1)
    if not pick.any():
        return None
    return float(np.median(bl.delta_e_map(lab[pick], start.lab[pick])))


def curve(
    recording: Recording,
    target: Target,
    start: bl.Baseline,
    made: np.ndarray,
    begin_ms: float,
    end_ms: float,
    grid: int,
) -> list[dict]:
    """begin_ms부터 end_ms까지 MEASURE_INTERVAL_MS마다 게이지(모듈 설명 2번 막대)."""
    union = ms.made_cells([cells for _, cells in target.areas], grid)
    free = free_cells(start, made)
    stabilizer = st.GaugeStabilizer()
    rows = []
    window = np.nonzero(
        (recording.times > begin_ms - ms.MEDIAN_WINDOW_MS) & (recording.times <= end_ms)
    )[0]
    states: dict[int, tuple[str | None, int]] = {}
    labs: dict[int, np.ndarray] = {}
    for index in window:
        slot = int(recording.slots[index])
        drift = None
        if slot >= 0:
            labs[slot] = grid_of(recording, slot, grid)
            drift = drift_size(labs[slot], start, free)
        state = frame_state(
            recording.infos[index],
            0.0 if slot < 0 else cover_share(recording, slot, union),
            drift,
            recording.far_check,
        )
        states[int(index)] = (st.frame_reason(state, target.makeup), slot)
    step = st.MEASURE_INTERVAL_MS
    window = window[
        np.abs(recording.times[window] / step - np.round(recording.times[window] / step)) < 1e-6
    ]
    tick = math.ceil(begin_ms / step) * step
    while tick <= end_ms + 1e-6:
        times = recording.times[window]
        inside = window[(times > tick - ms.MEDIAN_WINDOW_MS) & (times <= tick)]
        reasons = [states[int(index)][0] for index in inside]
        usable = [states[int(index)][1] for index in inside if states[int(index)][0] is None]
        reason = st.window_reason(reasons)
        measured = None
        if usable:
            current = frames_median([labs[slot] for slot in usable])
            measured = measure_now(current, start, target, made, recording.white)
        display = stabilizer.update(tick, measured, reason)
        why = reason if measured is None else measured.reason
        rows.append(
            {
                "t": round(tick),
                "raw": None if measured is None else measured.ratio,
                "target": None if measured is None else measured.target,
                "hue": None if measured is None else measured.hue,
                "chroma": None if measured is None else measured.chroma,
                "why": why,
                "ratio": display.ratio,
                "bar": display.bar,
                "label": display.label,
                "reason": display.reason,
                "stale": display.stale,
            }
        )
        tick += step
    return rows


def end_evaluation(
    recording: Recording,
    target: Target,
    start: bl.Baseline,
    made: np.ndarray,
    others: np.ndarray,
    pressed_ms: float,
    grid: int,
) -> dict:
    """단계 끝 평가(모듈 설명 2번). 끝 기준을 못 잡으면 reason이 noEnd다."""
    lo = pressed_ms - st.NEXT_START_WINDOW_MS
    indices = np.nonzero((recording.times >= lo) & (recording.times <= pressed_ms))[0]
    times, reasons, slots = [], [], []
    for index in indices:
        slot = int(recording.slots[index])
        state = frame_state(
            recording.infos[index],
            0.0 if slot < 0 else cover_share(recording, slot, made),
            None,
            recording.far_check,
        )
        times.append(float(recording.times[index]))
        reasons.append(st.frame_reason(state, target.makeup))
        slots.append(slot)
    picks = st.next_start_picks(times, reasons, pressed_ms)
    end = None
    if picks is not None:
        end = bl.build_baseline([grid_of(recording, slots[i], grid) for i in picks])
    result = evaluate(target, start, end, recording.white, others)
    return evaluation_row(result)


def evaluate(
    target: Target,
    start: bl.Baseline | None,
    end: bl.Baseline | None,
    white: np.ndarray | None,
    exclude: np.ndarray | None,
) -> se.StepEvaluation:
    """step_evaluation.evaluate를 그때 모듈 상수 값으로 부른다."""
    return se.evaluate(
        target.sub_step_id,
        start,
        end,
        target.areas,
        target.makeup,
        target.gauge,
        white,
        exclude=exclude,
        floor=se.PAINT_FLOOR,
        share=se.PAINT_SHARE,
        width=se.BAND_WIDTH,
        gap=se.BAND_GAP,
        side_method=se.SIDE_METHOD,
        combine=se.COMBINE,
        covered_max=se.COVERED_MAX,
        drift_ratio_max=se.DRIFT_RATIO_MAX,
        drift_all_max=se.DRIFT_ALL_MAX,
    )


def evaluation_row(result: se.StepEvaluation) -> dict:
    """StepEvaluation을 JSON에 넣을 값으로."""
    return {
        "coverage": result.coverage,
        "overflow": result.overflow,
        "sides": {side: [score.coverage, score.overflow] for side, score in result.sides.items()},
        "ratio": result.ratio,
        "ratioReason": result.ratio_reason,
        "reason": result.reason,
        "drift": result.drift,
        "regions": [[r.region, r.coverage, r.overflow] for r in result.regions],
    }


def controls_of(
    targets: Sequence[tuple[str, Target]], step_id: str, made: np.ndarray, grid: int
) -> list[Target]:
    """그 단계에서 바르지 않는 다른 부위 하위 단계 영역(모듈 설명 2번 control). 겹치는 화장
    종류는 뺀다."""
    grown = bl.grow(made, CONTROL_GAP_CELLS)
    makeups = {target.makeup for sid, target in targets if sid == step_id}
    out, seen = [], set()
    for sid, target in targets:
        if sid == step_id or target.makeup in makeups or target.makeup in seen:
            continue
        cells = ms.made_cells([c for _, c in target.areas], grid)
        if (cells & grown).any():
            continue
        seen.add(target.makeup)
        out.append(target)
        if len(out) >= CONTROLS_PER_STEP:
            break
    return out


def replay(
    recording: Recording,
    guide: GuideArea,
    step_times: dict[str, tuple[float, float]],
    grid: int = 0,
    with_controls: bool = True,
) -> list[dict]:
    """하위 단계마다 게이지 곡선 · control 곡선 · 단계 끝 평가(모듈 설명 2번). grid가 0이면
    baseline.GRID."""
    grid = grid or bl.GRID
    targets = targets_of(guide, grid)
    rows = []
    for step_id, target in targets:
        if step_id not in step_times:
            continue
        begin_s, end_s = step_times[step_id]
        begin_ms, end_ms = begin_s * 1000, end_s * 1000
        made = ms.made_cells([cells for _, cells in target.areas], grid)
        row: dict = {
            "subStepId": target.sub_step_id,
            "makeup": target.makeup,
            "begin": begin_ms,
            "end": end_ms,
        }
        start = start_baseline(recording, target, made, begin_ms, grid)
        if start is None:
            row["reason"] = "noStart"
            rows.append(row)
            continue
        row["curve"] = curve(recording, target, start, made, begin_ms, end_ms + END_TAIL_MS, grid)
        others = ms.made_cells(
            [cells for sid, other in targets if sid == step_id for _, cells in other.areas], grid
        )
        row["evaluation"] = end_evaluation(
            recording, target, start, made, others & ~made, end_ms + END_LAG_MS, grid
        )
        if with_controls:
            row["controls"] = {}
            for control in controls_of(targets, step_id, made, grid):
                control_made = ms.made_cells([cells for _, cells in control.areas], grid) | made
                row["controls"][control.sub_step_id] = curve(
                    recording, control, start, control_made, begin_ms, end_ms + END_TAIL_MS, grid
                )
        rows.append(row)
    return rows


def step_times_of(manifest: dict) -> dict[str, tuple[float, float]]:
    """manifest.json의 steps에서 단계마다 (시작 초, 끝 초)."""
    return {
        step["stepId"]: (float(step["startSeconds"]), float(step["endSeconds"]))
        for step in manifest["steps"]
        if step.get("startSeconds") is not None and step.get("endSeconds") is not None
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    pull = commands.add_parser("extract")
    pull.add_argument("video", type=Path)
    pull.add_argument("out", type=Path)
    pull.add_argument("--workers", type=int, default=8)
    join = commands.add_parser("merge")
    join.add_argument("out", type=Path)
    join.add_argument("--workers", type=int, default=8)
    run = commands.add_parser("run")
    run.add_argument("folder", type=Path)
    run.add_argument("guide", type=Path)
    run.add_argument("manifest", type=Path)
    run.add_argument("out", type=Path)
    run.add_argument("--grid", type=int, default=0)
    run.add_argument("--no-far", action="store_true", help="얼굴 폭 판정을 끈다(레퍼런스 영상)")
    args = parser.parse_args()
    if args.command == "extract":
        extract(args.video, args.out, args.workers)
        return
    if args.command == "merge":
        merge(args.out, args.workers)
        return
    guide = GuideArea.model_validate_json(args.guide.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    recording = load(args.folder, far_check=not args.no_far)
    rows = replay(recording, guide, step_times_of(manifest), args.grid)
    args.out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
