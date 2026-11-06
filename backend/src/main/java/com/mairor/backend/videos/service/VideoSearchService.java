package com.mairor.backend.videos.service;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.external.youtube.YouTubeClient;
import com.mairor.backend.common.external.youtube.YouTubeException;
import com.mairor.backend.common.external.youtube.YouTubeProperties;
import com.mairor.backend.common.external.youtube.YouTubeSearchResult;
import com.mairor.backend.common.external.youtube.YouTubeVideo;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.videos.dto.VideoSearchItem;
import com.mairor.backend.videos.dto.VideoSearchPage;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import com.mairor.backend.videos.support.VideoErrors;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 메이크업 영상 검색(API-VIDEO-004). YouTube 에서 CC BY 영상만 찾고, 분석할 수 없는 영상(비공개 · 연령 제한 · 라이브)을 뺀 뒤 우리 가이드
 * 상태를 붙인다.
 *
 * <p>YouTube 결과(가이드 상태 제외)는 같은 검색어 · 페이지 · 크기로 잠시 다시 쓴다. 가이드 상태는 매번 DB 에서 붙여 승인 직후에도 맞다.
 */
@Service
public class VideoSearchService {

  public static final int DEFAULT_SIZE = 20;
  public static final int MAX_SIZE = 50;
  public static final int MAX_QUERY_LENGTH = 100;

  private final YouTubeClient youTube;
  private final VideoRepository videos;
  private final GuideRepository guides;
  private final Cache<SearchKey, CachedPage> cache;

  public VideoSearchService(
      YouTubeClient youTube,
      VideoRepository videos,
      GuideRepository guides,
      YouTubeProperties properties) {
    this.youTube = youTube;
    this.videos = videos;
    this.guides = guides;
    this.cache =
        Caffeine.newBuilder()
            .expireAfterWrite(properties.searchCacheTtl())
            .maximumSize(properties.searchCacheSize())
            .build();
  }

  @Transactional(readOnly = true)
  public VideoSearchPage search(String q, String pageToken, Integer size) {
    String query = q == null ? "" : q.strip();
    if (query.isEmpty() || query.length() > MAX_QUERY_LENGTH) {
      throw invalid("q", "검색어는 공백을 뺀 1~" + MAX_QUERY_LENGTH + "자여야 합니다.");
    }
    int pageSize = size == null ? DEFAULT_SIZE : size;
    if (pageSize < 1 || pageSize > MAX_SIZE) {
      throw invalid("size", "size 는 1~" + MAX_SIZE + "이어야 합니다.");
    }
    String token = pageToken == null || pageToken.isBlank() ? null : pageToken;

    SearchKey key = new SearchKey(query, token, pageSize);
    CachedPage page = cache.getIfPresent(key);
    if (page == null) {
      page = fetch(query, token, pageSize);
      cache.put(key, page);
    }
    return new VideoSearchPage(withGuides(page.videos()), page.nextPageToken(), pageSize);
  }

  private CachedPage fetch(String query, String pageToken, int size) {
    try {
      YouTubeSearchResult result = youTube.search(query, pageToken, size);
      List<YouTubeVideo> details =
          youTube.videos(result.videoIds()).stream().filter(YouTubeVideo::analyzable).toList();
      return new CachedPage(details, result.nextPageToken());
    } catch (YouTubeException e) {
      throw VideoErrors.forSearch(e);
    }
  }

  private List<VideoSearchItem> withGuides(List<YouTubeVideo> found) {
    if (found.isEmpty()) {
      return List.of();
    }
    Map<String, UUID> videoIdByYoutubeId =
        videos
            .findByYoutubeVideoIdIn(found.stream().map(YouTubeVideo::youtubeVideoId).toList())
            .stream()
            .collect(Collectors.toMap(Video::getYoutubeVideoId, Video::getId));
    Map<UUID, UUID> guideIdByVideoId = new HashMap<>();
    if (!videoIdByYoutubeId.isEmpty()) {
      guideIdByVideoId =
          guides
              .findByVideoIdInAndReviewStatus(videoIdByYoutubeId.values(), ReviewStatus.APPROVED)
              .stream()
              .collect(Collectors.toMap(g -> g.getVideo().getId(), Guide::getId, (a, b) -> a));
    }
    Map<UUID, UUID> approved = guideIdByVideoId;
    return found.stream()
        .map(
            v -> {
              UUID videoId = videoIdByYoutubeId.get(v.youtubeVideoId());
              UUID guideId = videoId == null ? null : approved.get(videoId);
              return new VideoSearchItem(
                  v.youtubeVideoId(),
                  v.title(),
                  v.channelTitle(),
                  v.durationSeconds(),
                  v.thumbnailUrl(),
                  v.viewCount(),
                  v.publishedAt(),
                  guideId,
                  guideId != null);
            })
        .toList();
  }

  private static BusinessException invalid(String field, String reason) {
    ErrorCode code = ErrorCode.VALIDATION_FAILED;
    return new BusinessException(
        code.status(),
        code.name(),
        code.message(),
        List.of(new ErrorResponse.FieldError(field, reason)),
        null);
  }

  private record SearchKey(String query, String pageToken, int size) {}

  private record CachedPage(List<YouTubeVideo> videos, String nextPageToken) {}
}
