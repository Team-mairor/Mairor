package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 회원이 보는 분석 작업 상태({@link AnalysisJobStatusView})를 만든다. 상태 조회(API-VIDEO-003)와 분석 상태 SSE 가 이것으로 같은 값을
 * 만든다. 작업과 그 작업의 가이드를 읽어 칸을 채운다.
 */
@Service
public class AnalysisJobStatusService {

  private static final Logger log = LoggerFactory.getLogger(AnalysisJobStatusService.class);

  private final AnalysisJobAccess access;
  private final AnalysisJobRepository jobs;
  private final GuideRepository guides;
  private final AnalysisStatusProperties properties;
  private final ObjectMapper objectMapper;

  AnalysisJobStatusService(
      AnalysisJobAccess access,
      AnalysisJobRepository jobs,
      GuideRepository guides,
      AnalysisStatusProperties properties,
      ObjectMapper objectMapper) {
    this.access = access;
    this.jobs = jobs;
    this.guides = guides;
    this.properties = properties;
    this.objectMapper = objectMapper;
  }

  /**
   * 회원의 작업 상태.
   *
   * @throws com.mairor.backend.common.error.BusinessException 404 {@code NOT_FOUND} — 없거나 볼 수 없는 작업
   */
  @Transactional(readOnly = true)
  public AnalysisJobStatusView get(UUID userId, UUID jobId) {
    return assemble(access.load(userId, jobId));
  }

  /**
   * 작업의 지금 상태. 권한은 보지 않는다. 분석 상태 SSE 가 연결을 연 뒤(권한은 연결할 때 {@link AnalysisJobAccess}로 확인) 바뀔 때마다 다시
   * 읽는다.
   *
   * @return 작업이 없으면(지워짐) 빈 값
   */
  @Transactional(readOnly = true)
  public Optional<AnalysisJobStatusView> find(UUID jobId) {
    return jobs.findById(jobId).map(this::assemble);
  }

  /** 작업 하나의 상태를 만든다. 가이드를 읽으므로 트랜잭션 안에서 부른다. */
  AnalysisJobStatusView assemble(AnalysisJob job) {
    Optional<Guide> guide = guides.findByAnalysisJobId(job.getId());
    ReviewStatus reviewStatus = guide.map(Guide::getReviewStatus).orElse(ReviewStatus.NOT_READY);
    boolean approved = reviewStatus == ReviewStatus.APPROVED;
    boolean completed = job.getStatus() == AnalysisStatus.COMPLETED;
    boolean finished =
        job.getStatus() == AnalysisStatus.FAILED
            || approved
            || reviewStatus == ReviewStatus.REJECTED;
    return new AnalysisJobStatusView(
        job.getId(),
        job.getVideo().getId(),
        job.getStatus(),
        job.getProgressStage(),
        job.getProgressPercent(),
        null,
        StageProgress.of(job.getStatus(), job.getProgressStage(), progress(job)),
        job.isRetryable(),
        reviewStatus,
        approved,
        approved ? guide.get().getId() : null,
        List.of(),
        0,
        null,
        job.getFailureCode(),
        job.getFailureMessage(),
        finished ? null : (int) properties.pollAfter().toSeconds(),
        job.getCreatedAt(),
        completed ? job.getFinishedAt() : null);
  }

  private JsonNode progress(AnalysisJob job) {
    String json = job.getAiProgress();
    if (json == null) {
      return null;
    }
    try {
      return objectMapper.readTree(json);
    } catch (JacksonException e) {
      // 저장할 때 검사하므로 생기지 않는다. 생겨도 상태 조회를 막지 않는다
      log.warn("저장된 AI 진행 숫자를 읽지 못함 jobId={}", job.getId(), e);
      return null;
    }
  }
}
