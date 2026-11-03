"""코드 밖 파일의 위치. 모듈을 옮겨도 경로가 바뀌지 않게 여기서만 정한다."""

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
AI_DIR = APP_DIR.parent
PROMPTS_DIR = APP_DIR / "prompts"
FACE_MESH_DIR = AI_DIR.parent / "shared" / "face-mesh"
