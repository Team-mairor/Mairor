# 빌드는 레포 루트에서:  docker build -f frontend/Dockerfile -t mairor-nginx .
# FE 빌드가 ../shared 를 읽으므로 레포 루트가 재료다. 뺄 것은 옆의 Dockerfile.dockerignore 에 있다.

FROM node:24 AS build
WORKDIR /repo
COPY shared/ shared/
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend/ frontend/
# DEV_TOOLS=1: 배포본에도 확인 화면(/debug)을 넣는다. 운영에서 빼려면 이 값과 ci/frontend.yml의 값을 지운다.
ARG NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION=false
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_BASE_URL=/api \
    NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION=${NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION} \
    DEV_TOOLS=1
RUN cd frontend && npm run build

FROM nginx:1.27-alpine
COPY --from=build /repo/frontend/out /usr/share/nginx/html
COPY frontend/nginx/static.conf /etc/nginx/conf.d/default.conf
COPY frontend/nginx/api.conf /etc/nginx/snippets/api.conf
EXPOSE 80
