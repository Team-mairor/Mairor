package com.mairor.backend.common.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 내부 API({@code /v1/internal/**}) 공유 토큰 ({@code app.internal.token}, 환경변수 {@code
 * INTERNAL_API_TOKEN}).
 *
 * <p>운영자 명령과 AI 서버 콜백이 {@code X-Internal-Token} 헤더로 보낸다. 비어 있으면 내부 API 는 모든 요청을 401 로 거절한다(설정을 빠뜨려
 * 열리는 일이 없게). 앱 기동은 막지 않는다.
 */
@ConfigurationProperties(prefix = "app.internal")
public record InternalApiProperties(String token) {

  public boolean configured() {
    return token != null && !token.isBlank();
  }
}
