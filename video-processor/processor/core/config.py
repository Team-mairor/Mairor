"""인증값, S3 업로드·GMS 호출 설정."""

from pathlib import Path

from processor.core.paths import PROCESSOR_DIR, REPO_ROOT


def load_credentials():
    """
    1. video-processor/.env 우선 탐색
    2. c:/Users/SSAFY/jiwon/.env 탐색
    3. REPO_ROOT / .env 또는 ai / .env 탐색
    """
    creds = {
        "aws_region": "ap-northeast-2",
        "s3_bucket": "mairor-test-299284685316-ap-northeast-2-an",
        "aws_access_key": None,
        "aws_secret_key": None,
        "gms_api_key": None,
    }

    env_candidates = [
        PROCESSOR_DIR / ".env",
        Path("c:/Users/SSAFY/jiwon/.env"),
        REPO_ROOT / ".env",
        REPO_ROOT / "ai" / ".env",
    ]

    for env_path in env_candidates:
        try:
            if not env_path.exists():
                continue
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "AWS_REGION":
                    creds["aws_region"] = v
                elif k == "S3_BUCKET":
                    creds["s3_bucket"] = v
                elif k == "AWS_ACCESS_KEY_ID":
                    creds["aws_access_key"] = v
                elif k == "AWS_SECRET_ACCESS_KEY":
                    creds["aws_secret_key"] = v
                elif k == "GMS_API_KEY":
                    creds["gms_api_key"] = v

    return creds


CREDS = load_credentials()

# 지금 네트워크는 새 연결을 동시에 많이 열면 연결마다 1초 단위로 밀린다 (25개 동시 2~4초, 100개 최대 87초).
# 8프로세스 x 25스레드(연결 최대 200개)로 올리면 343장에 80초, 클라이언트 1개 x 연결 16개는 1.6초였다.
UPLOAD_CONNECTIONS = 16
# 쉬는 연결은 5~6초 만에 끊기므로 업로드 전까지 그보다 짧은 간격으로 연결을 계속 써 둔다
WARM_PING_INTERVAL = 2.0

# GMS Gemini 한도는 다른 사용자와 같이 쓰는 것으로 보여 숫자를 알 수 없다(첫 429 직전 1분에 보낸 요청이 0~29개로
# 들쭉날쭉). 한꺼번에 몰아 보내지 않게 시작 간격을 1~1.5초로 무작위로 벌리고 동시에 8개까지만 보낸다.
GMS_MIN_INTERVAL = 1.0
GMS_START_JITTER = 0.5
GMS_MAX_IN_FLIGHT = 8

# 버킷이 공개가 아니라 AI 서버가 사진 주소를 그냥 내려받으면 403이다. 요청에는 서명한 주소를 넣는다(BE도 같음, 24시간).
# 처리기 요청은 AI 쪽이 나중에 받아 쓰므로 서명 주소의 최대 유효 기간인 7일로 둔다.
FRAME_URL_TTL_SECONDS = 7 * 24 * 3600
