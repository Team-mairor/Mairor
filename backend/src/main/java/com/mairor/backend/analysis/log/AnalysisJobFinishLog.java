package com.mairor.backend.analysis.log;

import com.mairor.backend.analysis.entity.AnalysisJob;
import jakarta.persistence.PostPersist;
import jakarta.persistence.PostUpdate;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.spi.LoggingEventBuilder;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * 분석 작업이 끝날 때(완료 · 실패) 한 줄 요약을 남긴다. 끝나는 경로(AI 콜백 · 시간 초과 감시 · 노트북 실패 · worker 실패 등)가 여러 곳이라 작업이 저장될
 * 때 한 곳에서 남기고, 트랜잭션이 커밋된 뒤에만 남긴다(롤백된 끝은 남기지 않는다).
 *
 * <p>운영 JSON 로그에서는 소요 시간 · 시도 횟수 등이 칸으로 나간다(SLF4J key-value). 단계 수 · 프레임 수는 AI 에 맡길 때의 줄, AI 토큰은 AI
 * 로그(Phoenix)에 있다. 시도 횟수가 2 이상이면 {@code total_ms}는 처음 요청부터 센다.
 */
public class AnalysisJobFinishLog {

  private static final Logger log = LoggerFactory.getLogger(AnalysisJobFinishLog.class);

  @PostPersist
  @PostUpdate
  void saved(AnalysisJob job) {
    if (!job.takeFinished()) {
      return;
    }
    Summary summary = Summary.of(job);
    if (TransactionSynchronizationManager.isSynchronizationActive()) {
      TransactionSynchronizationManager.registerSynchronization(
          new TransactionSynchronization() {
            @Override
            public void afterCommit() {
              summary.log();
            }
          });
    } else {
      summary.log();
    }
  }

  record Summary(
      UUID analysisJobId,
      String aiJobId,
      String status,
      String stage,
      String failureCode,
      boolean retryable,
      int attempt,
      int processorClaims,
      Long waitMs,
      Long processingMs,
      Long aiMs,
      Long totalMs) {

    static Summary of(AnalysisJob job) {
      Instant created = job.getCreatedAt();
      Instant started = job.getStartedAt();
      Instant aiRequested = job.getAiRequestedAt();
      Instant finished = job.getFinishedAt();
      return new Summary(
          job.getId(),
          job.getAiJobId(),
          job.getStatus().name(),
          job.getProgressStage().name(),
          job.getFailureCode(),
          job.isRetryable(),
          job.getAttempt(),
          job.getProcessorClaims(),
          millis(created, started),
          millis(started, aiRequested != null ? aiRequested : finished),
          millis(aiRequested, finished),
          millis(created, finished));
    }

    void log() {
      // 작업 칸은 MDC 로 붙인다(같은 칸을 key-value 로 또 쓰면 JSON 에 같은 이름이 두 번 나온다)
      try (var ignored = AnalysisLogContext.of(analysisJobId, null, aiJobId)) {
        LoggingEventBuilder event =
            ("FAILED".equals(status) ? log.atWarn() : log.atInfo())
                .setMessage(
                    "분석 작업 끝 jobId={} status={} stage={} failureCode={} attempt={} totalMs={}")
                .addArgument(analysisJobId)
                .addArgument(status)
                .addArgument(stage)
                .addArgument(failureCode)
                .addArgument(attempt)
                .addArgument(totalMs)
                .addKeyValue("analysis_status", status)
                .addKeyValue("progress_stage", stage)
                .addKeyValue("attempt", attempt)
                .addKeyValue("processor_claims", processorClaims);
        addIfPresent(event, "failure_code", failureCode);
        if (failureCode != null) {
          event.addKeyValue("retryable", retryable);
        }
        addIfPresent(event, "wait_ms", waitMs);
        addIfPresent(event, "processing_ms", processingMs);
        addIfPresent(event, "ai_ms", aiMs);
        addIfPresent(event, "total_ms", totalMs);
        event.log();
      }
    }

    private static void addIfPresent(LoggingEventBuilder event, String key, Object value) {
      if (value != null) {
        event.addKeyValue(key, value);
      }
    }

    private static Long millis(Instant from, Instant to) {
      return from == null || to == null ? null : Duration.between(from, to).toMillis();
    }
  }
}
