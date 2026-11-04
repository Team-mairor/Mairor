package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.guides.entity.ReviewStatus;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * 회원이 보는 분석 작업 상태 한 건(API 명세 v2 {@code AnalysisJobStatus}). 상태 조회(API-VIDEO-003)와 분석 상태 SSE 가 같은 값을
 * 준다.
 *
 * @param stageProgress 지금 진행 단계 안의 숫자. 셀 수 없으면 {@code null}
 * @param foundProducts 찾은 제품. 제품 인식(RECOGNIZING_PRODUCTS)이 연결되기 전에는 늘 빈 목록이다
 * @param pollAfterSeconds 폴링할 때 다음 조회까지의 초. 더 바뀌지 않는 상태(실패·승인·반려)면 {@code null}
 */
public record AnalysisJobStatusView(
    UUID jobId,
    UUID videoId,
    AnalysisStatus status,
    ProgressStage progressStage,
    Integer progressPercent,
    Integer estimatedRemainingSeconds,
    StageProgress stageProgress,
    boolean retryable,
    ReviewStatus reviewStatus,
    boolean guideAvailable,
    UUID guideId,
    List<Object> foundProducts,
    int foundProductCount,
    Integer totalProductCount,
    String failureCode,
    String failureMessage,
    Integer pollAfterSeconds,
    Instant createdAt,
    Instant completedAt) {

  /** 더 바뀌지 않는 상태인지: 실패, 또는 검수 승인·반려. SSE 는 이 상태를 보낸 뒤 닫는다. */
  public boolean isFinal() {
    return status == AnalysisStatus.FAILED
        || reviewStatus == ReviewStatus.APPROVED
        || reviewStatus == ReviewStatus.REJECTED;
  }
}
