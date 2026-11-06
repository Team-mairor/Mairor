package com.mairor.backend.common.external.youtube;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * YouTube Data API v3 호출 설정 ({@code app.youtube}).
 *
 * @param baseUrl API 주소
 * @param apiKey 키. 비어 있으면 호출이 {@code NOT_CONFIGURED}로 실패한다(앱은 뜬다). 운영은 Parameter Store {@code
 *     YOUTUBE_API_KEY}
 * @param connectTimeout 연결 시간 제한
 * @param readTimeout 답을 기다리는 시간
 * @param regionCode 검색 지역(관련도 계산에 쓰인다)
 * @param relevanceLanguage 검색 언어
 * @param searchCacheTtl 같은 검색어 · 페이지 결과를 다시 쓰는 시간. 검색 1번이 하루 할당량 10,000 중 100 을 쓴다
 * @param searchCacheSize 검색 캐시에 담는 최대 개수
 */
@ConfigurationProperties(prefix = "app.youtube")
public record YouTubeProperties(
    @DefaultValue("https://www.googleapis.com/youtube/v3") String baseUrl,
    String apiKey,
    @DefaultValue("3s") Duration connectTimeout,
    @DefaultValue("5s") Duration readTimeout,
    @DefaultValue("KR") String regionCode,
    @DefaultValue("ko") String relevanceLanguage,
    @DefaultValue("10m") Duration searchCacheTtl,
    @DefaultValue("500") int searchCacheSize) {

  public boolean configured() {
    return apiKey != null && !apiKey.isBlank();
  }
}
