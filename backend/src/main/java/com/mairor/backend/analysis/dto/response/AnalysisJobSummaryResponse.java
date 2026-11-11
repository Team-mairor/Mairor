package com.mairor.backend.analysis.dto.response;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.service.AnalysisJobSummaryView;
import com.mairor.backend.guides.entity.ReviewStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/** 내 분석 목록의 한 항목(API 명세 v2 {@code AnalysisJobSummary}). 홈의 '검수 중 가이드' 카드 하나다. */
public record AnalysisJobSummaryResponse(
    @Schema(description = "분석 작업 ID", example = "2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f") UUID jobId,
    @Schema(description = "영상 내부 ID", example = "7d3e2a1b-6c5f-4e8d-9a0b-2c3d4e5f6a7b")
        UUID videoId,
    @Schema(description = "유튜브 영상 ID", example = "VxAXD6PP76I") String youtubeVideoId,
    @Schema(description = "영상 제목", example = "완성도 up! 데일리 메이크업") String title,
    @Schema(
            description = "영상 썸네일 주소. 없으면 null",
            nullable = true,
            example = "https://i.ytimg.com/vi/VxAXD6PP76I/hqdefault.jpg")
        String thumbnailUrl,
    @Schema(description = "작업 상태. 이 목록에는 분석이 끝난 작업만 나온다", example = "COMPLETED")
        AnalysisStatus status,
    @Schema(description = "가이드 검수 상태", example = "PENDING") ReviewStatus reviewStatus,
    @Schema(description = "승인된 가이드 ID. 승인 전 · 반려면 null", nullable = true) UUID guideId,
    @Schema(description = "내가 요청하거나 합류한 시각", example = "2026-11-11T00:42:24Z") Instant requestedAt,
    @Schema(description = "검수한 시각. 검수 전이면 null", nullable = true) Instant reviewedAt) {

  public static AnalysisJobSummaryResponse from(AnalysisJobSummaryView view) {
    boolean approved = view.reviewStatus() == ReviewStatus.APPROVED;
    return new AnalysisJobSummaryResponse(
        view.jobId(),
        view.videoId(),
        view.youtubeVideoId(),
        view.title(),
        view.thumbnailUrl(),
        AnalysisStatus.COMPLETED,
        view.reviewStatus(),
        approved ? view.guideId() : null,
        view.requestedAt(),
        view.reviewedAt());
  }
}
