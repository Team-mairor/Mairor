package com.mairor.backend.analysis.dto.response;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.service.AnalysisJobReceipt;
import com.mairor.backend.analysis.service.ReceiptType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

/** 분석 작업 접수 결과. API 명세 v2 AnalysisJobReceipt 의 운영용 일부다. */
public record AnalysisJobReceiptResponse(
    @Schema(description = "분석 작업 ID") UUID jobId,
    @Schema(description = "내부 영상 ID") UUID videoId,
    @Schema(description = "NEW_JOB(새 작업) 또는 JOINED_JOB(진행 중 작업에 합류)", example = "NEW_JOB")
        ReceiptType receiptType,
    @Schema(description = "작업 상태", example = "PENDING") AnalysisStatus status,
    @Schema(description = "진행 단계", example = "QUEUED") ProgressStage progressStage) {

  public static AnalysisJobReceiptResponse from(AnalysisJobReceipt receipt) {
    return new AnalysisJobReceiptResponse(
        receipt.jobId(),
        receipt.videoId(),
        receipt.receiptType(),
        receipt.status(),
        receipt.progressStage());
  }
}
