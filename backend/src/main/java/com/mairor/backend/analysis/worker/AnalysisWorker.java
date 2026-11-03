package com.mairor.backend.analysis.worker;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Profile;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 분석 worker. {@code worker} 프로파일에서만 뜬다(운영 compose 의 {@code worker} 서비스, -203 결정 5-4). 사용자 요청을 받는
 * api 슬롯은 작업을 돌리지 않는다.
 *
 * <p>기동하면 처리 중에 죽어 RUNNING 으로 남은 작업을 대기열로 돌리고, 그 뒤 주기마다 대기 작업을 하나씩 처리한다. worker 는 하나만 띄운다.
 */
@Component
@Profile("worker")
@EnableScheduling
class AnalysisWorker {

  private static final Logger log = LoggerFactory.getLogger(AnalysisWorker.class);

  private final AnalysisJobRunner runner;
  private final AnalysisJobStore store;
  private volatile boolean ready;

  AnalysisWorker(AnalysisJobRunner runner, AnalysisJobStore store) {
    this.runner = runner;
    this.store = store;
  }

  @EventListener(ApplicationReadyEvent.class)
  void recover() {
    int requeued = store.requeueRunning();
    if (requeued > 0) {
      log.warn("처리 중에 멈춘 분석 작업 {}개를 대기열로 되돌렸습니다.", requeued);
    }
    ready = true;
    log.info("분석 worker 시작");
  }

  @Scheduled(fixedDelayString = "${app.analysis.worker.poll-interval:5s}")
  void poll() {
    if (!ready) {
      return;
    }
    try {
      // 밀린 작업이 있으면 다음 주기를 기다리지 않고 이어서 처리한다
      while (runner.runNext()) {
        // 작업 하나씩 끝까지
      }
    } catch (RuntimeException e) {
      log.error("분석 작업을 집지 못했습니다. 다음 주기에 다시 시도합니다.", e);
    }
  }
}
