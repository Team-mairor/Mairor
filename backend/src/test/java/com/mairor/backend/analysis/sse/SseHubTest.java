package com.mairor.backend.analysis.sse;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.service.AnalysisJobStatusService;
import com.mairor.backend.analysis.service.AnalysisJobStatusView;
import com.mairor.backend.guides.entity.ReviewStatus;
import java.sql.ResultSet;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CyclicBarrier;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

/** {@link SseHub}의 실패·경합 경로. DB·상태 조립은 가짜로 두고 순서만 본다. */
class SseHubTest {

  private static final SseProperties PROPERTIES =
      new SseProperties(
          Duration.ofMinutes(30),
          Duration.ofSeconds(20),
          Duration.ofSeconds(30),
          Duration.ofSeconds(10),
          Duration.ofSeconds(30));

  private static AnalysisJobStatusView view(UUID jobId, AnalysisStatus status) {
    return new AnalysisJobStatusView(
        jobId,
        UUID.randomUUID(),
        status,
        status == AnalysisStatus.COMPLETED ? ProgressStage.DONE : ProgressStage.BUILDING_GUIDE,
        null,
        null,
        null,
        false,
        status == AnalysisStatus.COMPLETED ? ReviewStatus.PENDING : ReviewStatus.NOT_READY,
        false,
        null,
        List.of(),
        0,
        null,
        null,
        null,
        3,
        Instant.parse("2026-11-04T00:00:00Z"),
        null);
  }

  /** 맞추기 쿼리가 열린 작업마다 같은 확인값을 돌려주게 한다. */
  private static void fingerprintIs(NamedParameterJdbcTemplate jdbc, UUID jobId, String value) {
    doAnswer(
            invocation -> {
              ResultSet rs = mock(ResultSet.class);
              when(rs.getObject("id", UUID.class)).thenReturn(jobId);
              when(rs.getString("fingerprint")).thenReturn(value);
              invocation.<RowCallbackHandler>getArgument(2).processRow(rs);
              return null;
            })
        .when(jdbc)
        .query(anyString(), anyMap(), any(RowCallbackHandler.class));
  }

  @Test
  void reconcileRetriesAJobWhoseReadFailedLastTime() {
    AnalysisJobStatusService statuses = mock(AnalysisJobStatusService.class);
    NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);
    SseHub hub = new SseHub(statuses, jdbc, PROPERTIES);
    hub.start();
    UUID userId = UUID.randomUUID();
    UUID jobId = UUID.randomUUID();
    when(statuses.find(userId, jobId))
        // 연결 직후
        .thenReturn(Optional.of(view(jobId, AnalysisStatus.RUNNING)))
        // 완료 알림을 놓친 뒤 첫 맞추기: DB 를 못 읽음
        .thenThrow(new IllegalStateException("DB 일시 장애"))
        // 다음 맞추기
        .thenReturn(Optional.of(view(jobId, AnalysisStatus.COMPLETED)));
    hub.subscribe(userId, jobId);
    fingerprintIs(jdbc, jobId, "completed");

    hub.reconcile();
    hub.reconcile();

    verify(statuses, times(3)).find(userId, jobId);
  }

  @Test
  void reconcileDoesNotRereadAnUnchangedJobAfterASuccess() {
    AnalysisJobStatusService statuses = mock(AnalysisJobStatusService.class);
    NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);
    SseHub hub = new SseHub(statuses, jdbc, PROPERTIES);
    hub.start();
    UUID userId = UUID.randomUUID();
    UUID jobId = UUID.randomUUID();
    when(statuses.find(userId, jobId)).thenReturn(Optional.of(view(jobId, AnalysisStatus.RUNNING)));
    hub.subscribe(userId, jobId);
    fingerprintIs(jdbc, jobId, "same");

    hub.reconcile();
    hub.reconcile();

    verify(statuses, times(2)).find(userId, jobId);
  }

  /** 새 연결과 종료가 겹쳐도 닫히지 않은 연결이 남지 않는다. 새 연결이 "실행 중"을 확인한 뒤 등록하기 전에 종료가 끝나는 순서를 여러 번 겹쳐 본다. */
  @Test
  void connectionsOpenedWhileShuttingDownAreClosed() throws Exception {
    AnalysisJobStatusService statuses = mock(AnalysisJobStatusService.class);
    NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);
    when(statuses.find(any(UUID.class), any(UUID.class)))
        .thenAnswer(
            invocation -> Optional.of(view(invocation.getArgument(1), AnalysisStatus.RUNNING)));
    int subscribers = 4;

    for (int round = 0; round < 500; round++) {
      SseHub hub = new SseHub(statuses, jdbc, PROPERTIES);
      hub.start();
      CyclicBarrier start = new CyclicBarrier(subscribers + 1);
      List<Thread> threads = new ArrayList<>();
      for (int i = 0; i < subscribers; i++) {
        threads.add(
            Thread.ofPlatform()
                .start(
                    () -> {
                      await(start);
                      hub.subscribe(UUID.randomUUID(), UUID.randomUUID());
                    }));
      }
      Thread stopper =
          Thread.ofPlatform()
              .start(
                  () -> {
                    await(start);
                    hub.stop();
                  });
      for (Thread thread : threads) {
        thread.join();
      }
      stopper.join();

      assertThat(hub.openConnections()).as("round %d", round).isZero();
    }
  }

  private static void await(CyclicBarrier barrier) {
    try {
      barrier.await();
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }
}
