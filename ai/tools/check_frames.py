"""샘플 폴더의 사진마다 부위 분석에 쓸지 판정해 output/frames_checked.json으로 저장한다 (개발용).

얼굴 점 결과(output/landmarks.json)를 읽으므로 먼저 tools/build_landmarks.py를 실행해 둔다.
실행 (ai/ 폴더에서): uv run python tools/check_frames.py samples/local_01_lip_seq
"""

import sys
from collections import Counter
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.frame_checker import check_frames, outside_count_name

LANDMARKS_FILE = Path("output") / "landmarks.json"
OUTPUT_FILE = Path("output") / "frames_checked.json"
SUMMARY_MEASURES = ("faceWidthPx", "yawDeg", "pitchDeg", "faceWidthRatio")


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/check_frames.py <샘플 폴더>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    landmarks_path = folder / LANDMARKS_FILE
    if not landmarks_path.is_file():
        print(f"{landmarks_path}가 없습니다. 먼저 tools/build_landmarks.py를 실행하세요.")
        sys.exit(1)

    landmarks = LandmarksResult.model_validate_json(landmarks_path.read_text(encoding="utf-8"))
    result = check_frames(landmarks)
    path = save(result, folder)

    counts = Counter(row.status for row in result.frames)
    reasons = Counter(
        reason for row in result.frames if row.status == "rejected" for reason in row.reasons
    )
    print(f"사진 {len(result.frames)}장: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print("빼는 이유: " + (", ".join(f"{k} {v}" for k, v in reasons.items()) or "없음"))
    for name in SUMMARY_MEASURES:
        values = [row.measures[name] for row in result.frames if name in row.measures]
        if values:
            print(f"{name}: {min(values)} ~ {max(values)}")
    outside = {
        region: sum(row.measures.get(outside_count_name(region), 0) > 0 for row in result.frames)
        for region in REGION_POINTS
    }
    print("부위가 화면 밖인 사진: " + ", ".join(f"{k} {v}" for k, v in outside.items()))
    print(f"저장: {path}")


def save(result: LandmarksResult, folder: Path) -> Path:
    """판정 결과를 <샘플 폴더>/output/frames_checked.json에 camelCase로 저장하고 경로를 돌려준다."""
    path = folder / OUTPUT_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(result.model_dump_json(by_alias=True), encoding="utf-8")
    return path


if __name__ == "__main__":
    main()
