package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.guides.entity.ReviewStatus;
import java.util.UUID;

/**
 * 회원 분석 요청 결과(API 명세 v2 AnalysisJobReceipt). 재사용({@code REUSED_GUIDE})이면 {@code jobId}가 없고 승인 가이드
 * ID 가 있다.
 */
public record AnalysisRequestReceipt(
    UUID jobId,
    UUID videoId,
    ReceiptType receiptType,
    AnalysisStatus status,
    ProgressStage progressStage,
    UUID guideId,
    ReviewStatus reviewStatus,
    Integer pollAfterSeconds) {

  static AnalysisRequestReceipt reused(UUID videoId, UUID guideId) {
    return new AnalysisRequestReceipt(
        null,
        videoId,
        ReceiptType.REUSED_GUIDE,
        AnalysisStatus.COMPLETED,
        ProgressStage.DONE,
        guideId,
        ReviewStatus.APPROVED,
        null);
  }

  static AnalysisRequestReceipt of(ReceiptType type, AnalysisJobStatusView status) {
    return new AnalysisRequestReceipt(
        status.jobId(),
        status.videoId(),
        type,
        status.status(),
        status.progressStage(),
        status.guideId(),
        status.reviewStatus(),
        status.pollAfterSeconds());
  }
}
