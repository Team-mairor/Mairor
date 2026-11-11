package com.mairor.backend.videos.service;

import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.videos.dto.PopularVideoItem;
import com.mairor.backend.videos.dto.PopularVideoResponse;
import com.mairor.backend.videos.repository.VideoSelectionRecordRepository;
import com.mairor.backend.videos.support.VideoErrors;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Limit;
import org.springframework.stereotype.Service;

/**
 * 서비스 안 인기 영상 Top 4(API-VIDEO-005). YouTube 순위가 아니라 회원이 많이 고른(API-VIDEO-001) 영상이다(S15P31A306-403).
 *
 * <p>최근 30일 동안 영상을 고른 서로 다른 회원 수로 센다. 같으면 마지막 선택이 늦은 순이다. 승인 가이드 영상으로 채우지 않는다(명세).
 *
 * <p>선택은 분석할 수 있는 영상만 성공하므로 <b>선택할 때 분석할 수 있던</b> 영상만 들어온다. 그 뒤 비공개 · 삭제된 영상은 기간 동안 남을 수 있지만, 카드를
 * 눌러 분석을 요청하면(API-VIDEO-002) 라이선스 · 공개 여부를 다시 확인해 409 로 막는다. 응답 때마다 YouTube 를 부르지 않으려는
 * 선택이다(S15P31A306-403).
 *
 * <p>센 결과를 서버 메모리에 10분 담아 둔다. 서버(슬롯)마다 따로 세므로 두 서버의 결과가 최대 10분 다를 수 있다. 하나도 없는 결과는 담지 않아, 첫 선택이 생기면
 * 다음 조회에 바로 보인다.
 */
@Service
public class PopularVideoService {

  public static final String RANKING_BASIS = "DISTINCT_MEMBER_SELECTIONS";
  public static final String AGGREGATION_SCOPE = "LAST_30_DAYS";

  static final Duration WINDOW = Duration.ofDays(30);
  static final Duration REFRESH_INTERVAL = Duration.ofMinutes(10);
  static final int SIZE = 4;

  private final VideoSelectionRecordRepository selections;
  private final Clock clock;
  private volatile PopularVideoResponse cached;

  public PopularVideoService(VideoSelectionRecordRepository selections, Clock clock) {
    this.selections = selections;
    this.clock = clock;
  }

  /**
   * 인기 영상 1~4개. 담아 둔 결과가 다시 셀 시각을 지났으면 새로 센다.
   *
   * @throws com.mairor.backend.common.error.BusinessException 503 {@code VIDEO_POPULAR_UNAVAILABLE}
   *     — 기간 안 선택 기록이 하나도 없으면
   */
  public PopularVideoResponse popular() {
    Instant now = clock.instant();
    PopularVideoResponse current = cached;
    if (current == null || !now.isBefore(current.nextRefreshAt())) {
      current = count(now);
      // 빈 결과까지 담아 두면 첫 선택이 생겨도 다시 셀 때까지 503 이 이어진다
      cached = current.items().isEmpty() ? null : current;
    }
    if (current.items().isEmpty()) {
      throw VideoErrors.popularUnavailable();
    }
    return current;
  }

  /** 담아 둔 결과를 버려 다음 조회가 바로 다시 세게 한다. 시연 선택 기록을 넣은 뒤나 테스트에서 쓴다. */
  public void expire() {
    cached = null;
  }

  private PopularVideoResponse count(Instant now) {
    List<PopularVideoRow> rows =
        selections.findPopular(now.minus(WINDOW), ReviewStatus.APPROVED, Limit.of(SIZE));
    List<PopularVideoItem> items = new ArrayList<>(rows.size());
    for (PopularVideoRow row : rows) {
      items.add(
          new PopularVideoItem(
              items.size() + 1,
              row.videoId(),
              row.youtubeVideoId(),
              row.title(),
              row.channelTitle(),
              row.durationSeconds(),
              row.thumbnailUrl(),
              null,
              row.publishedAt(),
              row.guideId(),
              row.guideId() != null));
    }
    return new PopularVideoResponse(
        List.copyOf(items), RANKING_BASIS, AGGREGATION_SCOPE, now, now.plus(REFRESH_INTERVAL));
  }
}
