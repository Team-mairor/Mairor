package com.mairor.backend.videos.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

/** 인기 영상 Top 4(API 명세 v2 PopularVideoResponse). */
public record PopularVideoResponse(
    @Schema(description = "순위 순 영상. 서로 다른 영상 1~4개") List<PopularVideoItem> items,
    @Schema(
            description = "순위 기준. DISTINCT_MEMBER_SELECTIONS = 영상을 고른 서로 다른 회원 수",
            example = "DISTINCT_MEMBER_SELECTIONS")
        String rankingBasis,
    @Schema(description = "집계 기간. LAST_30_DAYS = 최근 30일", example = "LAST_30_DAYS")
        String aggregationScope,
    @Schema(description = "집계한 시각(UTC)", example = "2026-11-11T09:00:00Z") Instant updatedAt,
    @Schema(description = "다음에 다시 셀 시각(UTC)", example = "2026-11-11T09:10:00Z")
        Instant nextRefreshAt) {}
