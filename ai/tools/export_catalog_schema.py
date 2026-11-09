"""CollectedProduct 모델에서 JSON Schema를 만들어 shared/catalog-import에 쓴다.

모델을 바꾸면 이 도구를 다시 돌려 파일을 갱신한다. tests/catalog/test_contract.py가 파일과 모델이
같은지 확인한다. 계약을 바꿀 때는 contractVersion을 올리고 README와 샘플도 함께 고친다.

    uv run python tools/export_catalog_schema.py
"""

import json
import sys
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR))

from app.core.paths import CATALOG_IMPORT_DIR  # noqa: E402
from app.tasks.catalog.contract import collected_product_schema  # noqa: E402

SCHEMA_FILE = CATALOG_IMPORT_DIR / "collected_product.v1.schema.json"


def render() -> str:
    return json.dumps(collected_product_schema(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    SCHEMA_FILE.write_text(render(), encoding="utf-8", newline="\n")
    print(f"썼습니다: {SCHEMA_FILE}")


if __name__ == "__main__":
    main()
