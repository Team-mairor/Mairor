package com.mairor.backend.common.external.youtube;

import java.time.Instant;

/**
 * {@code videos.list} 한 항목에서 쓰는 값.
 *
 * @param youtubeVideoId 영상 ID
 * @param title 제목
 * @param channelTitle 채널 이름
 * @param description 설명란(챕터를 여기서 읽는다)
 * @param durationSeconds 길이(초). 라이브 · 예정 영상은 0
 * @param thumbnailUrl 썸네일(high → medium → default 순). 없으면 null
 * @param viewCount 조회수. 숨긴 영상은 null
 * @param publishedAt 게시 시각
 * @param privacyStatus {@code public} · {@code unlisted} · {@code private}
 * @param license {@code youtube}(표준) · {@code creativeCommon}(CC BY)
 * @param ageRestricted 연령 제한({@code contentRating.ytRating = ytAgeRestricted})
 * @param liveBroadcastContent {@code none} · {@code live} · {@code upcoming}
 */
public record YouTubeVideo(
    String youtubeVideoId,
    String title,
    String channelTitle,
    String description,
    int durationSeconds,
    String thumbnailUrl,
    Long viewCount,
    Instant publishedAt,
    String privacyStatus,
    String license,
    boolean ageRestricted,
    String liveBroadcastContent) {

  public static final String CREATIVE_COMMON = "creativeCommon";

  /** CC BY 영상인가. 분석은 이 영상만 받는다(11.04 결정). */
  public boolean creativeCommon() {
    return CREATIVE_COMMON.equals(license);
  }

  /** 분석할 수 있는 영상인가: 공개 · CC BY · 연령 제한 없음 · 라이브 아님 · 길이 있음. */
  public boolean analyzable() {
    return "public".equals(privacyStatus)
        && creativeCommon()
        && !ageRestricted
        && "none".equals(liveBroadcastContent)
        && durationSeconds > 0;
  }
}
