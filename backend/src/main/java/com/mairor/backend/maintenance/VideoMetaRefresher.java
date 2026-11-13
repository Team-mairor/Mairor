package com.mairor.backend.maintenance;

import com.mairor.backend.common.external.youtube.YouTubeClient;
import com.mairor.backend.common.external.youtube.YouTubeException;
import com.mairor.backend.common.external.youtube.YouTubeVideo;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.service.GuideReviewService;
import com.mairor.backend.maintenance.VideoMetaStore.StaleVideo;
import com.mairor.backend.videos.support.ChapterParser;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

/**
 * 영상 메타 갱신(S15P31A306-407). YouTube Data API 값은 30일 안에 다시 받아야 하므로(ADR-002) 메타를 받은 지 {@code
 * meta-refresh-after} (기본 25일) 지난 영상을 {@code videos.list}(50개씩, 1 unit)로 다시 받는다.
 *
 * <p>YouTube 에 없는 영상(삭제 · 비공개)은 공개 가이드를 내린다(인기 Top 4 · 재사용에서 빠진다). 영상 행은 리포트 기록이 참조해 지우지 않는다. 분석 요청
 * · 선택은 원래 YouTube 를 매번 다시 확인해서 막힌다. CC 라이선스가 바뀐 영상은 내리지 않는다(이미 받은 CC 는 철회되지 않음).
 */
@Service
public class VideoMetaRefresher {

  /** 한 번 갱신한 결과. */
  public record Result(
      int refreshed, int missing, int takenDown, int failed, boolean stoppedByYouTube) {}

  private static final Logger log = LoggerFactory.getLogger(VideoMetaRefresher.class);

  private final VideoMetaStore store;
  private final YouTubeClient youTube;
  private final GuideRepository guides;
  private final GuideReviewService reviews;
  private final ObjectMapper objectMapper;
  private final MaintenanceProperties properties;
  private final Clock clock;

  VideoMetaRefresher(
      VideoMetaStore store,
      YouTubeClient youTube,
      GuideRepository guides,
      GuideReviewService reviews,
      ObjectMapper objectMapper,
      MaintenanceProperties properties,
      Clock clock) {
    this.store = store;
    this.youTube = youTube;
    this.guides = guides;
    this.reviews = reviews;
    this.objectMapper = objectMapper;
    this.properties = properties;
    this.clock = clock;
  }

  public Result run() {
    Instant now = clock.instant();
    List<StaleVideo> stale =
        store.staleBefore(now.minus(properties.metaRefreshAfter()), properties.metaRefreshBatch());
    int refreshed = 0;
    int missing = 0;
    int takenDown = 0;
    int failed = 0;
    boolean stopped = false;
    for (int from = 0; from < stale.size(); from += YouTubeClient.MAX_IDS_PER_CALL) {
      List<StaleVideo> chunk =
          stale.subList(from, Math.min(stale.size(), from + YouTubeClient.MAX_IDS_PER_CALL));
      Map<String, YouTubeVideo> found;
      try {
        found =
            youTube.videos(chunk.stream().map(StaleVideo::youtubeVideoId).toList()).stream()
                .collect(
                    Collectors.toMap(
                        YouTubeVideo::youtubeVideoId, Function.identity(), (a, b) -> a));
      } catch (YouTubeException e) {
        // 할당량 · 장애. 남은 영상은 다음 실행에 다시 본다
        log.warn("영상 메타 갱신 중 YouTube 를 쓰지 못해 멈춤 남은 영상={}", stale.size() - from, e);
        stopped = true;
        break;
      }
      for (StaleVideo video : chunk) {
        YouTubeVideo meta = found.get(video.youtubeVideoId());
        try {
          if (meta != null) {
            store.update(
                video.id(),
                meta,
                objectMapper.writeValueAsString(ChapterParser.parse(meta.description())),
                now);
            refreshed++;
            continue;
          }
          // 가이드를 내린 뒤에 확인 시각을 남긴다. 내리다 실패하면 다음 실행에 다시 본다
          if (takeDown(video)) {
            takenDown++;
          }
          store.markChecked(video.id(), now);
          missing++;
        } catch (RuntimeException e) {
          failed++;
          log.warn("영상 메타를 갱신하지 못함 youtubeVideoId={}", video.youtubeVideoId(), e);
        }
      }
    }
    log.atInfo()
        .setMessage("영상 메타 갱신 refreshed={} missing={} takenDown={} failed={}")
        .addArgument(refreshed)
        .addArgument(missing)
        .addArgument(takenDown)
        .addArgument(failed)
        .addKeyValue("refreshed_videos", refreshed)
        .addKeyValue("missing_videos", missing)
        .log();
    return new Result(refreshed, missing, takenDown, failed, stopped);
  }

  private boolean takeDown(StaleVideo video) {
    return guides
        .findByVideoIdAndReviewStatus(video.id(), ReviewStatus.APPROVED)
        .map(
            guide -> {
              reviews.review(guide.getId(), GuideReviewService.Decision.REJECTED);
              log.warn(
                  "YouTube 에서 사라진 영상의 공개 가이드를 내림 youtubeVideoId={} guideId={}",
                  video.youtubeVideoId(),
                  guide.getId());
              return true;
            })
        .orElse(false);
  }
}
