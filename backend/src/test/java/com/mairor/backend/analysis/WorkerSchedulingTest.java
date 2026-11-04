package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.worker.AnalysisJobRunner;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

/**
 * worker 의 실제 스케줄러 설정으로, 긴 분석 작업({@code AnalysisWorker.poll()})이 도는 동안에도 AI 콜백 감시({@code
 * AiCallbackWatcher.check()})가 도는지 본다(서연 후속 요청 1번). 가상 스레드 설정의 기본 스케줄러는 fixed-delay 작업을 스레드 하나에서
 * 차례로 돌려, 프레임 추출처럼 수십 분 걸리는 작업 동안 감시가 멈췄다.
 */
@ActiveProfiles("worker")
@TestPropertySource(
    properties = {"app.analysis.worker.poll-interval=50ms", "app.ai.watch-interval=200ms"})
class WorkerSchedulingTest extends AnalysisIntegrationTest {

  @MockitoBean private AnalysisJobRunner runner;
  @MockitoSpyBean private AnalysisJobRepository jobs;

  private final CountDownLatch jobStarted = new CountDownLatch(1);
  private final CountDownLatch jobMayFinish = new CountDownLatch(1);

  @BeforeEach
  void aLongJobIsWaiting() {
    when(runner.runNext())
        .thenAnswer(
            invocation -> {
              jobStarted.countDown();
              jobMayFinish.await(10, TimeUnit.SECONDS);
              return false;
            });
  }

  @AfterEach
  void finishTheLongJob() {
    jobMayFinish.countDown();
  }

  @Test
  void theCallbackWatcherKeepsRunningWhileALongJobRuns() throws InterruptedException {
    assertThat(jobStarted.await(10, TimeUnit.SECONDS)).as("poll 이 긴 작업을 잡았다").isTrue();
    clearInvocations(jobs);

    verify(jobs, timeout(3_000).atLeastOnce())
        .findAwaitingAiRequestedBefore(eq(AnalysisStatus.RUNNING), any());
  }
}
