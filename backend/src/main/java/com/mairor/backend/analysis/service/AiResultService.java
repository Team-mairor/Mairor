package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.repository.GuideRepository;
import java.time.Clock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;

/**
 * AI 가이드 생성 결과를 작업·가이드에 반영한다. AI 콜백과 콜백 시간 초과 감시(상태 조회)가 같은 처리를 쓴다.
 *
 * <ul>
 *   <li>COMPLETED: 가이드에 쉬운 설명({@code guide})·영역({@code area})·{@code meshVersion}을 저장하고 검수 PENDING,
 *       작업 COMPLETED · DONE
 *   <li>FAILED: 작업 FAILED, {@code error.code}를 실패 코드로 바꿈(재시도 가능)
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
  private final AnalysisJobNotifier notifier;
  private final Clock clock;

  AiResultService(
      AnalysisJobRepository jobs,
      GuideRepository guides,
      AnalysisJobNotifier notifier,
      Clock clock) {
    this.jobs = jobs;
    this.guides = guides;
    this.notifier = notifier;
    this.clock = clock;
  }

  /**
   * @throws BusinessException NOT_FOUND(모르는 AI 작업), VALIDATION_FAILED(필수 칸 없음)
   */
  @Transactional
  public Outcome apply(AiGuideJobCallbackRequest result) {
    validate(result);
    AnalysisJob job =
        jobs.lockByAiJobId(result.jobId())
            .orElseThrow(
                () ->
                    new BusinessException(ErrorCode.NOT_FOUND, "모르는 AI 작업입니다: " + result.jobId()));
    if (!job.isAwaitingAi()) {
      log.info("이미 끝난 작업의 AI 결과라 무시 jobId={} aiJobId={}", job.getId(), result.jobId());
      return Outcome.ALREADY_FINISHED;
    }
    if ("COMPLETED".equals(result.status())) {
      Guide guide =
          guides
              .findByAnalysisJobId(job.getId())
              .orElseThrow(() -> new IllegalStateException("작업 " + job.getId() + " 의 가이드가 없습니다."));
      JsonNode area = present(result.area()) ? result.area() : null;
      guide.recordAiResult(
          result.guide().toString(), area == null ? null : area.toString(), meshVersion(area));
      job.complete(clock.instant());
      log.info(
          "AI 가이드 저장 jobId={} aiJobId={} guideId={} steps={} area={}",
          job.getId(),
          result.jobId(),
          guide.getId(),
          result.guide().path("steps").size(),
          area != null);
    } else {
      String code = result.error() == null ? "" : result.error().path("code").asString("");
      String message =
          result.error() == null ? null : result.error().path("message").asString(null);
      AnalysisFailureCode failure =
          "GENERATION_FAILED".equals(code)
              ? AnalysisFailureCode.AI_GENERATION_FAILED
              : AnalysisFailureCode.AI_INTERNAL_ERROR;
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
    log.warn("AI 결과 시간 초과 jobId={} aiJobId={} reason={}", job.getId(), aiJobId, reason);
    return true;
  }

  /** 실행 중에는 처리에 필요한 칸만 본다. 전체 형식은 테스트가 공유 스키마로 확인한다. */
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
