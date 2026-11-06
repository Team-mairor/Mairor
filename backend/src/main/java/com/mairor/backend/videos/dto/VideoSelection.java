package com.mairor.backend.videos.dto;

import com.mairor.backend.guides.entity.ReviewStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 고른 영상(API 명세 v2 VideoSelection). 임베드 재생을 하지 않아 embeddable 칸은 없다. */
public record VideoSelection(
    @Schema(description = "서비스 내부 영상 ID. 분석 요청(API-VIDEO-002)에 쓴다") UUID videoId,
    @Schema(description = "YouTube 영상 ID", example = "VxAXD6PP76I") String youtubeVideoId,
    @Schema(description = "제목", example = "데일리 메이크업 튜토리얼") String title,
    @Schema(description = "채널 이름", example = "메이크업채널") String channelTitle,
    @Schema(description = "길이(초)", example = "1858") int durationSeconds,
    @Schema(
            description = "썸네일 주소. 없으면 null",
            example = "https://i.ytimg.com/vi/VxAXD6PP76I/hqdefault.jpg")
        String thumbnailUrl,
    @Schema(description = "조회수. 숨긴 영상은 null", example = "120345") Long viewCount,
    @Schema(description = "게시 시각(UTC). 모르면 null", example = "2026-10-01T09:00:00Z")
        Instant publishedAt,
    @Schema(description = "설명란 챕터. 없으면 빈 목록") List<VideoChapter> chapters,
    @Schema(description = "검수 승인된 가이드 ID. 승인 전 · 없음은 null") UUID guideId,
    @Schema(description = "승인된 가이드가 있어 바로 따라 할 수 있는가", example = "false") boolean guideAvailable,
    @Schema(description = "내가 요청해 진행 중인 분석 작업 ID. 없으면 null") UUID analysisJobId,
    @Schema(
            description = "분석이 진행 중이면 NOT_READY, 아니면 가장 최근 가이드의 검수 상태, 분석한 적 없으면 null",
            example = "APPROVED")
        ReviewStatus reviewStatus) {}
