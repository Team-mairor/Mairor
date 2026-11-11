"""코드 밖 파일의 위치. 모듈을 옮겨도 경로가 바뀌지 않게 여기서만 정한다."""

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
AI_DIR = APP_DIR.parent
PROMPTS_DIR = APP_DIR / "prompts"
RESOURCES_DIR = APP_DIR / "resources"
WEIGHTS_DIR = APP_DIR / "weights"
FACE_MESH_DIR = AI_DIR.parent / "shared" / "face-mesh"
CATALOG_IMPORT_DIR = AI_DIR.parent / "shared" / "catalog-import"
DEFAULT_CATALOG_RUN_DIR = AI_DIR / "catalog-runs"
DEFAULT_CATALOG_SITES_DIR = AI_DIR / "catalog-sites"
