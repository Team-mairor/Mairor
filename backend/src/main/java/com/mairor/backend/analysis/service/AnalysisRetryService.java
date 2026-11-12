package com.mairor.backend.analysis.service;

import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

/**
 * 회원 분석 재시도(API-VIDEO-006). 재시도할 수 있는 실패로 끝난 작업을 다시 돌리고 그 상태를 준다. 노트북이 영상 처리를 끝낸 작업은 가이드 생성 요청만 다시
 * 하고, 그 전에 멈춘 작업은 대기열로 돌아가 처음부터 한다({@link com.mairor.backend.analysis.entity.AnalysisJob#retry()}).
 * 하루 분석 한도는 세지 않고 작업마다 시도 횟수 상한만 있다.
 */
@Service
public class AnalysisRetryService {

  private static final Logger log = LoggerFactory.getLogger(AnalysisRetryService.class);

  private final AnalysisJobWriter writer;
  private final AnalysisJobStatusService statuses;
  private final AnalysisRequestProperties properties;

  AnalysisRetryService(
      AnalysisJobWriter writer,
      AnalysisJobStatusService statuses,
      AnalysisRequestProperties properties) {
    this.writer = writer;
    this.statuses = statuses;
    this.properties = properties;
  }

  /**
   * @return 이어서 볼 작업의 상태. 같은 영상의 다른 진행 중 작업에 합류했으면 그 작업(jobId 가 다르다)
   * @throws com.mairor.backend.common.error.BusinessException 404 {@code NOT_FOUND} — 없거나 내가 요청 ·
   *     합류한 작업이 아님, 409 {@code ANALYSIS_NOT_RETRYABLE} — 완료 · 재시도할 수 없는 실패 · 시도 횟수 상한
   */
  public AnalysisJobStatusView retry(UUID userId, UUID jobId) {
    UUID target;
    try {
      target = writer.retryForMember(jobId, userId, properties);
    } catch (DataIntegrityViolationException conflict) {
      // 같은 영상의 새 분석 요청과 겹쳤다. 다시 하면 그 작업에 합류한다
      log.info("분석 재시도가 새 분석 요청과 겹쳐 다시 시도합니다. jobId={}", jobId);
      target = writer.retryForMember(jobId, userId, properties);
    }
    UUID found = target;
    return statuses
        .find(userId, found)
        .orElseThrow(() -> new IllegalStateException("재시도한 작업 " + found + " 을 찾지 못했습니다."));
  }
}
