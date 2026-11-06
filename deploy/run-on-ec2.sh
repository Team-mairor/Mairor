#!/usr/bin/env bash
# CI 의 deploy · rollback 잡이 EC2 한 대에 배포 명령을 보내고 끝날 때까지 기다린다(SSM Run Command, 22번 없음).
#   deploy/run-on-ec2.sh deploy <태그> <be|ai>     ECR 의 mairor-deploy:<태그> 에서 배포 파일을 꺼내 그 서버의 배포 스크립트 <태그>
#   deploy/run-on-ec2.sh rollback <태그> <be|ai>   같은 순서로 그 서버의 되돌리기 스크립트 <태그>
# 서버: be = mairor-app(deploy.sh · rollback.sh), ai = mairor-ai(deploy-ai.sh · rollback-ai.sh). S15P31A306-356
# 필요한 환경변수: EC2_INSTANCE_ID(be) · AI_EC2_INSTANCE_ID(ai), AWS 자격(CI 변수, IAM 사용자 mairor-ci-deploy), AWS_DEFAULT_REGION.
# 서버 출력은 잡 로그에 그대로 찍고, 서버에서 실패하면 이 스크립트도 실패(종료 코드 1)한다.
set -euo pipefail

ACTION="${1:?사용법: run-on-ec2.sh <deploy|rollback> <태그> <be|ai>}"
TAG="${2:?사용법: run-on-ec2.sh <deploy|rollback> <태그> <be|ai>}"
SERVER="${3:?사용법: run-on-ec2.sh <deploy|rollback> <태그> <be|ai>}"
REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
RUN_SECONDS=1200 # 서버에서 명령이 돌 수 있는 최대 시간. 롤링 배포는 보통 3 ~ 5분

case "$SERVER" in
  be)
    INSTANCE="${EC2_INSTANCE_ID:?EC2_INSTANCE_ID 가 없다(CI 변수)}"
    DEPLOY_SCRIPT=deploy.sh
    ROLLBACK_SCRIPT=rollback.sh
    ;;
  ai)
    INSTANCE="${AI_EC2_INSTANCE_ID:?AI_EC2_INSTANCE_ID 가 없다(CI 변수)}"
    DEPLOY_SCRIPT=deploy-ai.sh
    ROLLBACK_SCRIPT=rollback-ai.sh
    ;;
  *)
    echo "서버는 be 또는 ai 만 받는다: $SERVER" >&2
    exit 1
    ;;
esac

case "$ACTION" in
  deploy) SCRIPT=$DEPLOY_SCRIPT ;;
  rollback) SCRIPT=$ROLLBACK_SCRIPT ;;
  *)
    echo "deploy 또는 rollback 만 받는다: $ACTION" >&2
    exit 1
    ;;
esac
# 태그는 서버 명령에 그대로 들어가므로 커밋 해시 모양만 받는다
if ! [[ "$TAG" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "태그는 커밋 해시(16진수 7 ~ 40자)여야 한다: $TAG" >&2
  exit 1
fi

# EC2 에서 root 로 돈다. ECR 로그인 → 이 태그의 배포 파일 이미지에서 compose · 스크립트를 꺼내 /opt/mairor 에 → 실행.
# 배포 파일이 앱 이미지와 같은 태그라, 되돌릴 때도 그 시점의 compose 로 돌아간다(-203 5-12)
remote=$(
  cat <<EOF
set -euo pipefail
export HOME=/root PATH=/usr/local/bin:/usr/bin:/bin:\$PATH
REG=\$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$REGION.amazonaws.com
aws ecr get-login-password --region $REGION | docker login -u AWS --password-stdin "\$REG" >/dev/null
docker pull -q "\$REG/mairor-deploy:$TAG" >/dev/null
id=\$(docker create "\$REG/mairor-deploy:$TAG")
docker cp "\$id:/deploy/." /opt/mairor/
docker rm "\$id" >/dev/null
/opt/mairor/$SCRIPT $TAG
EOF
)
# 따옴표가 섞인 스크립트를 JSON 매개변수에 그대로 실으면 깨지므로 base64 로 보낸다
b64=$(printf '%s\n' "$remote" | base64 | tr -d '\n')

command_id=$(aws ssm send-command \
  --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript \
  --comment "mairor $ACTION $TAG $SERVER pipeline ${CI_PIPELINE_ID:-manual}" \
  --parameters "{\"commands\":[\"echo $b64 | base64 -d | bash\"],\"executionTimeout\":[\"$RUN_SECONDS\"]}" \
  --query Command.CommandId --output text)
echo "SSM 명령 $command_id: $ACTION $TAG ($SERVER 서버 $INSTANCE)"

invocation() { # invocation <조회할 칸>
  aws ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE" --query "$1" --output text
}

status=Pending
waited=0
while [ "$waited" -le $((RUN_SECONDS + 60)) ]; do
  sleep 10
  waited=$((waited + 10))
  # 보낸 직후에는 실행 기록이 아직 없다고 나올 수 있어 그때는 대기로 본다
  status=$(invocation Status 2>/dev/null) || status=Pending
  case "$status" in
    Pending | InProgress | Delayed | Cancelling) ;;
    *) break ;;
  esac
done

echo "----- $SERVER 서버 출력 -----"
invocation StandardOutputContent || true
errors=$(invocation StandardErrorContent 2>/dev/null || true)
if [ -n "$errors" ] && [ "$errors" != None ]; then
  # docker login 의 "credentials are stored unencrypted" 경고도 여기 나온다. 결과는 아래 상태로 판단한다
  echo "----- 서버 오류 출력(경고 포함) -----"
  echo "$errors"
fi
echo "---------------------"
echo "결과: $SERVER $status (${waited}초)"
[ "$status" = Success ]
