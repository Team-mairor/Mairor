package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.analysis.controller.AiCallbackController;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

/**
 * AI 콜백({@code /api/v1/internal/ai/})은 공유 토큰 없이 받으므로 바깥에서 막혀 있어야 한다. 막는 곳은 nginx 설정({@code
 * frontend/nginx/api.conf}, BE 관리)이라, 그 줄이 빠지면 여기서 잡는다.
 */
class NginxInternalRouteTest {

  private static final Path API_CONF = Path.of("../frontend/nginx/api.conf");

  @Test
  void aiCallbackPathIsClosedFromOutside() throws IOException {
    String conf = Files.readString(API_CONF);

    assertThat(conf)
        .containsPattern("location /api/v1/internal/ai/ \\{\\s*return 404;\\s*}")
        .as("일반 /api/ 경로도 그대로 있다")
        .contains("location /api/ {");
  }

  @Test
  void aiProgressPathIsUnderTheClosedAiPrefix() {
    // nginx 는 /api/v1/internal/ai/ 를 막고 context-path 는 /api 다. 진행 알림도 이 아래라야 바깥에서 막힌다
    assertThat("/api" + AiCallbackController.PROGRESS_PATH).startsWith("/api/v1/internal/ai/");
  }

  @Test
  void securityConfigSkipsTheTokenOnlyForTheAiCallback() {
    assertThat(SecurityConfig.AI_CALLBACK).isNotNull();
    assertThat(SecurityConfig.INTERNAL_TOKEN_REQUIRED).isNotNull();
  }
}
