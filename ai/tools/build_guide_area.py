"""샘플 폴더의 단계마다 도포 영역을 채워 output/guide_area.json으로 저장한다 (개발용).

사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
서비스와 같게 가림 찾기 모델로 사진마다 가린 칸을 빼고 만든다.
서비스와 같게 편 지도를 기억해(RememberedPhotos), 흐린 사진을 잴 때 편 지도를 다시 쓴다.
샘플 폴더에 BE 형식 가이드 입력(guide_input.json)이 있으면 그 단계로 만든다(guide_steps).
찾은 영역마다 뽑은 대표 색은 output/area_colors.json에 따로 저장한다. 가이드 영역에는 하위 단계마다
그중 하나를 고른 게이지 기준(gauge)만 들어가고, 좌우 따로 낸 색·바르기 전 색은 이 파일에만 있다.
색 표와 견본 그림은 tools/area_color_report.py로 만든다.
실행 (ai/ 폴더에서): uv run python tools/build_guide_area.py samples/local_01_lip_seq
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide import GuideInput, GuideInputStep
from app.schemas.guide_area import GuideArea
from app.schemas.landmarks import LandmarksResult
from app.schemas.manifest import Step
from app.tasks.area.guide_area_builder import build_guide_area
from app.tasks.area.landmarks.occlusion import remember_by_frame
from app.tasks.area.landmarks.occlusion_finder import find_occlusion
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_color import recording_colors
from app.tasks.area.parts.area_preparation import RememberedPhotos
from app.tasks.area.reference_area import FACE_MAP_KEEP, OCCLUSION_KEEP

CHECKED_FILE = Path("output") / "frames_checked.json"
OUTPUT_FILE = Path("output") / "guide_area.json"
COLORS_FILE = Path("output") / "area_colors.json"
GUIDE_INPUT_FILE = "guide_input.json"


def guide_steps(folder: Path, manifest_steps: Sequence[Step]) -> list[Step] | list[GuideInputStep]:
    """영역을 만들 단계. 샘플 폴더에 guide_input.json이 있으면 그 단계, 없으면 매니페스트 단계다.

    서비스는 BE가 보낸 가이드 입력 단계로 영역을 만들고, 아이섀도 기본 가이드 키를 그 단계 글
    (partLabel·facts.area)로 고른다. 매니페스트 단계에는 글이 없어 늘 위아래 모두(eyeshadow)가
    되므로, 가이드 입력이 있으면 서비스와 같은 키가 나오게 그 단계를 쓴다.
    """
    path = folder / GUIDE_INPUT_FILE
    if not path.is_file():
        return list(manifest_steps)
    return GuideInput.model_validate_json(path.read_text(encoding="utf-8")).steps


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/build_guide_area.py <샘플 폴더>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    checked_path = folder / CHECKED_FILE
    if not checked_path.is_file():
        print(f"{checked_path}가 없습니다. 먼저 tools/check_frames.py를 실행하세요.")
        sys.exit(1)

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(checked_path.read_text(encoding="utf-8"))
    with recording_colors() as colors:
        area = build_guide_area(
            reference.manifest.video_id,
            guide_steps(folder, reference.manifest.steps),
            result,
            RememberedPhotos(
                lambda row: read_frame_rgb(reference, frames[row.frame_index]), FACE_MAP_KEEP
            ),
            occlusion=remember_by_frame(find_occlusion, OCCLUSION_KEEP),
        )
    path = save(area, folder)
    colors_path = save_colors(area, colors, folder)

    for step in area.steps:
        for sub_step in step.sub_steps:
            guides = [g for s in sub_step.guide_sets for g in s.guides]
            points = sum(len(g.outline) for g in guides if g.type == "polygon")
            arrows = sum(g.type == "arrow" for g in guides)
            detail = (
                f"테두리 점 {points}개, 화살표 {arrows}개"
                if points
                else ", ".join(sub_step.reasons) or "-"
            )
            print(f"{sub_step.sub_step_id} {step.makeup}: {sub_step.status} ({detail})")
    print(f"저장: {path}")
    print(f"저장: {colors_path}")


def save_colors(area: GuideArea, colors: dict[str, list[dict]], folder: Path) -> Path:
    """단계마다 뽑은 색 기록을 <샘플 폴더>/output/area_colors.json에 저장하고 경로를 돌려준다.

    colors는 빌더가 단계 ID별로 모은 색 기록(area_color.recording_colors)이다.
    단계 순서대로 stepId·makeup·colors를 적고, 색을 뽑지 않은 단계는 colors가 빈 목록이다.
    """
    steps = [
        {"stepId": step.step_id, "makeup": step.makeup, "colors": colors.get(step.step_id, [])}
        for step in area.steps
    ]
    path = folder / COLORS_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps({"videoId": area.video_id, "steps": steps}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def save(area: GuideArea, folder: Path) -> Path:
    """결과를 <샘플 폴더>/output/guide_area.json에 camelCase로 저장하고 경로를 돌려준다.

    FE·BE와 함께 보는 샘플이라 들여쓰기 2칸으로 줄을 나눠 저장한다.
    """
    path = folder / OUTPUT_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(area.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    main()
