package com.mairor.backend.common.external.llm;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Gemini 호출 설정 ({@code app.llm.gemini}). GMS 와 Google 직접 호출은 요청 형식이 같아 주소와 키만 바꾼다.
 *
 * @param baseUrl {@code https://generativelanguage.googleapis.com} 또는 GMS 의 Gemini 주소
 * @param apiKey 키. 비어 있으면 호출이 {@code NOT_CONFIGURED}로 실패한다(앱은 뜬다)
 * @param apiKeyHeader 키를 싣는 헤더
 * @param model 모델 이름
 * @param connectTimeout 연결 시간 제한
 * @param readTimeout 답을 기다리는 시간. 30분 영상은 몇 분 걸린다
 * @param maxAttempts 재시도를 포함한 최대 호출 횟수(429·5xx·연결 실패만 다시 부른다)
 * @param retryBackoff 첫 재시도 전 대기. 다음부터 두 배씩
 */
@ConfigurationProperties(prefix = "app.llm.gemini")
public record GeminiProperties(
    @DefaultValue("https://generativelanguage.googleapis.com") String baseUrl,
    String apiKey,
    @DefaultValue("x-goog-api-key") String apiKeyHeader,
    @DefaultValue("gemini-2.5-flash") String model,
    @DefaultValue("10s") Duration connectTimeout,
    @DefaultValue("10m") Duration readTimeout,
    @DefaultValue("3") int maxAttempts,
    @DefaultValue("5s") Duration retryBackoff) {

  public boolean configured() {
    return apiKey != null && !apiKey.isBlank();
  }

  /** {@code llm_calls.provider}에 남길 이름. */
  public String provider() {
    return baseUrl.contains("gms.ssafy.io") ? "GMS" : "GOOGLE";
  }
}
