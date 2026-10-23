package com.mairor.backend.guides;

/**
 * 가이드 목록 항목 (API-ANALYSIS-002 {@code GuideSummary}). 지금은 템플릿 예시용 최소 필드이며, 전체 필드는 가이드 조회(4A-4)에서 노션
 * API 명세대로 채운다.
 */
public record GuideSummaryResponse(
    String guideId, String title, String channelTitle, Integer stepCount, String thumbnailUrl) {}
