package com.mairor.backend.analysis.log;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.videos.entity.Video;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.logging.logback.StructuredLogEncoder;
import org.springframework.core.env.Environment;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 작업 끝 요약 한 줄: 한 번만, 커밋 뒤에만 남고, 운영 JSON(logstash)에서 작업 칸과 요약 칸이 나온다. */
class AnalysisJobFinishLogTest {

  private static final Instant T0 = Instant.parse("2026-11-12T00:00:00Z");
  private static final Instant T1 = Instant.parse("2026-11-12T00:05:00Z");
  private static final UUID ID = UUID.fromString("c0000000-0000-4000-8000-0000000000bb");

  private final Logger logger = (Logger) LoggerFactory.getLogger(AnalysisJobFinishLog.class);
  private final ListAppender<ILoggingEvent> events = new ListAppender<>();

  @BeforeEach
  void capture() {
    events.start();
    logger.addAppender(events);
  }

  @AfterEach
  void release() {
    logger.detachAppender(events);
    MDC.clear();
    if (TransactionSynchronizationManager.isSynchronizationActive()) {
      TransactionSynchronizationManager.clearSynchronization();
    }
  }

  private static AnalysisJob failedJob() {
    Video video = new Video("VxAXD6PP76I", "제목", "채널", 1858, null, null, "[]", T0);
    AnalysisJob job = new AnalysisJob(video, null);
    ReflectionTestUtils.setField(job, "id", ID);
    ReflectionTestUtils.setField(job, "createdAt", T0);
    job.claimByProcessor(T0.plusSeconds(60), Duration.ofMinutes(15));
    job.fail(AnalysisFailureCode.LLM_UNAVAILABLE, null, T1);
    return job;
  }

  @Test
  void aFinishedJobIsLoggedOnceAsJsonFields() {
    AnalysisJob job = failedJob();
    AnalysisJobFinishLog listener = new AnalysisJobFinishLog();

    listener.saved(job);
    listener.saved(job);

    assertThat(events.list).hasSize(1);
    assertThat(MDC.getCopyOfContextMap()).isNullOrEmpty();
    JsonNode json = logstash(events.list.getFirst());
    assertThat(json.path("level").asString()).isEqualTo("WARN");
    assertThat(json.path("analysis_job_id").asString()).isEqualTo(ID.toString());
    assertThat(json.path("analysis_status").asString()).isEqualTo("FAILED");
    assertThat(json.path("failure_code").asString()).isEqualTo("LLM_UNAVAILABLE");
    assertThat(json.path("retryable").asString()).isEqualTo("true");
    assertThat(json.path("attempt").asInt()).isEqualTo(1);
    assertThat(json.path("processor_claims").asInt()).isEqualTo(1);
    assertThat(json.path("wait_ms").asLong()).isEqualTo(60_000);
    assertThat(json.path("total_ms").asLong()).isEqualTo(300_000);
    assertThat(json.has("ai_ms")).as("AI 에 맡기기 전에 끝났다").isFalse();
  }

  @Test
  void insideATransactionItIsLoggedOnlyAfterCommit() {
    TransactionSynchronizationManager.initSynchronization();

    new AnalysisJobFinishLog().saved(failedJob());

    assertThat(events.list).isEmpty();
    TransactionSynchronizationManager.getSynchronizations()
        .forEach(TransactionSynchronization::afterCommit);
    assertThat(events.list).hasSize(1);
  }

  @Test
  void aJobThatDidNotFinishIsNotLogged() {
    Video video = new Video("VxAXD6PP76I", "제목", "채널", 1858, null, null, "[]", T0);
    AnalysisJob running = new AnalysisJob(video, null);
    running.claimByProcessor(T0, Duration.ofMinutes(15));

    new AnalysisJobFinishLog().saved(running);

    assertThat(events.list).isEmpty();
  }

  /** 운영과 같은 logstash 형식으로 한 줄을 만든다. */
  private static JsonNode logstash(ILoggingEvent event) {
    LoggerContext context = new LoggerContext();
    context.putObject(Environment.class.getName(), new MockEnvironment());
    StructuredLogEncoder encoder = new StructuredLogEncoder();
    encoder.setContext(context);
    encoder.setFormat("logstash");
    encoder.start();
    String line = new String(encoder.encode(event), StandardCharsets.UTF_8);
    return JsonMapper.builder().build().readTree(line);
  }
}
