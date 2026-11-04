package com.mairor.backend.analysis.dto.response;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.service.AnalysisJobStatusView;
import com.mairor.backend.analysis.service.StageProgress;
import com.mairor.backend.guides.entity.ReviewStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 분석 작업 상태(API 명세 v2 {@code AnalysisJobStatus}). 상태 조회와 분석 상태 SSE 가 같은 모양을 준다. */
public record AnalysisJobStatusResponse(
    @Schema(description = "분석 작업 ID", example = "2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f") UUID jobId,
    @Schema(description = "영상 내부 ID", example = "7d3e2a1b-6c5f-4e8d-9a0b-2c3d4e5f6a7b")
        UUID videoId,
    @Schema(description = "작업 상태", example = "RUNNING") AnalysisStatus status,
    @Schema(description = "진행 단계. FAILED 면 멈춘 단계", example = "BUILDING_GUIDE")
        ProgressStage progressStage,
    @Schema(description = "전체 진행률(0~100). 계산할 수 있을 때만 있고 지금은 COMPLETED 일 때만 100", nullable = true)
        Integer progressPercent,
    @Schema(description = "남은 시간(초). 계산할 수 있을 때만 있다(지금은 늘 null)", nullable = true)
        Integer estimatedRemainingSeconds,
    @Schema(description = "지금 진행 단계 안에서 센 수. 셀 수 없으면 null(지금은 가이드 구성 중에만 있다)", nullable = true)
        StageProgressResponse stageProgress,
    @Schema(description = "실패했을 때 재시도할 수 있는지", example = "false") boolean retryable,
    @Schema(description = "가이드 검수 상태. 가이드가 아직 없으면 NOT_READY", example = "NOT_READY")
        ReviewStatus reviewStatus,
    @Schema(description = "따라 하기에 쓸 수 있는 가이드가 있는지(검수 승인)", example = "false")
        boolean guideAvailable,
    @Schema(description = "승인된 가이드 ID. 승인 전에는 null", nullable = true) UUID guideId,
    @Schema(description = "찾은 제품. 제품 인식이 연결되기 전에는 늘 빈 목록이다") List<Object> foundProducts,
    @Schema(description = "찾은 제품 수. 제품 인식이 연결되기 전에는 0", example = "0") int foundProductCount,
    @Schema(description = "영상의 전체 제품 수. 모르면 null(제품 인식이 연결되기 전에는 늘 null)", nullable = true)
        Integer totalProductCount,
    @Schema(description = "실패 원인 코드. 실패가 아니면 null", nullable = true, example = "ANALYSIS_TIMEOUT")
        String failureCode,
    @Schema(description = "실패 원인 설명. 실패가 아니면 null", nullable = true) String failureMessage,
    @Schema(
            description = "폴링할 때 다음 조회까지의 초. 실패·승인·반려면 null(더 바뀌지 않음)",
            nullable = true,
            example = "3")
        Integer pollAfterSeconds,
    @Schema(description = "작업을 만든 시각", example = "2026-11-03T03:00:00Z") Instant createdAt,
    @Schema(description = "분석을 마친 시각(COMPLETED). 그 밖에는 null", nullable = true)
        Instant completedAt) {

  /** 지금 진행 단계 안에서 센 수. 전체 %가 아니다. */
  public record StageProgressResponse(
      @Schema(
              description =
                  "센 대상. FRAMES 사진 받기, LANDMARKS 얼굴 점 찾기, AREA 영역 만들기(단계), EXPLANATION 쉬운 설명(단계)",
              example = "LANDMARKS")
          StageProgress.Item item,
      @Schema(description = "끝난 수(실패한 것 포함)", example = "840") long done,
      @Schema(description = "전체 수", example = "2000") long total) {}

  public static AnalysisJobStatusResponse from(AnalysisJobStatusView view) {
    StageProgress progress = view.stageProgress();
    return new AnalysisJobStatusResponse(
        view.jobId(),
        view.videoId(),
        view.status(),
        view.progressStage(),
        view.progressPercent(),
        view.estimatedRemainingSeconds(),
        progress == null
            ? null
            : new StageProgressResponse(progress.item(), progress.done(), progress.total()),
        view.retryable(),
        view.reviewStatus(),
        view.guideAvailable(),
        view.guideId(),
        view.foundProducts(),
        view.foundProductCount(),
        view.totalProductCount(),
        view.failureCode(),
        view.failureMessage(),
        view.pollAfterSeconds(),
        view.createdAt(),
        view.completedAt());
  }
}
