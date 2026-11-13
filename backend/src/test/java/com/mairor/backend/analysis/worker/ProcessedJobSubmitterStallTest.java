package com.mairor.backend.analysis.worker;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.mairor.backend.analysis.service.AiFrameDelivery;
import com.mairor.backend.analysis.service.ProcessorJobService;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.storage.ObjectStorage;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import tools.jackson.databind.json.JsonMapper;

/** 노트북 응답 없음 경고는 Grafana 알림이 세는 줄이라 같은 상태가 이어지면 10분에 한 번만 남긴다(S15P31A306-406). */
class ProcessedJobSubmitterStallTest {

  private static final Instant T0 = Instant.parse("2026-11-12T06:00:00Z");

  private final Logger logger = (Logger) LoggerFactory.getLogger(ProcessedJobSubmitter.class);
  private final ListAppender<ILoggingEvent> events = new ListAppender<>();

  @BeforeEach
  void capture() {
    events.start();
    logger.addAppender(events);
  }

  @AfterEach
  void release() {
    logger.detachAppender(events);
  }

  private static ProcessedJobSubmitter submitter() {
    return new ProcessedJobSubmitter(
        mock(AnalysisJobStore.class),
        mock(ProcessorJobService.class),
        mock(ObjectStorage.class),
        null,
        mock(AiGuideJobClient.class),
        null,
        null,
        JsonMapper.builder().build(),
        mock(AiFrameDelivery.class));
  }

  private static ProcessorJobService.Stall stallAt(Instant at) {
    return new ProcessorJobService.Stall(2, Duration.ofMinutes(7), at);
  }

  @Test
  void theWarningIsRepeatedOnlyEveryTenMinutes() {
    ProcessedJobSubmitter submitter = submitter();

    submitter.warnStalled(stallAt(T0));
    submitter.warnStalled(stallAt(T0.plusSeconds(5)));
    submitter.warnStalled(stallAt(T0.plus(Duration.ofMinutes(9))));
    submitter.warnStalled(stallAt(T0.plus(Duration.ofMinutes(10))));

    assertThat(events.list).hasSize(2);
    ILoggingEvent first = events.list.getFirst();
    assertThat(first.getFormattedMessage())
        .isEqualTo("노트북이 작업을 가져가지 않음 waiting=2 oldestWaitMs=420000");
    assertThat(first.getKeyValuePairs())
        .extracting(kv -> kv.key + "=" + kv.value)
        .containsExactly("waiting=2", "oldest_wait_ms=420000");
  }
}
