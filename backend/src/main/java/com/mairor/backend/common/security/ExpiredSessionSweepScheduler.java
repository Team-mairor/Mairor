package com.mairor.backend.common.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * {@link ExpiredSessionSweeper} 를 주기적으로 실행한다. {@code app.session.sweep.enabled=false} 면 만들어지지
 * 않는다(그러면 아무도 만료된 세션 행을 지우지 않는다). 첫 실행은 기동 직후가 아니라 한 주기 뒤다. 한 번의 실패가 다음 실행을 막지 않도록 예외는 여기서 기록하고
 * 삼킨다.
 */
@Component
@EnableScheduling
@ConditionalOnProperty(
    prefix = "app.session.sweep",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
class ExpiredSessionSweepScheduler {

  private static final Logger log = LoggerFactory.getLogger(ExpiredSessionSweepScheduler.class);

  private final ExpiredSessionSweeper sweeper;

  ExpiredSessionSweepScheduler(ExpiredSessionSweeper sweeper) {
    this.sweeper = sweeper;
  }

  @Scheduled(
      fixedDelayString = "${app.session.sweep.interval}",
      initialDelayString = "${app.session.sweep.interval}")
  void run() {
    try {
      sweeper.sweep();
    } catch (RuntimeException e) {
      log.error("만료된 세션 정리 작업이 실패했습니다. 다음 주기에 다시 실행합니다.", e);
    }
  }
}
