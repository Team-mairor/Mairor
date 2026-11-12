package com.mairor.backend.analysis.log;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class AnalysisLogContextTest {

  private static final UUID JOB = UUID.fromString("c0000000-0000-4000-8000-0000000000bb");

  @AfterEach
  void clear() {
    MDC.clear();
  }

  @Test
  void putsTheThreeFieldsAndRemovesThemOnClose() {
    try (var ignored = AnalysisLogContext.of(JOB, "VxAXD6PP76I", "ai-1")) {
      assertThat(MDC.get("analysis_job_id")).isEqualTo(JOB.toString());
      assertThat(MDC.get("video_id")).isEqualTo("VxAXD6PP76I");
      assertThat(MDC.get("job_id")).isEqualTo("ai-1");
    }
    assertThat(MDC.getCopyOfContextMap()).isNullOrEmpty();
  }

  @Test
  void missingValuesAreLeftOutAndTheAiJobCanBeAddedLater() {
    try (var context = AnalysisLogContext.of(JOB, null, " ")) {
      assertThat(MDC.get("video_id")).isNull();
      assertThat(MDC.get("job_id")).isNull();
      context.aiJob("ai-2");
      assertThat(MDC.get("job_id")).isEqualTo("ai-2");
    }
    assertThat(MDC.get("job_id")).isNull();
    assertThat(MDC.get("analysis_job_id")).isNull();
  }

  @Test
  void anInnerContextRestoresTheOuterValues() {
    try (var outer = AnalysisLogContext.of(JOB, "VxAXD6PP76I", null)) {
      try (var inner = AnalysisLogContext.of(null, null, "ai-3")) {
        assertThat(MDC.get("analysis_job_id")).isEqualTo(JOB.toString());
        assertThat(MDC.get("job_id")).isEqualTo("ai-3");
      }
      assertThat(MDC.get("job_id")).isNull();
      assertThat(MDC.get("analysis_job_id")).isEqualTo(JOB.toString());
    }
    assertThat(MDC.getCopyOfContextMap()).isNullOrEmpty();
  }
}
