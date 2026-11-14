"""부위 지도 함수를 모델 방식으로 바꾼 채 서비스 코드로 샘플 폴더의 가이드 영역을 만든다(개발용).

model_area.install로 바꾼 뒤 tools/build_guide_area.py와 같은 흐름으로 만들고, 결과를
output/guide_area_<이름>.json에 둔다(서비스 그대로인 output/guide_area.json은 덮지 않는다).
eval_real.py·eval_fallback.py가 --area <이름>으로 이 파일을 읽는다.
실행 (ai/ 폴더에서):
  uv run --no-sync python tools/guide_area_training/build_with_method.py <onnx> \
    rule|model|and|or|rule_gate|model_gate <이름> <샘플 폴더> [<샘플 폴더> ...] [--each-side]
rule은 판정을 바꾸지 않는다(규칙에 --each-side만 견줄 때, onnx 자리는 아무 값).
--each-side를 주면 짝 부위 좌우 맞추기를 끄고 쪽마다 찾은 모양을 쓴다(model_area.install_each_side).
환경 변수 A306_STORE가 있으면 모델 결과를 그 폴더에 남겨 다른 방식 실행이 다시 쓴다.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import model_area  # noqa: E402

from app.schemas.landmarks import LandmarksResult  # noqa: E402
from app.tasks.area.landmarks.occlusion import remember_by_frame  # noqa: E402
from app.tasks.area.landmarks.occlusion_finder import find_occlusion  # noqa: E402
from app.tasks.area.landmarks.reference_input import (  # noqa: E402
    load_reference_input,
    read_frame_rgb,
)
from app.tasks.area.parts.area_preparation import RememberedPhotos  # noqa: E402
from app.tasks.area.reference_area import FACE_MAP_KEEP, OCCLUSION_KEEP  # noqa: E402
from tools.build_guide_area import CHECKED_FILE, guide_steps  # noqa: E402


def build(folder: Path, name: str) -> Path:
    from app.tasks.area.guide_area_builder import build_guide_area

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(
        (folder / CHECKED_FILE).read_text(encoding="utf-8")
    )
    area = build_guide_area(
        reference.manifest.video_id,
        guide_steps(folder, reference.manifest.steps),
        result,
        RememberedPhotos(
            lambda row: read_frame_rgb(reference, frames[row.frame_index]), FACE_MAP_KEEP
        ),
        occlusion=remember_by_frame(find_occlusion, OCCLUSION_KEEP),
    )
    path = folder / "output" / f"guide_area_{name}.json"
    path.write_text(area.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    for step in area.steps:
        for sub in step.sub_steps:
            reasons = ",".join(sub.reasons)
            print(f"{folder.name} {sub.sub_step_id} {step.makeup}: {sub.status} {reasons}")
    return path


def main() -> None:
    args = sys.argv[1:]
    each = "--each-side" in args
    args = [arg for arg in args if arg != "--each-side"]
    if len(args) < 4:
        raise SystemExit(__doc__)
    model, method, name, folders = Path(args[0]), args[1], args[2], [Path(a) for a in args[3:]]
    store = os.environ.get("A306_STORE")
    if method != "rule":
        model_area.install(method, model, 4, Path(store) if store else None)
    if each:
        model_area.install_each_side()
    for folder in folders:
        print(f"저장: {build(folder, name)}")


if __name__ == "__main__":
    main()
