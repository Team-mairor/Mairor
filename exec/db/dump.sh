#!/usr/bin/env bash
# 운영 DB 덤프. BE 서버(mairor-app)에서 root 로 실행한다(Session Manager → sudo -i).
#   bash dump.sh
# pg_dump 는 읽기만 한다. 결과는 /tmp/mairor-<날짜>.dump (custom 형식, 개인정보 그대로).
# 제출본은 로컬에서 복원 → exec/db/README.md "개인정보 가림" 적용 → 일반 SQL 로 다시 덤프한다.
# 원본은 쓰고 나면 지운다.
set -euo pipefail

cd /opt/mairor
set -a
. ./app.env # deploy.sh 가 Parameter Store /mairor/prod/* 로 만든 파일
set +a

u=${DB_URL#jdbc:postgresql://}
hp=${u%%/*}
db=${u#*/}
db=${db%%\?*}
host=${hp%%:*}
port=${hp##*:}
[ "$port" = "$hp" ] && port=5432

f=mairor-$(date +%Y%m%d-%H%M).dump
docker run --rm -e PGPASSWORD="$DB_PASSWORD" -v /tmp:/out postgres:17 \
  pg_dump -h "$host" -p "$port" -U "$DB_USERNAME" -d "$db" \
  --no-owner --no-privileges -Fc -f "/out/$f"

ls -lh "/tmp/$f"
