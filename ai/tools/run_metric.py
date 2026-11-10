"""지표 도구 하나를 서비스 기준값을 바꿔(--set) 돌리는 빠른 판이다 (개발용).

--set으로 받은 상수를 먼저 바꾸고 그다음 도구를 불러 main을 부른다. 도구는 불러올 때 일부 상수를
부위 표에 복사하므로, 이 순서여야 도구와 서비스 찾기가 같은 값을 쓴다(tools/metric_settings.py).
--set을 주면 --tag도 줘야 하고, 결과는 그 이름 폴더에 따로 두며 바꾼 상수를 settings.json에 적는다.
사진 지도·대표 지도 저장(tools/face_map_store.py)을 그대로 쓰므로, 판정 기준만 바꾼 다시 재기는
사진 펴기와 대표 지도 만들기 없이 바뀐 색 계산과 판정만 한다.

실행 (ai/ 폴더에서):
uv run python tools/run_metric.py <noise|stability|timing|boundary|scorecard> <샘플 폴더>
    [도구 인자...] [--set <모듈>.<상수>=<값> ...] [--tag <이름>]
예: uv run python tools/run_metric.py noise samples/local_03_seq --occlusion after334
    --set eyeshadow_area.REDDENING_MIN=1.2 --tag shadow12
"""

import importlib
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from tools.metric_settings import (
    SETTINGS_USAGE,
    apply_settings,
    split_settings,
    split_tag,
    tagged_dir,
    write_settings,
)
from tools.occlusion_tables import output_dir, split_occlusion

TOOLS = {
    "noise": "noise_metric",
    "stability": "stability_metric",
    "timing": "timing_metric",
    "boundary": "boundary_metric",
    "scorecard": "guide_scorecard",
}
USAGE = (
    f"사용법: uv run python tools/run_metric.py <{'|'.join(TOOLS)}> <샘플 폴더> [도구 인자...]"
    f" {SETTINGS_USAGE}"
)


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in TOOLS:
        print(USAGE)
        sys.exit(1)
    tool, args = sys.argv[1], sys.argv[2:]
    args, texts = split_settings(args)
    _, tag = split_tag(args)
    if texts and tag is None:
        raise SystemExit("--set을 주면 기준 결과를 덮지 않게 --tag <이름>도 줘야 합니다")
    settings = apply_settings(texts)
    module = importlib.import_module(f"tools.{TOOLS[tool]}")
    saved = sys.argv
    sys.argv = [f"tools/{TOOLS[tool]}.py", *args]
    try:
        module.main()
    finally:
        sys.argv = saved
    if tag is not None:
        rest, occlusion_name = split_occlusion(args)
        rest, _ = split_tag(rest)
        folder = tagged_dir(output_dir(Path(rest[0]), occlusion_name), tag)
        print(f"설정: {write_settings(folder, tool, args, settings)}")


if __name__ == "__main__":
    main()
