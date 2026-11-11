package com.mairor.backend.videos.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/**
 * 인기 영상 한 줄(API 명세 v2 PopularVideoItem). 검색 결과 한 줄의 모든 칸과 순위, 내부 영상 ID. 인기 영상은 늘 저장돼 있어 카드를 누르면 영상
 * 선택 없이 이 ID 로 바로 분석을 요청할 수 있다.
 */
public record PopularVideoItem(
    @Schema(description = "순위(1부터)", example = "1") int rank,
    @Schema(
            description = "내부 영상 ID. 가이드가 없을 때 분석 요청(API-VIDEO-002)의 videoId 로 쓴다",
            example = "3f6c2a1e-8b4d-4c2a-9f1e-2d7b5a9c0e11")
        UUID videoId,
    @Schema(description = "YouTube 영상 ID", example = "VxAXD6PP76I") String youtubeVideoId,
    @Schema(description = "제목", example = "데일리 메이크업 튜토리얼") String title,
    @Schema(description = "채널 이름", example = "메이크업채널") String channelTitle,
    @Schema(description = "길이(초)", example = "1858") int durationSeconds,
    @Schema(
            description = "썸네일 주소. 없으면 null",
            example = "https://i.ytimg.com/vi/VxAXD6PP76I/hqdefault.jpg")
        String thumbnailUrl,
    @Schema(description = "조회수. 저장하지 않아 늘 null") Long viewCount,
    @Schema(description = "게시 시각(UTC). 모르면 null", example = "2026-10-01T09:00:00Z")
        Instant publishedAt,
    @Schema(description = "검수 승인된 가이드 ID. 승인 전 · 없음은 null") UUID guideId,
    @Schema(description = "승인된 가이드가 있어 바로 따라 할 수 있는가", example = "false") boolean guideAvailable) {}
