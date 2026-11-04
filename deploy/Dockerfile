# 배포 파일 이미지(mairor-deploy): EC2 가 레포 없이 배포 파일을 받게 한다. 앱 이미지와 같은 커밋 태그로 올린다.
# 빌드는 레포 루트에서:  docker build -f deploy/Dockerfile -t mairor-deploy .
# EC2 는 이 이미지를 받아 /deploy/ 를 /opt/mairor 로 꺼낸 뒤 deploy.sh 를 실행한다(deploy/README.md).
FROM busybox:1.37
COPY docker-compose.prod.yml /deploy/
COPY infra/alloy/config.alloy /deploy/alloy.alloy
COPY --chmod=755 deploy/deploy.sh deploy/rollback.sh /deploy/
