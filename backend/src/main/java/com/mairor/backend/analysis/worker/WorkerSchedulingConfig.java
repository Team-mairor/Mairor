package com.mairor.backend.analysis.worker;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

/**
 * worker 의 주기 작업 스케줄러. 가상 스레드를 켜면({@code spring.threads.virtual.enabled}) Boot 가 기본으로 쓰는 스케줄러는
 * fixed-delay 작업을 스케줄러 스레드 하나에서 차례로 돌린다. 그러면 {@link AnalysisWorker#poll()}이 밀린 작업을 끝까지 처리하는 동안(프레임
 * 추출만 수십 분) {@link AiCallbackWatcher#check()}가 돌지 못한다. 이 빈이 있으면 Boot 기본 스케줄러는 만들어지지 않는다.
 *
 * <p>api 프로세스(SSE 주기 작업)는 Boot 기본 스케줄러를 그대로 쓴다.
 */
@Configuration(proxyBeanMethods = false)
@Profile("worker")
class WorkerSchedulingConfig {

  /** 대기 작업 처리 하나와 AI 콜백 감시 하나가 서로 막지 않게. */
  static final int POOL_SIZE = 2;

  @Bean
  ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(POOL_SIZE);
    scheduler.setThreadNamePrefix("analysis-worker-sched-");
    // 내려갈 때 처리 중인 작업을 끊지(interrupt) 않는다. 끊으면 ffmpeg 대기 등이 실패로 기록될 수 있다.
    // 프로세스가 끝나면 RUNNING 으로 남고, 다음 기동 때 대기열로 돌아간다(AI 에 맡기기 전 작업)
    scheduler.setWaitForTasksToCompleteOnShutdown(true);
    scheduler.setDaemon(true);
    return scheduler;
  }
}
