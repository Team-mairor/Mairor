package com.mairor.backend.videos.service;

import java.time.Instant;
import java.util.UUID;

/**
 * 인기 Top 4 집계 한 줄. 영상 메타 · 승인 가이드 ID 와 고른 서로 다른 회원 수 · 마지막으로 고른 시각.
 *
 * @param guideId 검수 승인된 가이드 ID. 없으면 null
 * @param members 기간 안에 이 영상을 고른 서로 다른 회원 수
 * @param lastSelectedAt 기간 안에 마지막으로 고른 시각. 회원 수가 같으면 늦은 쪽이 앞이다
 */
public record PopularVideoRow(
    UUID videoId,
    String youtubeVideoId,
    String title,
    String channelTitle,
    int durationSeconds,
    String thumbnailUrl,
    Instant publishedAt,
    UUID guideId,
    long members,
    Instant lastSelectedAt) {}
