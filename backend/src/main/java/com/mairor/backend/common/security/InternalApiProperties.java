package com.mairor.backend.common.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 내부 API({@code /v1/internal/**}) 공유 토큰 ({@code app.internal.token}, 환경변수 {@code
 * INTERNAL_API_TOKEN}).
 *
 * <p>카탈로그 적재 · 수집 결과처럼 서버끼리 부르는 내부 API 와 운영자의 카탈로그 확인(수집 요청 조회)이 {@code X-Internal-Token} 헤더로 보낸다.
 * 비어 있으면 내부 API 는 모든 요청을 401 로 거절한다(설정을 빠뜨려 열리는 일이 없게). 앱 기동은 막지 않는다.
 */
@ConfigurationProperties(prefix = "app.internal")
public record InternalApiProperties(String token) {

  public boolean configured() {
    return token != null && !token.isBlank();
  }
}
