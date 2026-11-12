"""CollectedProduct와 수집 작업(CollectJob·CollectJobResult) 모델에서 JSON Schema를 만들어
shared/catalog-import에 쓴다.

모델을 바꾸면 이 도구를 다시 돌려 파일을 갱신한다. tests/catalog/test_contract.py와
tests/catalog/test_jobs.py가 파일과 모델이 같은지 확인한다. 계약을 바꿀 때는 contractVersion을
올리고 README와 샘플도 함께 고친다.

    uv run python tools/export_catalog_schema.py
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR))

from app.core.paths import CATALOG_IMPORT_DIR  # noqa: E402
from app.tasks.catalog.contract import collected_product_schema  # noqa: E402
from app.tasks.catalog.jobs import (  # noqa: E402
    COLLECT_JOB_RESULT_SCHEMA_FILE,
    COLLECT_JOB_SCHEMA_FILE,
    collect_job_result_schema,
    collect_job_schema,
)

SCHEMA_FILE = CATALOG_IMPORT_DIR / "collected_product.v1.schema.json"
SCHEMAS: dict[Path, Callable[[], dict[str, Any]]] = {
    SCHEMA_FILE: collected_product_schema,
    CATALOG_IMPORT_DIR / COLLECT_JOB_SCHEMA_FILE: collect_job_schema,
    CATALOG_IMPORT_DIR / COLLECT_JOB_RESULT_SCHEMA_FILE: collect_job_result_schema,
}


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    for path, build in SCHEMAS.items():
        path.write_text(render(build()), encoding="utf-8", newline="\n")
        print(f"썼습니다: {path.name}")


if __name__ == "__main__":
    main()
