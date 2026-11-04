package com.mairor.backend.analysis.sse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 분석 상태 SSE 의 주기 작업: 빈 신호(ping)와 상태 맞추기. api 프로세스에서만 뜬다.
 *
 * <p>스케줄링을 여기서 직접 켠다. 지금 {@code @EnableScheduling}은 worker 와 만료 세션 정리에만 있는데, 운영 api-b 는 worker 가
 * 아니고 세션 정리도 꺼져 있어({@code SESSION_SWEEP_ENABLED=false}) 기존 설정에 기대면 api-b 에서 이 작업이 돌지 않는다. 여러 번 켜도 한
 * 번만 적용된다.
 */
@Component
@Profile("!worker")
@EnableScheduling
class SseMaintenance {

  private static final Logger log = LoggerFactory.getLogger(SseMaintenance.class);

  private final SseHub hub;

  SseMaintenance(SseHub hub) {
    this.hub = hub;
  }

  @Scheduled(
      fixedRateString = "${app.analysis.sse.ping-interval:20s}",
      initialDelayString = "${app.analysis.sse.ping-interval:20s}")
  void ping() {
    hub.ping();
  }

  @Scheduled(
      fixedDelayString = "${app.analysis.sse.reconcile-interval:30s}",
      initialDelayString = "${app.analysis.sse.reconcile-interval:30s}")
  void reconcile() {
    try {
      hub.reconcile();
    } catch (RuntimeException e) {
      log.warn("분석 상태 SSE 맞추기 실패. 다음 주기에 다시 함", e);
    }
  }
}
