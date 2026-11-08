package com.mairor.backend.analysis.dto.response;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.service.AnalysisRequestReceipt;
import com.mairor.backend.analysis.service.ReceiptType;
import com.mairor.backend.guides.entity.ReviewStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

/** 회원 분석 요청 결과(API 명세 v2 AnalysisJobReceipt). */
public record AnalysisRequestReceiptResponse(
    @Schema(description = "분석 작업 ID. 진행 화면(SSE · 상태 조회)에 쓴다. 가이드 재사용이면 null", nullable = true)
        UUID jobId,
    @Schema(description = "내부 영상 ID") UUID videoId,
    @Schema(
            description = "REUSED_GUIDE(승인 가이드 재사용) · JOINED_JOB(진행 중 작업에 합류) · NEW_JOB(새 작업)",
            example = "NEW_JOB")
        ReceiptType receiptType,
    @Schema(description = "작업 상태. 재사용이면 COMPLETED", example = "PENDING") AnalysisStatus status,
    @Schema(description = "진행 단계. 재사용이면 DONE", example = "QUEUED") ProgressStage progressStage,
    @Schema(description = "승인된 가이드 ID. 재사용이면 있고, 그 밖에는 null", nullable = true) UUID guideId,
    @Schema(description = "검수 상태. 재사용이면 APPROVED, 진행 중이면 NOT_READY", example = "NOT_READY")
        ReviewStatus reviewStatus,
    @Schema(description = "폴링할 때 다음 조회까지의 초. 재사용이면 null", nullable = true, example = "3")
        Integer pollAfterSeconds) {

  public static AnalysisRequestReceiptResponse from(AnalysisRequestReceipt receipt) {
    return new AnalysisRequestReceiptResponse(
        receipt.jobId(),
        receipt.videoId(),
        receipt.receiptType(),
        receipt.status(),
        receipt.progressStage(),
        receipt.guideId(),
        receipt.reviewStatus(),
        receipt.pollAfterSeconds());
  }
}
