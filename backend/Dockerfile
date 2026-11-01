# BE 이미지: Spring Boot 실행 jar 와 ffmpeg(영상 프레임 추출, 5B). api·worker 가 같은 이미지를 쓴다.
# 빌드는 레포 루트에서:  docker build -f backend/Dockerfile -t mairor-backend .
# 세 이미지의 빌드 명령을 같게 하려고 레포 루트를 재료로 한다. 뺄 것은 옆의 Dockerfile.dockerignore 에 있다.

# 1단계: 실행 jar 만들기. 의존성을 먼저 받아 두면 코드만 바뀐 빌드는 이 층을 다시 쓴다
FROM eclipse-temurin:21-jdk AS build
WORKDIR /repo/backend
COPY backend/gradlew backend/settings.gradle backend/build.gradle backend/gradle.properties ./
COPY backend/gradle/ gradle/
RUN chmod +x gradlew && ./gradlew --no-daemon dependencies > /dev/null
COPY backend/src/ src/
RUN ./gradlew --no-daemon bootJar \
    && find build/libs -name '*.jar' ! -name '*-plain.jar' -exec cp {} /app.jar \;

# 2단계: JRE 와 ffmpeg 위에 jar 만 담는다 (JDK·Gradle 은 버린다)
FROM eclipse-temurin:21-jre
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=build /app.jar app.jar
USER app
# 컨테이너 메모리 상한(compose)의 75%를 힙으로 쓴다
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75"
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
