package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.mairor.backend.analysis.service.AiProgressService;
import com.mairor.backend.analysis.service.AiResultService;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.guides.service.GuideReviewService;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.postgresql.PGConnection;
import org.postgresql.PGNotification;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.json.JsonMapper;

/**
 * 상태를 바꾸는 곳마다 커밋 뒤 {@code analysis_job} 알림이 나가는지, 실제 {@code LISTEN} 연결로 받은 작업 ID 를 본다. 받는 쪽(SSE)은 이
 * 알림을 받아 작업을 다시 읽는다. 바뀌지 않은 경우(이미 끝난 작업의 재전송, 버린 진행 알림)는 알림이 없어야 한다.
 */
class AnalysisJobNotifyTest extends AnalysisIntegrationTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  @Autowired private DataSource dataSource;
  @Autowired private PlatformTransactionManager transactionManager;
  @Autowired private AnalysisJobNotifier notifier;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobStore store;
  @Autowired private AiProgressService progress;
  @Autowired private AiResultService results;
  @Autowired private GuideReviewService reviews;

  private Connection listener;

  @BeforeEach
  void listen() throws SQLException {
    listener = dataSource.getConnection();
    listener.setAutoCommit(true);
    try (Statement statement = listener.createStatement()) {
      statement.execute("LISTEN " + AnalysisJobNotifier.CHANNEL);
    }
    received();
  }

  @AfterEach
  void stopListening() throws SQLException {
    try (Statement statement = listener.createStatement()) {
      statement.execute("UNLISTEN *");
    }
    listener.close();
  }

  /** 지금까지 받은 알림의 작업 ID. 더 오지 않을 때까지 모은다. */
  private List<String> received() throws SQLException {
    PGConnection pg = listener.unwrap(PGConnection.class);
    List<String> ids = new ArrayList<>();
    while (true) {
      PGNotification[] batch = pg.getNotifications(300);
      if (batch == null || batch.length == 0) {
        return ids;
      }
      for (PGNotification notification : batch) {
        assertThat(notification.getName()).isEqualTo(AnalysisJobNotifier.CHANNEL);
        ids.add(notification.getParameter());
      }
    }
  }

  private UUID newJob(String youtubeVideoId) {
    return service
        .register(
            new AnalysisJobRequest(
                youtubeVideoId, "videos/" + youtubeVideoId + "/source.mp4", "제목", "채널", 600))
        .jobId();
  }

  @Test
  void notifyMustRunInsideTheSavingTransaction() {
    assertThatThrownBy(() -> notifier.changed(UUID.randomUUID()))
        .isInstanceOf(IllegalTransactionStateException.class);
  }

  @Test
  void onlyCommittedChangesAreAnnounced() throws SQLException {
    UUID committed = UUID.randomUUID();
    UUID rolledBack = UUID.randomUUID();
    TransactionTemplate tx = new TransactionTemplate(transactionManager);

    tx.executeWithoutResult(status -> notifier.changed(committed));
    tx.executeWithoutResult(
        status -> {
          notifier.changed(rolledBack);
          status.setRollbackOnly();
        });

    assertThat(received()).containsExactly(committed.toString());
  }

  @Test
  void workerStepsProgressAndTheCallbackAreAnnounced() throws SQLException {
    UUID jobId = newJob("eFzG30avtOI");
    String id = jobId.toString();

    assertThat(store.claimNext(WORK_ROOT)).isPresent();
    assertThat(received()).as("worker 가 집음").containsExactly(id);

    store.saveGuideInput(jobId, "{\"videoId\": \"eFzG30avtOI\", \"steps\": []}");
    assertThat(received()).as("가이드 입력 저장은 보이는 상태가 아니다").isEmpty();

    store.advance(jobId, ProgressStage.BUILDING_GUIDE);
    assertThat(received()).as("단계 진행").containsExactly(id);

    store.awaitAi(jobId, "ai-notify-1");
    assertThat(received()).as("AI 접수").containsExactly(id);

    progress.record(
        "{\"jobId\": \"ai-notify-1\", \"explanation\": {\"done\": 3, \"total\": 19},"
            + " \"frames\": null, \"landmarks\": null, \"area\": null}");
    assertThat(received()).as("진행 숫자").containsExactly(id);

    progress.record(
        "{\"jobId\": \"someone-else\", \"explanation\": {\"done\": 3, \"total\": 19},"
            + " \"frames\": null, \"landmarks\": null, \"area\": null}");
    progress.record("not json");
    assertThat(received()).as("버린 진행 알림").isEmpty();

    AiGuideJobCallbackRequest completed =
        new AiGuideJobCallbackRequest(
            "ai-notify-1",
            "eFzG30avtOI",
            "COMPLETED",
            JSON.readTree("{\"steps\": []}"),
            null,
            null);
    results.apply(completed);
    assertThat(received()).as("콜백 완료").containsExactly(id);

    results.apply(completed);
    assertThat(received()).as("이미 끝난 작업의 재전송").isEmpty();
  }

  @Test
  void failureTimeoutAndRequeueAreAnnounced() throws SQLException {
    UUID failing = newJob("eFzG30avtOI");
    store.claimNext(WORK_ROOT);
    received();
    store.fail(failing, AnalysisFailureCode.SOURCE_NOT_FOUND, null);
    assertThat(received()).as("worker 실패").containsExactly(failing.toString());

    UUID timingOut = newJob("aaaaaaaaaaa");
    store.claimNext(WORK_ROOT);
    store.awaitAi(timingOut, "ai-timeout-1");
    received();
    assertThat(results.timeout("ai-timeout-1", "테스트")).isTrue();
    assertThat(received()).as("시간 초과").containsExactly(timingOut.toString());
    assertThat(results.timeout("ai-timeout-1", "테스트")).isFalse();
    assertThat(received()).as("이미 끝난 작업").isEmpty();

    UUID crashed = newJob("bbbbbbbbbbb");
    store.claimNext(WORK_ROOT);
    received();
    assertThat(store.requeueRunning()).isEqualTo(1);
    assertThat(received()).as("재시작 되돌림").containsExactly(crashed.toString());
  }

  @Test
  void reviewAnnouncesTheReviewedJobAndTheSupersededOne() throws SQLException {
    UUID earlier = newJob("eFzG30avtOI");
    jdbc.update(
        "update analysis_jobs set status = 'COMPLETED', progress_stage = 'DONE' where id = ?",
        earlier);
    store.saveGuideInput(earlier, "{\"steps\": []}");
    jdbc.update("update guides set review_status = 'APPROVED' where analysis_job_id = ?", earlier);
    UUID later = newJob("eFzG30avtOI");
    jdbc.update(
        "update analysis_jobs set status = 'COMPLETED', progress_stage = 'DONE' where id = ?",
        later);
    UUID laterGuide = store.saveGuideInput(later, "{\"steps\": []}");
    jdbc.update("update guides set review_status = 'PENDING' where id = ?", laterGuide);
    received();

    reviews.review(laterGuide, GuideReviewService.Decision.APPROVED);

    assertThat(received())
        .as("승인한 판과 공개에서 내려간 이전 판")
        .containsExactlyInAnyOrder(later.toString(), earlier.toString());
  }
}
