package com.mairor.backend.videos.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/** 검색 결과 한 줄(API 명세 v2 VideoSearchItem). */
public record VideoSearchItem(
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
    @Schema(description = "검수 승인된 가이드 ID. 승인 전 · 없음은 null") UUID guideId,
    @Schema(description = "승인된 가이드가 있어 바로 따라 할 수 있는가", example = "false") boolean guideAvailable) {}
