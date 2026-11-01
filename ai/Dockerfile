# AI 서버 이미지: FastAPI(uvicorn). 얼굴 모델을 레포 루트의 shared/face-mesh/ 에서 읽어 레포와 같은 폴더 모양으로 담는다.
# 빌드는 레포 루트에서:  docker build -f ai/Dockerfile -t mairor-ai .
# 베이스와 시스템 패키지는 CI(ci/ai.yml)와 같다. 뺄 것은 옆의 Dockerfile.dockerignore 에 있다.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# MediaPipe·OpenCV 가 쓰는 시스템 라이브러리
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /repo/ai

# 의존성만 먼저 설치해 두면 코드만 바뀐 빌드는 이 층을 다시 쓴다. 개발용(dev)은 넣지 않는다
COPY ai/pyproject.toml ai/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

COPY shared/ /repo/shared/
COPY ai/app/ app/

USER app
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
