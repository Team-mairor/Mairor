package com.mairor.backend.products.imports;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 하트비트가 끊긴 카탈로그 적재 실행을 주기적으로 {@code ABANDONED}로 끝낸다. 수집기가 죽었거나 네트워크가 끊겨 {@code finish}를 못 부른 실행이
 * 영원히 진행 중으로 남지 않게 한다. 기준 시간은 {@code catalog.import.heartbeat-timeout}이다.
 *
 * <p>분석 작업 감시와 같이 worker 프로파일에서만 돈다. 한 번에 한 곳에서만 돌아야 하고, 상태 변경이 조건부 갱신이라 겹쳐 돌아도 같은 실행을 두 번 끝내지 않는다.
 */
@Component
@Profile("worker")
class CatalogImportWatcher {

  private static final Logger log = LoggerFactory.getLogger(CatalogImportWatcher.class);

  private final CatalogImportRunService runs;

  CatalogImportWatcher(CatalogImportRunService runs) {
    this.runs = runs;
  }

  @Scheduled(
      fixedDelayString = "${catalog.import.watch-interval:60s}",
      initialDelayString = "${catalog.import.watch-interval:60s}")
  void check() {
    try {
      runs.abandonStale();
    } catch (RuntimeException e) {
      log.warn("끊긴 적재 실행 정리에 실패했습니다.", e);
    }
  }
}
