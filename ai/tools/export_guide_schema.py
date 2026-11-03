"""가이드 입력·작업 모델에서 BE와 함께 쓰는 JSON Schema를 만든다.

실행 (ai/ 폴더에서):
  uv run python tools/export_guide_schema.py     결과 → shared/guide-input/, shared/guide-job/

guide.py·guide_job.py의 모델을 고치면 다시 실행한다. 안 하면 tests/test_guide_schema.py가 실패한다.
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide import GuideInput
from app.schemas.guide_job import GuideJobRequest, GuideJobResult

SHARED = AI_ROOT.parent / "shared"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

# 파일 이름의 버전: BE가 보내던(받던) JSON이 거절되는 변경이면 올린다 (shared/guide-input/README.md)
GUIDE_INPUT_PATH = SHARED / "guide-input" / "guide_input.v2.schema.json"
GUIDE_JOB_REQUEST_PATH = SHARED / "guide-job" / "guide_job_request.v2.schema.json"
GUIDE_JOB_CALLBACK_PATH = SHARED / "guide-job" / "guide_job_callback.v1.schema.json"

SCHEMAS: dict[Path, tuple[type[BaseModel], str]] = {
    GUIDE_INPUT_PATH: (GuideInput, "validation"),
    GUIDE_JOB_REQUEST_PATH: (GuideJobRequest, "validation"),
    GUIDE_JOB_CALLBACK_PATH: (GuideJobResult, "serialization"),
}


def build_schema(path: Path) -> dict:
    model, mode = SCHEMAS[path]
    return {"$schema": DIALECT} | model.model_json_schema(mode=mode)


def write_schema(path: Path) -> None:
    text = json.dumps(build_schema(path), ensure_ascii=False, indent=2) + "\n"
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old is not None and json.loads(old) == json.loads(text):
        print(f"{path.name} 그대로입니다")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"{path.name}을 {'새로 만들었습니다' if old is None else '고쳤습니다'}")


def main() -> None:
    for path in SCHEMAS:
        write_schema(path)


if __name__ == "__main__":
    main()
