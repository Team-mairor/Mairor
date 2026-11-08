package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.repository.AnalysisJobRequestRecordRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * 회원이 분석 작업을 볼 수 있는지 정한다. 상태 조회(API-VIDEO-003)와 분석 상태 SSE 가 함께 쓴다.
 *
 * <p>작업을 처음 요청한 회원({@code requestedBy})과 분석 요청 기록({@code analysis_job_requests})이 있는 회원(새 작업 · 합류,
 * API-VIDEO-002)이 본다. 운영 명령으로 만든 작업은 회원이 합류하기 전까지 아무 회원도 못 본다. 없는 작업과 볼 수 없는 작업은 구분하지 않고 404 다(다른
 * 회원의 작업이 있는지 알 수 없게).
 */
@Component
public class AnalysisJobAccess {

  private final AnalysisJobRepository jobs;
  private final AnalysisJobRequestRecordRepository requests;

  AnalysisJobAccess(AnalysisJobRepository jobs, AnalysisJobRequestRecordRepository requests) {
    this.jobs = jobs;
    this.requests = requests;
  }

  /**
   * @throws BusinessException 404 {@code NOT_FOUND} — 없는 작업이거나 이 회원이 볼 수 없는 작업
   */
  public AnalysisJob load(UUID userId, UUID jobId) {
    Objects.requireNonNull(userId, "userId");
    return jobs.findById(jobId)
        .filter(job -> canView(userId, job))
        .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
  }

  public boolean canView(UUID userId, AnalysisJob job) {
    return userId.equals(job.getRequestedBy())
        || requests.existsByAnalysisJobIdAndUserId(job.getId(), userId);
  }
}
