"""샘플 폴더의 사진을 서비스와 같은 코드로 판정하고 단계·묶음마다 쓸 사진을 센다(개발용).

얼굴 점 찾기(build_landmarks) → 사진 판정(check_frames) → 부위별 고르기(usable_rows) →
흐린 사진 빼기(drop_blurry) 순서이고 기준값은 서비스 것을 그대로 쓴다. 사람이 고르지 않는다.
묶음은 단계 시작 앞(before)·끝 뒤(after) plan.MARGIN_MS 구간이다. 서비스 창 안 장수도 같이 센다.
학습에 고르는 사진(picked)은 쓸 사진 가운데 plan.THIN_GAP_MS 안에서 한 장씩이다.
결과: <샘플 폴더>/output/landmarks.json, frames_checked.json, photo_counts.json
실행 (ai/ 폴더에서): uv run --no-sync python tools/guide_area_training/judge_frames.py [영상 ID ...]
"""

import sys
from collections import Counter

import plan
import workspace

from app.schemas.landmarks import LandmarksResult
from app.tasks.area.landmarks.frame_checker import check_frames
from app.tasks.area.landmarks.landmarks_builder import build_landmarks
from app.tasks.area.landmarks.occlusion import remember_by_frame
from app.tasks.area.landmarks.occlusion_finder import find_occlusion
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import (
    RememberedPhotos,
    drop_blurry,
    recording_dropped,
    step_bounds,
    usable_rows,
    within_step,
)
from app.tasks.area.reference_area import PART_WINDOWS

PART_REGIONS = {
    "lip": ("lipsOuter",),
    "blush": ("leftCheek", "rightCheek"),
    "brow": ("leftBrow", "rightBrow"),
    "eyeshadow": ("leftEye", "rightEye"),
    "eyeliner": ("leftEye", "rightEye"),
}
KEEP = 64


def judge(video_id: str) -> dict:
    """영상 하나의 샘플 폴더를 판정하고 단계·묶음별 사진 수 표를 돌려준다."""
    folder = workspace.sample_dir(video_id)
    reference = load_reference_input(folder)
    output = folder / "output"
    output.mkdir(exist_ok=True)
    landmarks_path = output / "landmarks.json"
    if landmarks_path.is_file():
        landmarks = LandmarksResult.model_validate_json(landmarks_path.read_text(encoding="utf-8"))
    else:
        landmarks = build_landmarks(
            reference.manifest, lambda frame: read_frame_rgb(reference, frame)
        )
        landmarks_path.write_text(landmarks.model_dump_json(by_alias=True), encoding="utf-8")
    checked = check_frames(landmarks)
    (output / "frames_checked.json").write_text(
        checked.model_dump_json(by_alias=True), encoding="utf-8"
    )

    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    photos = RememberedPhotos(lambda row: read_frame_rgb(reference, frames[row.frame_index]), KEEP)
    occlusion = remember_by_frame(find_occlusion, KEEP)
    bounds = step_bounds(reference.manifest.steps)
    steps = [step.model_dump(by_alias=True) for step in reference.manifest.steps]
    by_step: dict[str, dict[str, dict]] = {}
    for item in plan.boundary_ranges(steps):
        by_step.setdefault(item["stepId"], {})[item["group"]] = item

    rows_out = []
    for step_id, groups in by_step.items():
        makeup = groups["before"]["makeup"]
        regions = PART_REGIONS[makeup]
        with within_step(*bounds[step_id]), recording_dropped() as dropped:
            usable = {
                group: {
                    row.frame_index: row
                    for region in regions
                    for row in usable_rows(checked, item["lowMs"], item["highMs"], [region])
                }
                for group, item in groups.items()
            }
            before, after = (
                sorted(usable[group].values(), key=lambda row: row.timestamp_ms)
                for group in ("before", "after")
            )
            if before or after:
                before, after = drop_blurry(before, after, photos, occlusion)
        kept = {"before": before, "after": after}
        window = dict(zip(("before", "after"), PART_WINDOWS[makeup], strict=True))
        for group, item in groups.items():
            inside = [
                row for row in checked.frames if item["lowMs"] < row.timestamp_ms <= item["highMs"]
            ]
            rejected = Counter(
                reason for row in inside if row.status == "rejected" for reason in row.reasons
            )
            in_range = {row.frame_index for row in inside}
            edge = item["highMs"] if group == "before" else item["lowMs"]
            length = window[group] or 0
            near = (edge - length, edge) if group == "before" else (edge, edge + length)
            times = {row.timestamp_ms: row.frame_index for row in kept[group]}
            rows_out.append(
                {
                    "stepId": step_id,
                    "makeup": makeup,
                    "group": group,
                    "lowMs": item["lowMs"],
                    "highMs": item["highMs"],
                    "inRange": len(inside),
                    "noFace": sum(row.status == "noFace" for row in inside),
                    "rejected": dict(rejected),
                    "ok": sum(row.status == "ok" for row in inside),
                    "dropped": {
                        reason: len(numbers & in_range) for reason, numbers in dropped.items()
                    },
                    "usable": len(kept[group]),
                    "usableInServiceWindow": sum(
                        near[0] < row.timestamp_ms <= near[1] for row in kept[group]
                    ),
                    "usableFrames": [row.frame_index for row in kept[group]],
                    "pickedFrames": [times[time_ms] for time_ms in plan.thin(list(times))],
                }
            )
    counts = {
        "videoId": video_id,
        "photos": len(checked.frames),
        "status": dict(Counter(row.status for row in checked.frames)),
        "groups": rows_out,
    }
    workspace.write_json(workspace.counts_path(video_id), counts)
    return counts


def main() -> None:
    wanted = set(sys.argv[1:])
    for video in workspace.load_videos():
        video_id = video["videoId"]
        if wanted and video_id not in wanted:
            continue
        if not (workspace.sample_dir(video_id) / "manifest.json").is_file():
            print(f"{video_id}: 샘플 폴더 없음, 건너뜀")
            continue
        counts = judge(video_id)
        usable = sum(group["usable"] for group in counts["groups"])
        picked = sum(len(group["pickedFrames"]) for group in counts["groups"])
        print(f"{video_id}: 사진 {counts['photos']}장, 쓸 사진 {usable}장, 고른 사진 {picked}장")


if __name__ == "__main__":
    main()
