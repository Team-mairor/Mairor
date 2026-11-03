package com.mairor.backend.analysis.extraction;

import com.mairor.backend.analysis.entity.LlmCall;
import com.mairor.backend.analysis.entity.LlmCallStatus;
import com.mairor.backend.analysis.repository.LlmCallRepository;
import com.mairor.backend.common.external.llm.LlmException;
import com.mairor.backend.common.external.llm.LlmResult;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** LLM 호출마다 {@code llm_calls} 한 행(토큰·시간·답 원문). 비용은 토큰으로 계산한다. */
@Component
public class LlmCallRecorder {

  private final LlmCallRepository calls;

  LlmCallRecorder(LlmCallRepository calls) {
    this.calls = calls;
  }

  @Transactional
  public void succeeded(UUID jobId, String purpose, LlmResult result, long durationMs) {
    calls.save(
        new LlmCall(
            jobId,
            result.provider(),
            result.model(),
            purpose,
            LlmCallStatus.SUCCEEDED,
            result.inputTokens(),
            result.outputTokens(),
            clamp(durationMs),
            null,
            result.text()));
  }

  @Transactional
  public void failed(UUID jobId, String purpose, LlmException e, long durationMs) {
    String code = e.kind().name() + (e.status() == null ? "" : "_" + e.status());
    calls.save(
        new LlmCall(
            jobId,
            e.provider() == null ? "UNKNOWN" : e.provider(),
            e.model() == null ? "UNKNOWN" : e.model(),
            purpose,
            LlmCallStatus.FAILED,
            null,
            null,
            clamp(durationMs),
            code,
            e.getMessage()));
  }

  private static int clamp(long durationMs) {
    return (int) Math.min(Math.max(durationMs, 0), Integer.MAX_VALUE);
  }
}
