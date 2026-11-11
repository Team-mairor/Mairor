#!/usr/bin/env bash
# DB 자격은 app.env로만 전달하며 출력하지 않는다. 기존 슬롯을 바꾸기 전에 실행한다.
set -euo pipefail
BASE="${MAIROR_DEPLOY_BASE:-/opt/mairor}"
docker run --rm --network host \
  --env-file "$BASE/app.env" \
  -v "$BASE/check-camera-schema.sql:/check.sql:ro" \
  postgres:17 sh -ec '
    export PGPASSWORD="$DB_PASSWORD"
    exec psql "${DB_URL#jdbc:}" -U "$DB_USERNAME" -v ON_ERROR_STOP=1 -f /check.sql
  '
