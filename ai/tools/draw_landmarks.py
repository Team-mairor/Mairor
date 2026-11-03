"""landmarks.json의 점을 사진 위에 그려 확인용 사진과 GIF를 만든다 (개발용).

실행 (ai/ 폴더에서): uv run python tools/draw_landmarks.py samples/local_01_seq
결과: <샘플 폴더>/output/points/<프레임 번호>.png, <샘플 폴더>/output/landmarks.gif
"""

import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from PIL import Image, ImageDraw, ImageFont

from app.core.errors import AppError
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.schemas.manifest import Frame
from app.tasks.area.landmarks.reference_input import (
    ReferenceInput,
    load_reference_input,
    read_frame_rgb,
)
from tools.build_landmarks import OUTPUT_FILE

PHOTO_WIDTH = 960
GIF_WIDTH = 640
POINT_RADIUS = 1.5
POINT_COLOR = (0, 255, 0)
FONT = ImageFont.load_default(size=18)


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/draw_landmarks.py <샘플 폴더>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    reference = load_reference_input(folder)
    result = LandmarksResult.model_validate_json((folder / OUTPUT_FILE).read_text(encoding="utf-8"))
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}

    points_dir = folder / OUTPUT_FILE.parent / "points"
    points_dir.mkdir(parents=True, exist_ok=True)
    gif_frames = []
    for row in result.frames:
        photo = _open_photo(reference, frames[row.frame_index])
        _draw(photo, row, PHOTO_WIDTH).save(points_dir / f"{row.frame_index:06d}.png")
        gif_frames.append(_draw(photo, row, GIF_WIDTH))

    gif_path = folder / OUTPUT_FILE.parent / "landmarks.gif"
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=_durations(result.frames),
        loop=0,
    )
    print(f"점 찍은 사진 {len(result.frames)}장: {points_dir}")
    print(f"GIF: {gif_path}")


def _open_photo(reference: ReferenceInput, frame: Frame) -> Image.Image:
    """사진을 연다. 열리지 않으면 같은 크기의 검은 화면으로 대신한다."""
    try:
        return Image.fromarray(read_frame_rgb(reference, frame))
    except (AppError, OSError):
        return Image.new("RGB", (frame.width, frame.height))


def _draw(photo: Image.Image, row: FrameLandmarks, width: int) -> Image.Image:
    """사진을 가로 width로 줄이고, 점 478개와 상태 글씨를 그린다."""
    height = round(photo.height * width / photo.width)
    image = photo.resize((width, height))
    draw = ImageDraw.Draw(image)

    if row.face is not None:
        r = POINT_RADIUS
        for point in row.face.landmarks:
            x, y = point.x * width, point.y * height
            draw.ellipse((x - r, y - r, x + r, y + r), fill=POINT_COLOR)

    label = f"{row.timestamp_ms / 1000:.1f}s  {row.status}  faces {row.face_count}"
    if row.reasons:
        label += "  " + ",".join(row.reasons)
    left, top, right, bottom = draw.textbbox((8, 6), label, font=FONT)
    draw.rectangle((left - 4, top - 3, right + 4, bottom + 3), fill="white")
    draw.text((8, 6), label, fill="black", font=FONT)
    return image


def _durations(rows: list[FrameLandmarks]) -> list[int]:
    """GIF 한 장을 보여 줄 시간(ms). 다음 사진과의 시각 차이라서 실제 속도로 움직인다."""
    times = [row.timestamp_ms for row in rows]
    gaps = [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
    return [*gaps, gaps[-1] if gaps else 1000]


if __name__ == "__main__":
    main()
