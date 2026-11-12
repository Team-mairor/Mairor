package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.log.AnalysisLogContext;
import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.event.ReferenceProductReconciliationRequested;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.service.GuideReviewService;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * AI 가이드 생성 결과를 작업·가이드에 반영한다. AI 콜백과 콜백 시간 초과 감시(상태 조회)가 같은 처리를 쓴다.
 *
 * <ul>
 *   <li>COMPLETED: 맡긴 작업의 결과인지 먼저 본다({@link AiResultCheck}: 영상 · 단계 ID · 영역). 어긋나면 작업 FAILED {@code
 *       AI_RESULT_MISMATCH}(재시도 불가)로 끝내고 가이드는 저장하지 않는다. 맞으면 가이드에 쉬운 설명({@code guide})·영역({@code
 *       area})·{@code meshVersion}을 저장하고 운영자 검수 없이 바로 공개(APPROVED, S15P31A306-409), 작업 COMPLETED ·
 *       DONE
 *   <li>FAILED: 작업 FAILED, {@code error.code}를 실패 코드로 바꿈(재시도 가능). {@code error.details}(단계별 이유)를 실패
 *       메시지에 붙이고, 자르지 않은 전체는 로그에 남긴다
 *   <li>이미 끝난 작업이면 아무것도 바꾸지 않는다(같은 콜백이 다시 올 수 있다)
 * </ul>
 *
 * <p>작업을 실제로 끝냈을 때만 같은 트랜잭션에서 {@link AnalysisJobNotifier}로 알린다.
 */
@Service
public class AiResultService {

  public enum Outcome {
    APPLIED,
    ALREADY_FINISHED
  }

  private static final Logger log = LoggerFactory.getLogger(AiResultService.class);
  private static final int MESH_VERSION_MAX = Guide.MESH_VERSION_MAX_LENGTH;

  private final AnalysisJobRepository jobs;
  private final GuideRepository guides;
  private final GuideReviewService reviews;
  private final AnalysisJobNotifier notifier;
  private final ObjectMapper objectMapper;
  private final Clock clock;
  private final ApplicationEventPublisher events;

  AiResultService(
      AnalysisJobRepository jobs,
      GuideRepository guides,
      GuideReviewService reviews,
      AnalysisJobNotifier notifier,
      ObjectMapper objectMapper,
      Clock clock,
      ApplicationEventPublisher events) {
    this.jobs = jobs;
    this.guides = guides;
    this.reviews = reviews;
    this.notifier = notifier;
    this.objectMapper = objectMapper;
    this.clock = clock;
    this.events = events;
  }

  /**
   * @throws BusinessException SERVICE_UNAVAILABLE(아직 모르는 AI 작업, {@link #unknownJob}),
   *     VALIDATION_FAILED(필수 칸 없음)
   */
  @Transactional
  public Outcome apply(AiGuideJobCallbackRequest result) {
    validate(result);
    AnalysisJob job =
        jobs.lockByAiJobId(result.jobId()).orElseThrow(() -> unknownJob(result.jobId()));
    try (var ignored = AnalysisLogContext.of(job)) {
      return applyTo(job, result);
    }
  }

  private Outcome applyTo(AnalysisJob job, AiGuideJobCallbackRequest result) {
    if (!job.isAwaitingAi()) {
      log.info("이미 끝난 작업의 AI 결과라 무시 jobId={} aiJobId={}", job.getId(), result.jobId());
      return Outcome.ALREADY_FINISHED;
    }
    if ("COMPLETED".equals(result.status())) {
      Guide guide =
          guides
              .findByAnalysisJobId(job.getId())
              .orElseThrow(() -> new IllegalStateException("작업 " + job.getId() + " 의 가이드가 없습니다."));
      List<String> problems =
          AiResultCheck.problems(
              job.getVideo().getYoutubeVideoId(),
              objectMapper.readTree(guide.getGuideInput()),
              // 프레임을 싣지 않고 맡긴 작업은 요청할 때 키를 비워 둔다(BuildGuideStep)
              guide.getFramesManifestKey() != null,
              result);
      if (!problems.isEmpty()) {
        String reason = String.join(" / ", problems);
        job.fail(
            AnalysisFailureCode.AI_RESULT_MISMATCH,
            AnalysisFailureCode.AI_RESULT_MISMATCH.defaultMessage() + " " + reason,
            clock.instant());
        log.warn(
            "AI 결과가 작업과 맞지 않아 실패 처리 jobId={} aiJobId={} problems={}",
            job.getId(),
            result.jobId(),
            reason);
        notifier.changed(job.getId());
        return Outcome.APPLIED;
      }
      JsonNode area = present(result.area()) ? result.area() : null;
      guide.recordAiResult(
          result.guide().toString(), area == null ? null : area.toString(), meshVersion(area));
      Instant now = clock.instant();
      reviews.publish(guide, now);
      job.complete(now);
      events.publishEvent(new ReferenceProductReconciliationRequested(guide.getId()));
      log.info(
          "AI 가이드 저장 · 공개 jobId={} aiJobId={} guideId={} steps={} area={}",
          job.getId(),
          result.jobId(),
          guide.getId(),
          result.guide().path("steps").size(),
          area != null);
    } else {
      String code = result.error() == null ? "" : result.error().path("code").asString("");
      AnalysisFailureCode failure =
          "GENERATION_FAILED".equals(code)
              ? AnalysisFailureCode.AI_GENERATION_FAILED
              : AnalysisFailureCode.AI_INTERNAL_ERROR;
      String message = AiResultCheck.failureMessage(result.error(), failure.defaultMessage());
      job.fail(failure, message, clock.instant());
      log.warn(
          "AI 가이드 생성 실패 jobId={} aiJobId={} code={} message={}",
          job.getId(),
          result.jobId(),
          code,
          message);
    }
    notifier.changed(job.getId());
    return Outcome.APPLIED;
  }

  /**
   * AI 결과가 오지 않은 작업을 시간 초과로 끝낸다(재시도 가능). 이미 끝났으면 바꾸지 않는다.
   *
   * @return 실제로 끝냈으면 true
   */
  @Transactional
  public boolean timeout(String aiJobId, String reason) {
    AnalysisJob job = jobs.lockByAiJobId(aiJobId).orElse(null);
    if (job == null || !job.isAwaitingAi()) {
      return false;
    }
    job.fail(AnalysisFailureCode.ANALYSIS_TIMEOUT, reason, clock.instant());
    notifier.changed(job.getId());
    try (var ignored = AnalysisLogContext.of(job)) {
      log.warn("AI 결과 시간 초과 jobId={} aiJobId={} reason={}", job.getId(), aiJobId, reason);
    }
    return true;
  }

  /** 실행 중에는 처리에 필요한 칸만 본다. 전체 형식은 테스트가 공유 스키마로 확인한다. */
  /**
   * 모르는 AI 작업. AI 는 202 를 보낸 직후 작업을 시작해, BE 가 {@code ai_job_id}를 커밋하기 전에 콜백이 오면 이렇게 보인다. 503 이면 AI
   * 가 1 · 5 · 25초 뒤 다시 보내므로({@code docs/references/ai-api.md} "콜백 재시도") 그사이 커밋된 작업에 반영된다. 정말 없는
   * 작업이면 AI 가 네 번 보내고 멈춘다.
   */
  private static BusinessException unknownJob(String aiJobId) {
    log.warn("모르는 AI 작업의 콜백이라 503 으로 답함(AI 가 다시 보냄) aiJobId={}", aiJobId);
    return new BusinessException(ErrorCode.SERVICE_UNAVAILABLE, "아직 모르는 AI 작업입니다: " + aiJobId);
  }

  private static void validate(AiGuideJobCallbackRequest result) {
    if (result == null || result.jobId() == null || result.jobId().isBlank()) {
      throw new BusinessException(ErrorCode.VALIDATION_FAILED, "jobId 가 없습니다.");
    }
    if ("COMPLETED".equals(result.status())) {
      if (result.guide() == null || !result.guide().path("steps").isArray()) {
        throw new BusinessException(
            ErrorCode.VALIDATION_FAILED, "COMPLETED 인데 guide.steps 가 없습니다.");
      }
    } else if (!"FAILED".equals(result.status())) {
      throw new BusinessException(
          ErrorCode.VALIDATION_FAILED, "status 는 COMPLETED 또는 FAILED 여야 합니다: " + result.status());
    }
  }

  private static boolean present(JsonNode node) {
    return node != null && !node.isNull() && !node.isMissingNode();
  }

  private static String meshVersion(JsonNode area) {
    if (area == null) {
      return null;
    }
    String version = area.path("meshVersion").asString("");
    if (version.isBlank()) {
      return null;
    }
    return version.length() > MESH_VERSION_MAX ? version.substring(0, MESH_VERSION_MAX) : version;
  }
}
