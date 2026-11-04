package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.extraction.GuideInput;
import com.mairor.backend.analysis.frames.FrameManifest;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiProperties;
import com.mairor.backend.common.external.ai.AiServerException;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * 가이드 구성(BUILDING_GUIDE): AI 서버에 가이드 생성을 맡긴다({@code docs/references/ai-api.md}). 요청은 {@code
 * callbackUrl}, 진행 알림 주소({@code progressUrl}), 가이드 입력, 레퍼런스 프레임(저장소 키 → 사전 서명 URL)이다. 진행 알림은 같은 기준
 * 주소의 {@code /v1/internal/ai/guide-jobs/progress}로 받는다(S15P31A306-296).
 *
 * <p>접수되면 AI 작업 ID 를 적고 끝난다. 작업은 RUNNING 으로 남고, AI 콜백이 설명·영역을 저장하며 COMPLETED 로 끝낸다({@link
 * #finishesLater()}).
 */
@Component
class BuildGuideStep implements AnalysisStepHandler {

  static final String CALLBACK_PATH = "/v1/internal/ai/guide-jobs/callback";
  static final String PROGRESS_PATH = "/v1/internal/ai/guide-jobs/progress";

  private static final Logger log = LoggerFactory.getLogger(BuildGuideStep.class);

  private final AiGuideJobClient client;
  private final AiProperties properties;
  private final ObjectStorage storage;
  private final AnalysisJobStore store;
  private final ObjectMapper objectMapper;

  BuildGuideStep(
      AiGuideJobClient client,
      AiProperties properties,
      ObjectStorage storage,
      AnalysisJobStore store,
      ObjectMapper objectMapper) {
    this.client = client;
    this.properties = properties;
    this.storage = storage;
    this.store = store;
    this.objectMapper = objectMapper;
  }

  @Override
  public ProgressStage stage() {
    return ProgressStage.BUILDING_GUIDE;
  }

  @Override
  public boolean finishesLater() {
    return true;
  }

  @Override
  public void run(AnalysisContext context) {
    GuideInput guideInput = context.guideInput();
    if (guideInput == null) {
      throw new IllegalStateException("단계 추출 전에는 가이드 생성을 요청할 수 없습니다.");
    }
    String body;
    try {
      body = objectMapper.writeValueAsString(request(guideInput, context.frames()));
    } catch (StorageException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.STORAGE_UNAVAILABLE, "프레임 주소를 만들지 못했습니다: " + e.getMessage(), e);
    }
    String aiJobId;
    try {
      aiJobId = client.submit(body);
    } catch (AiServerException e) {
      throw new AnalysisStepException(failureCode(e), e.getMessage(), e);
    }
    store.awaitAi(context.jobId(), aiJobId);
    log.info(
        "AI 가이드 생성 요청 jobId={} aiJobId={} steps={} frames={} requestBytes={}",
        context.jobId(),
        aiJobId,
        guideInput.steps().size(),
        context.frames() == null ? 0 : context.frames().items().size(),
        body.length());
  }

  /**
   * AI 가 요청을 거절한 4xx(408 · 429 제외)는 같은 입력이면 다시 해도 같은 결과라 재시도 불가({@code AI_REQUEST_REJECTED}), 연결 실패
   * · 5xx · 408 · 429 는 재시도 가능({@code AI_UNAVAILABLE}).
   */
  static AnalysisFailureCode failureCode(AiServerException e) {
    Integer status = e.status();
    boolean rejected =
        status != null && status >= 400 && status < 500 && status != 408 && status != 429;
    return rejected ? AnalysisFailureCode.AI_REQUEST_REJECTED : AnalysisFailureCode.AI_UNAVAILABLE;
  }

  /**
   * {@code guide_job_request.v2}: {callbackUrl, progressUrl, guideInput, frames?}. 프레임이 없으면 AI 는 영역
   * 없이 설명만 만든다.
   */
  Map<String, Object> request(GuideInput guideInput, FrameManifest frames) {
    Map<String, Object> request = new LinkedHashMap<>();
    request.put("callbackUrl", properties.callbackBaseUrl() + CALLBACK_PATH);
    request.put("progressUrl", properties.callbackBaseUrl() + PROGRESS_PATH);
    request.put("guideInput", guideInput);
    if (frames != null && !frames.items().isEmpty()) {
      List<Map<String, Object>> items = new ArrayList<>(frames.items().size());
      for (FrameManifest.Item item : frames.items()) {
        Map<String, Object> frame = new LinkedHashMap<>();
        frame.put("frameIndex", item.frameIndex());
        frame.put("timestampMs", item.timestampMs());
        frame.put("stepId", item.stepId());
        frame.put("url", storage.presignGet(item.key(), properties.frameUrlTtl()).toString());
        frame.put("width", item.width());
        frame.put("height", item.height());
        items.add(frame);
      }
      Map<String, Object> referenceFrames = new LinkedHashMap<>();
      referenceFrames.put("source", frames.source());
      referenceFrames.put("items", items);
      request.put("frames", referenceFrames);
    }
    return request;
  }
}
