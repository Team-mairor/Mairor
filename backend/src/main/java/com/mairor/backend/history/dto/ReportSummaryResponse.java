package com.mairor.backend.history.dto;

import com.mairor.backend.history.entity.HistoryRecord;
import com.mairor.backend.photos.dto.PhotoResponse;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/** 리포트 목록 한 줄(API 명세 v2 ReportSummary). 완료할 때 고정한 값이다. */
public record ReportSummaryResponse(
    @Schema(description = "리포트 ID", example = "00000000-0000-4000-8000-000000000601") UUID recordId,
    @Schema(
            description = "따라 한 가이드 ID. 다시 따라 하기에 쓴다",
            example = "00000000-0000-4000-8000-000000000201")
        UUID guideId,
    @Schema(description = "내부 영상 ID", example = "00000000-0000-4000-8000-000000000101")
        UUID videoId,
    @Schema(description = "YouTube 영상 ID", example = "VxAXD6PP76I") String youtubeVideoId,
    @Schema(description = "완료할 때의 영상 제목", example = "데일리 메이크업 튜토리얼") String videoTitle,
    @Schema(description = "완료할 때의 채널 이름", example = "메이크업채널") String channelTitle,
    @Schema(
            description = "썸네일 주소. 없으면 null",
            example = "https://i.ytimg.com/vi/VxAXD6PP76I/hqdefault.jpg")
        String thumbnailUrl,
    @Schema(description = "완료 시각(UTC)", example = "2026-11-11T09:00:00Z") Instant completedAt,
    @Schema(description = "완성 사진(가장 나중에 찍은 단계 사진). 없거나 지우는 중이면 null") PhotoResponse completedPhoto,
    @Schema(description = "단계 수", example = "12") int stepCount,
    @Schema(description = "대체 제품으로 따라 한 단계 수", example = "3") int substituteCount) {

  public static ReportSummaryResponse from(HistoryRecord record, PhotoResponse completedPhoto) {
    return new ReportSummaryResponse(
        record.getId(),
        record.getGuideId(),
        record.getVideoId(),
        record.getYoutubeVideoId(),
        record.getVideoTitle(),
        record.getChannelTitle(),
        record.getThumbnailUrl(),
        record.getCompletedAt(),
        completedPhoto,
        record.getStepCount(),
        record.getSubstituteCount());
  }
}
