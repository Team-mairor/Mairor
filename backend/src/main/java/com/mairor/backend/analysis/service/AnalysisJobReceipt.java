package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import java.util.UUID;

/** 작업 접수 결과. */
public record AnalysisJobReceipt(
    UUID jobId,
    UUID videoId,
    ReceiptType receiptType,
    AnalysisStatus status,
    ProgressStage progressStage) {

  static AnalysisJobReceipt of(AnalysisJob job, ReceiptType type) {
    return new AnalysisJobReceipt(
        job.getId(), job.getVideo().getId(), type, job.getStatus(), job.getProgressStage());
  }
}
