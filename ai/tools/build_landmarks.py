import sys
from collections import Counter
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.landmarks import LandmarksResult
from app.services.landmarks_builder import build_landmarks
from app.services.reference_input import load_reference_input, read_frame_rgb

OUTPUT_FILE = Path("output") / "landmarks.json"


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/build_landmarks.py <샘플 폴더>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    reference = load_reference_input(folder)
    result = build_landmarks(reference.manifest, lambda frame: read_frame_rgb(reference, frame))
    path = save(result, folder)

    counts = Counter(frame.status for frame in result.frames)
    many = sum(1 for frame in result.frames if frame.face_count > 1)
    print(f"사진 {len(result.frames)}장: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"여러 명: {many}장")
    print(f"저장: {path}")


def save(result: LandmarksResult, folder: Path) -> Path:
    path = folder / OUTPUT_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(result.model_dump_json(by_alias=True), encoding="utf-8")
    return path


if __name__ == "__main__":
    main()
