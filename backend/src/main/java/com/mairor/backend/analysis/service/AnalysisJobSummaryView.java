package com.mairor.backend.analysis.service;

import com.mairor.backend.guides.entity.ReviewStatus;
import java.time.Instant;
import java.util.UUID;

/**
 * 내 분석 목록(API-VIDEO-007)의 한 줄. 요청 기록 · 작업 · 영상 · 가이드를 한 번에 읽은 값이다.
 *
 * @param guideId 작업이 만든 가이드 ID. 회원에게는 검수 승인일 때만 보낸다
 * @param requestedAt 이 회원이 요청하거나 합류한 시각
 * @param reviewedAt 검수(승인 · 반려)한 시각. 검수 전이면 {@code null}
 */
public record AnalysisJobSummaryView(
    UUID jobId,
    UUID videoId,
    String youtubeVideoId,
    String title,
    String thumbnailUrl,
    ReviewStatus reviewStatus,
    UUID guideId,
    Instant requestedAt,
    Instant reviewedAt) {}
