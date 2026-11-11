package com.mairor.backend.executions.service;

import com.mairor.backend.executions.repository.GuideExecutionOrphanRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 세션 행이 이미 사라진 미완료 실행을 배치로 포기 처리한다. */
@Component
@ConditionalOnProperty(
    prefix = "app.guide-execution",
    name = "orphan-cleanup-enabled",
    havingValue = "true",
    matchIfMissing = true)
public class GuideExecutionOrphanScheduler {
  private static final Logger log = LoggerFactory.getLogger(GuideExecutionOrphanScheduler.class);
  private final GuideExecutionOrphanRepository orphans;
  private final ExecutionLifecycleService lifecycle;
  private final int batchSize;

  public GuideExecutionOrphanScheduler(
      GuideExecutionOrphanRepository orphans,
      ExecutionLifecycleService lifecycle,
      @org.springframework.beans.factory.annotation.Value("${app.session.sweep.batch-size:50}")
          int batchSize) {
    this.orphans = orphans;
    this.lifecycle = lifecycle;
    this.batchSize = batchSize;
  }

  @Scheduled(fixedDelayString = "${app.session.sweep.interval:1m}")
  public void sweep() {
    try {
      for (var orphan : orphans.findMissingSessions(batchSize)) {
        try {
          lifecycle.abandonSession(orphan.userId(), orphan.sessionId());
        } catch (RuntimeException failure) {
          log.warn("세션이 사라진 가이드 실행 정리를 다음 주기에 재시도합니다.", failure);
        }
      }
    } catch (RuntimeException failure) {
      log.warn("세션 유실 가이드 실행 조회에 실패했습니다. 다음 주기에 재시도합니다.", failure);
    }
  }
}
