# FE 이미지: Next.js 정적 결과물(out/)을 nginx로 내준다. 운영에서는 이 nginx가 /api 를 Spring으로 넘긴다.
# 빌드는 레포 루트에서:  docker build -f frontend/Dockerfile -t mairor-nginx .
# FE 빌드가 ../shared 를 읽으므로 레포 루트가 재료다. 뺄 것은 옆의 Dockerfile.dockerignore 에 있다.

# 1단계: 정적 파일 만들기
FROM node:24 AS build
WORKDIR /repo
COPY shared/ shared/
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend/ frontend/
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_BASE_URL=/api
RUN cd frontend && npm run build

# 2단계: nginx 에 결과물과 설정만 담기 (Node·node_modules 는 버린다)
FROM nginx:1.27-alpine
COPY --from=build /repo/frontend/out /usr/share/nginx/html
COPY frontend/nginx/static.conf /etc/nginx/conf.d/default.conf
COPY frontend/nginx/api.conf /etc/nginx/snippets/api.conf
EXPOSE 80
