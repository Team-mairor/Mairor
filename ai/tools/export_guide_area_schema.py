"""가이드 영역 모델(GuideArea)에서 FE·BE와 함께 쓰는 JSON Schema를 만든다.

실행 (ai/ 폴더에서):
  uv run python tools/export_guide_area_schema.py     결과 → shared/guide-area/

guide_area.py의 모델을 고치면 다시 실행한다. 안 하면 tests/test_guide_area_schema.py가 실패한다.
SCHEMA_VERSION은 이미 만든 결과가 거절되는 변경일 때 올린다 (shared/guide-area/README.md).
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import GuideArea

SCHEMA_VERSION = "v1"
SCHEMA_DIR = AI_ROOT.parent / "shared" / "guide-area"
SCHEMA_PATH = SCHEMA_DIR / f"guide_area.{SCHEMA_VERSION}.schema.json"
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def build_schema() -> dict:
    return {"$schema": DIALECT} | GuideArea.model_json_schema()


def main() -> None:
    text = json.dumps(build_schema(), ensure_ascii=False, indent=2) + "\n"
    old = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else None
    if old is not None and json.loads(old) == json.loads(text):
        print(f"{SCHEMA_PATH.name} 그대로입니다")
        return
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"{SCHEMA_PATH.name}을 {'새로 만들었습니다' if old is None else '고쳤습니다'}")


if __name__ == "__main__":
    main()
