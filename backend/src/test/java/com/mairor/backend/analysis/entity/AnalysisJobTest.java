package com.mairor.backend.analysis.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.videos.entity.Video;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class AnalysisJobTest {

  private static final Instant T0 = Instant.parse("2026-11-03T00:00:00Z");
  private static final Instant T1 = Instant.parse("2026-11-03T00:05:00Z");

  private static AnalysisJob newJob() {
    Video video = new Video("VxAXD6PP76I", "제목", "채널", 1858, null, null, "[]", T0);
    return new AnalysisJob(video, null);
  }

  @Test
  void newJobIsPendingAndQueued() {
    AnalysisJob job = newJob();

    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.PENDING);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.QUEUED);
    assertThat(job.getAttempt()).isEqualTo(1);
    assertThat(job.isRetryable()).isFalse();
  }

  @Test
  void runsThroughToCompleted() {
    AnalysisJob job = newJob();

    job.start(T0);
    job.advanceTo(ProgressStage.LOADING_VIDEO);
    job.complete(T1);

    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.COMPLETED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.DONE);
    assertThat(job.getProgressPercent()).isEqualTo(100);
    assertThat(job.getStartedAt()).isEqualTo(T0);
    assertThat(job.getFinishedAt()).isEqualTo(T1);
  }

  @Test
  void failureKeepsTheStageWhereItStoppedAndRecordsRetryable() {
    AnalysisJob job = newJob();
    job.start(T0);
    job.advanceTo(ProgressStage.LOADING_VIDEO);

    job.fail(AnalysisFailureCode.STORAGE_UNAVAILABLE, null, T1);

    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.FAILED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.LOADING_VIDEO);
    assertThat(job.getFailureCode()).isEqualTo("STORAGE_UNAVAILABLE");
    assertThat(job.getFailureMessage())
        .isEqualTo(AnalysisFailureCode.STORAGE_UNAVAILABLE.defaultMessage());
    assertThat(job.isRetryable()).isTrue();
  }

  @Test
  void longFailureMessageIsTruncated() {
    AnalysisJob job = newJob();
    job.start(T0);

    job.fail(AnalysisFailureCode.SOURCE_UNREADABLE, "가".repeat(600), T1);

    assertThat(job.getFailureMessage()).hasSize(AnalysisJob.FAILURE_MESSAGE_MAX_LENGTH);
    assertThat(job.isRetryable()).isFalse();
  }

  @Test
  void crashedJobGoesBackToPending() {
    AnalysisJob job = newJob();
    job.start(T0);
    job.advanceTo(ProgressStage.LOADING_VIDEO);

    job.requeueAfterCrash();

    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.PENDING);
    assertThat(job.getStartedAt()).isNull();
  }

  @Test
  void transitionsOutOfOrderAreRejected() {
    AnalysisJob pending = newJob();
    assertThatThrownBy(() -> pending.complete(T1)).isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> pending.advanceTo(ProgressStage.LOADING_VIDEO))
        .isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> pending.requeueAfterCrash()).isInstanceOf(IllegalStateException.class);

    AnalysisJob running = newJob();
    running.start(T0);
    assertThatThrownBy(() -> running.start(T1)).isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> running.advanceTo(ProgressStage.DONE))
        .isInstanceOf(IllegalArgumentException.class);

    running.complete(T1);
    assertThatThrownBy(() -> running.fail(AnalysisFailureCode.INTERNAL_ERROR, null, T1))
        .isInstanceOf(IllegalStateException.class);
  }

  // --- AI 진행 숫자 (S15P31A306-296) ---

  private static final String AI_JOB = "8728c83b0d124c74a23863a50d4d7c0c";
  private static final String PROGRESS = "{\"explanation\":{\"done\":3,\"total\":19}}";

  private static AnalysisJob awaitingAiJob() {
    AnalysisJob job = newJob();
    job.start(T0);
    job.advanceTo(ProgressStage.BUILDING_GUIDE);
    job.awaitAi(AI_JOB, T0);
    return job;
  }

  @Test
  void awaitingAiRecordsWhenTheJobWasHandedOver() {
    AnalysisJob job = awaitingAiJob();

    assertThat(job.getAiJobId()).isEqualTo(AI_JOB);
    assertThat(job.getAiRequestedAt()).isEqualTo(T0);
    assertThat(job.isAwaitingAi()).isTrue();
  }

  @Test
  void timeoutBaselineIsTheHandOverTimeEvenAfterProgress() {
    AnalysisJob job = awaitingAiJob();
    job.recordAiProgress(PROGRESS);

    assertThat(job.aiTimeoutBaseline()).isEqualTo(T0);
  }

  @Test
  void progressIsStoredWhileWaitingForTheAiWithoutMovingTheRequestTime() {
    AnalysisJob job = awaitingAiJob();

    assertThat(job.recordAiProgress(PROGRESS)).isTrue();
    assertThat(job.recordAiProgress("{\"explanation\":{\"done\":19,\"total\":19}}")).isTrue();

    assertThat(job.getAiProgress()).contains("\"done\":19");
    assertThat(job.getAiRequestedAt()).isEqualTo(T0);
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.RUNNING);
  }

  @Test
  void progressIsDroppedBeforeHandoverAndAfterTheJobEnds() {
    AnalysisJob notYet = newJob();
    notYet.start(T0);
    assertThat(notYet.recordAiProgress(PROGRESS)).isFalse();
    assertThat(notYet.getAiProgress()).isNull();

    AnalysisJob completed = awaitingAiJob();
    completed.complete(T1);
    assertThat(completed.recordAiProgress(PROGRESS)).isFalse();
    assertThat(completed.getAiProgress()).isNull();

    AnalysisJob failed = awaitingAiJob();
    failed.fail(AnalysisFailureCode.ANALYSIS_TIMEOUT, null, T1);
    assertThat(failed.recordAiProgress(PROGRESS)).isFalse();
  }
}
