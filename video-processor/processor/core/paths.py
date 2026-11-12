"""처리기 폴더와 파일 경로."""

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
PROCESSOR_DIR = PACKAGE_DIR.parent
REPO_ROOT = PROCESSOR_DIR.parent
TEMP_DIR = PROCESSOR_DIR / "temp"
DOWNLOAD_DIR = TEMP_DIR / "downloads"
JOBS_DIR = TEMP_DIR / "jobs"
PROMPTS_DIR = PACKAGE_DIR / "prompts"
GUIDE_REQUEST_SCHEMA = REPO_ROOT / "shared" / "guide-job" / "guide_job_request.v2.schema.json"
