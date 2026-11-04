package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * 회원이 분석 작업을 볼 수 있는지 정한다. 상태 조회(API-VIDEO-003)와 분석 상태 SSE 가 함께 쓴다.
 *
 * <p>지금은 작업을 요청한 회원({@code requestedBy})만 본다. 운영 명령으로 만든 작업({@code requestedBy = null})은 아무 회원도 못
 * 본다. 진행 작업에 합류한 회원(API-VIDEO-002 JOINED_JOB)은 002 가 합류 기록을 만들 때 여기서 넓힌다. 없는 작업과 볼 수 없는 작업은 구분하지 않고
 * 404 다(다른 회원의 작업이 있는지 알 수 없게).
 */
@Component
public class AnalysisJobAccess {

  private final AnalysisJobRepository jobs;

  AnalysisJobAccess(AnalysisJobRepository jobs) {
    this.jobs = jobs;
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
    return userId.equals(job.getRequestedBy());
  }
}
