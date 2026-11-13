package com.mairor.backend.products.collect;

import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * DB 에 없는 화장품 자동 수집 설정({@code catalog.collect}).
 *
 * @param enabled 끄면 직접 입력 등록 뒤 수집 요청을 만들지 않는다
 * @param types 자동 수집하는 소분류. 확정된 허용 목록만 둔다(미확정 COMPACT·LIP_BALM·POWDER 와 매칭 제외 소분류는 넣지 않는다)
 * @param dailyLimitPerUser 회원 한 명이 최근 24시간에 만들 수 있는 요청 수. 넘으면 조용히 만들지 않는다
 * @param retryAfter 찾은 제품이 없거나({@code SEARCH_EMPTY}) 부족 정보가 풀리지 않은 요청과 같은 제품은 이 시간 동안 다시 요청하지 않는다
 * @param queueUrl 수집 큐(SQS) 주소. 비우면 큐에 보내지 않고 요청은 QUEUED 로 남는다(로컬·테스트)
 * @param queueRegion 수집 큐 리전
 * @param maxSendAttempts 큐에 보내기를 이만큼 실패하면 요청을 FAILED({@code SEND_FAILED})로 끝낸다
 * @param resultTimeout 큐에 보낸 뒤 이 시간 안에 워커 결과가 없으면 FAILED({@code RESULT_TIMEOUT})로 끝낸다. 워커 재시도(받은 횟수
 *     3번)와 태스크가 뜨는 시간까지 넉넉히 둔다
 */
@ConfigurationProperties(prefix = "catalog.collect")
public record CatalogCollectProperties(
    @DefaultValue("true") boolean enabled,
    @DefaultValue({
          "CUSHION",
          "FOUNDATION",
          "BASE_STICK",
          "CONCEALER",
          "EYESHADOW_PALETTE",
          "EYELINER",
          "MASCARA",
          "BROW_PENCIL",
          "BLUSHER",
          "HIGHLIGHTER",
          "LIPSTICK",
          "LIP_TINT",
          "LIQUID_LIP",
          "LIP_GLOSS"
        })
        List<String> types,
    @DefaultValue("20") int dailyLimitPerUser,
    @DefaultValue("24h") Duration retryAfter,
    @DefaultValue("") String queueUrl,
    @DefaultValue("ap-northeast-2") String queueRegion,
    @DefaultValue("20") int maxSendAttempts,
    @DefaultValue("6h") Duration resultTimeout) {

  public CatalogCollectProperties {
    types = List.copyOf(types);
    if (dailyLimitPerUser < 0) {
      throw new IllegalArgumentException("catalog.collect.daily-limit-per-user 는 0 이상이다");
    }
  }

  public boolean queueEnabled() {
    return queueUrl != null && !queueUrl.isBlank();
  }

  public Set<String> typeSet() {
    return Set.copyOf(types);
  }
}
