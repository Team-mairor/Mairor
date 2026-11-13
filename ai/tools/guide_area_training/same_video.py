"""샘플 폴더의 사진이 후보 영상 가운데 어느 영상에서 나왔는지 찾는다(개발용).

이름이 다른 로컬 샘플이 후보 영상과 같은 영상이면 학습 데이터에 두 번 들어간다.
길이가 LENGTH_GAP_SECONDS 안으로 같은 후보 영상마다, 샘플 사진 몇 장을 같은 시각의 영상
장면과 작은 회색 그림으로 줄여 견준다. 밝기 차이 가운데 값이 SAME_MAX 이하면 같은 영상이다.
실행 (ai/ 폴더에서): uv run --no-sync python tools/guide_area_training/same_video.py <샘플 폴더> ...
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import workspace

LENGTH_GAP_SECONDS = 2.0
SAME_MAX = 8.0
CHECK_PHOTOS = 7
SMALL = (64, 36)


def small_gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(cv2.resize(image, SMALL, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)


def difference(folder: Path, manifest: dict, video: Path) -> float | None:
    """샘플 사진과 같은 시각 영상 장면의 밝기 차이 가운데 값. 장면을 못 읽으면 None이다."""
    frames = manifest["frames"]
    picks = [frames[i] for i in np.linspace(0, len(frames) - 1, CHECK_PHOTOS).astype(int)]
    capture = cv2.VideoCapture(str(video))
    gaps = []
    for frame in picks:
        photo = cv2.imdecode(np.fromfile(folder / frame["path"], dtype=np.uint8), cv2.IMREAD_COLOR)
        capture.set(cv2.CAP_PROP_POS_MSEC, frame["timestampMs"])
        found, scene = capture.read()
        if found and photo is not None:
            gap = small_gray(photo).astype(np.float32) - small_gray(scene).astype(np.float32)
            gaps.append(float(np.abs(gap).mean()))
    capture.release()
    return float(np.median(gaps)) if gaps else None


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for folder in map(Path, sys.argv[1:]):
        manifest = workspace.read_json(folder / "manifest.json")
        length = manifest["source"]["durationSeconds"]
        matches = []
        for video in workspace.load_videos():
            video_id = video["videoId"]
            info = workspace.read_json(workspace.info_path(video_id))
            if abs(info["duration"] - length) > LENGTH_GAP_SECONDS:
                continue
            files = list((workspace.processor_dir(video_id) / "downloads").glob(f"{video_id}.*"))
            gap = difference(folder, manifest, files[0]) if files else None
            matches.append((video_id, gap))
        same = [video_id for video_id, gap in matches if gap is not None and gap <= SAME_MAX]
        detail = ", ".join(
            f"{v} 차이 {g:.1f}" if g is not None else f"{v} 못 읽음" for v, g in matches
        )
        print(f"{folder.name} ({length:.0f}초): 같은 영상 {same or '없음'}")
        print(f"  견준 영상: {detail or '길이가 같은 영상 없음'}")


if __name__ == "__main__":
    main()
