package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.extraction.GuideInputMapper;
import com.mairor.backend.analysis.extraction.InvalidStepOutputException;
import com.mairor.backend.analysis.extraction.LlmCallRecorder;
import com.mairor.backend.analysis.extraction.StepExtractionPrompt;
import com.mairor.backend.common.external.llm.LlmClient;
import com.mairor.backend.common.external.llm.LlmException;
import com.mairor.backend.common.external.llm.LlmRequest;
import com.mairor.backend.common.external.llm.LlmResult;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * 단계 추출(EXTRACTING_STEPS): Gemini 에 유튜브 URL 을 넣어 단계 목록·세부 사실을 받고, 가이드 입력 v2 로 바꿔 작업의 가이드에 저장한다.
 *
 * <p>영상 길이는 유튜브 메타가 아니라 불러오기 단계의 ffprobe 값을 쓴다(실제 파일 기준이라 프레임 추출과 맞는다). 호출마다 {@code llm_calls}에
 * 남긴다.
 */
@Component
class ExtractStepsStep implements AnalysisStepHandler {

  static final String PURPOSE = "STEP_EXTRACTION";

  private static final Logger log = LoggerFactory.getLogger(ExtractStepsStep.class);

  private final LlmClient llm;
  private final StepExtractionPrompt prompt;
  private final GuideInputMapper mapper;
  private final LlmCallRecorder recorder;
  private final AnalysisJobStore store;
  private final ObjectMapper objectMapper;

  ExtractStepsStep(
      LlmClient llm,
      StepExtractionPrompt prompt,
      GuideInputMapper mapper,
      LlmCallRecorder recorder,
      AnalysisJobStore store,
      ObjectMapper objectMapper) {
    this.llm = llm;
    this.prompt = prompt;
    this.mapper = mapper;
    this.recorder = recorder;
    this.store = store;
    this.objectMapper = objectMapper;
  }

  @Override
  public ProgressStage stage() {
    return ProgressStage.EXTRACTING_STEPS;
  }

  @Override
  public void run(AnalysisContext context) {
    VideoProbe probe = context.probe();
    if (probe == null) {
      throw new IllegalStateException("영상 불러오기 전에는 단계를 뽑을 수 없습니다.");
    }
    UUID jobId = context.jobId();
    String videoUrl = "https://www.youtube.com/watch?v=" + context.youtubeVideoId();
    LlmRequest request =
        new LlmRequest(
            videoUrl, prompt.prompt(), prompt.responseSchema(), StepExtractionPrompt.TEMPERATURE);

    long started = System.nanoTime();
    LlmResult result;
    try {
      result = llm.generate(request);
    } catch (LlmException e) {
      recorder.failed(jobId, PURPOSE, e, millisSince(started));
      AnalysisFailureCode code =
          e.kind() == LlmException.Kind.INVALID_RESPONSE
              ? AnalysisFailureCode.LLM_INVALID_RESPONSE
              : AnalysisFailureCode.LLM_UNAVAILABLE;
      throw new AnalysisStepException(code, e.getMessage(), e);
    }
    long elapsed = millisSince(started);
    recorder.succeeded(jobId, PURPOSE, result, elapsed);

    GuideInputMapper.Result mapped;
    try {
      mapped = mapper.map(result.text(), context.youtubeVideoId(), probe.durationSeconds());
    } catch (InvalidStepOutputException e) {
      throw new AnalysisStepException(AnalysisFailureCode.LLM_INVALID_RESPONSE, e.getMessage(), e);
    }
    mapped.dropped().forEach(reason -> log.warn("단계 버림 jobId={} {}", jobId, reason));
    int steps = mapped.input().steps().size();
    log.info(
        "단계 추출 jobId={} provider={} model={} steps={} dropped={} inputTokens={} outputTokens={}"
            + " attempts={} elapsedMs={}",
        jobId,
        result.provider(),
        result.model(),
        steps,
        mapped.dropped().size(),
        result.inputTokens(),
        result.outputTokens(),
        result.attempts(),
        elapsed);
    if (steps == 0) {
      throw new AnalysisStepException(
          AnalysisFailureCode.NO_VALID_STEPS,
          "쓸 수 있는 단계가 없습니다(받은 단계 " + mapped.dropped().size() + "개 모두 버림).");
    }
    store.saveGuideInput(jobId, objectMapper.writeValueAsString(mapped.input()));
    context.stepsExtracted(mapped.input());
  }

  private static long millisSince(long nanoStart) {
    return (System.nanoTime() - nanoStart) / 1_000_000;
  }
}
