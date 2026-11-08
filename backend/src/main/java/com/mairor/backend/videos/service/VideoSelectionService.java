package com.mairor.backend.videos.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AnalysisJobAccess;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.external.youtube.YouTubeClient;
import com.mairor.backend.common.external.youtube.YouTubeException;
import com.mairor.backend.common.external.youtube.YouTubeVideo;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.videos.dto.VideoChapter;
import com.mairor.backend.videos.dto.VideoSelection;
import com.mairor.backend.videos.dto.VideoSelectionRequest;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import com.mairor.backend.videos.support.ChapterParser;
import com.mairor.backend.videos.support.VideoErrors;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/**
 * 영상 선택(API-VIDEO-001). YouTube 에서 메타 · 공개 여부 · 라이선스를 다시 확인하고, 분석할 수 있는 영상이면 {@code videos}에 저장 ·
 * 갱신한 뒤 챕터 · 가이드 상태 · 내 진행 중 작업을 돌려준다. 분석은 만들지 않는다.
 *
 * <p>CC BY 가 아닌 영상도 분석할 수 없는 영상으로 본다(11.04 결정). 라이선스는 저장하지 않고 선택 · 분석 요청 때마다 다시 확인한다.
 */
@Service
public class VideoSelectionService {

  private static final Pattern YOUTUBE_ID = Pattern.compile("^[A-Za-z0-9_-]{11}$");
  private static final List<AnalysisStatus> ACTIVE =
      List.of(AnalysisStatus.PENDING, AnalysisStatus.RUNNING);

  /** 같은 영상을 동시에 골라도 행이 하나만 생기게 유일 키로 넣거나 바꾼다. */
  private static final String UPSERT =
      """
      insert into videos (id, youtube_video_id, title, channel_title, duration_seconds, thumbnail_url,
                          published_at, chapters, meta_refreshed_at, created_at, updated_at)
      values (?, ?, ?, ?, ?, ?, ?, cast(? as jsonb), ?, ?, ?)
      on conflict (youtube_video_id) do update set
        title = excluded.title,
        channel_title = excluded.channel_title,
        duration_seconds = excluded.duration_seconds,
        thumbnail_url = excluded.thumbnail_url,
        published_at = excluded.published_at,
        chapters = excluded.chapters,
        meta_refreshed_at = excluded.meta_refreshed_at,
        updated_at = excluded.updated_at
      """;

  private final YouTubeClient youTube;
  private final VideoRepository videos;
  private final GuideRepository guides;
  private final AnalysisJobRepository jobs;
  private final AnalysisJobAccess access;
  private final JdbcTemplate jdbc;
  private final ObjectMapper objectMapper;
  private final Clock clock;

  @Autowired
  public VideoSelectionService(
      YouTubeClient youTube,
      VideoRepository videos,
      GuideRepository guides,
      AnalysisJobRepository jobs,
      AnalysisJobAccess access,
      JdbcTemplate jdbc,
      ObjectMapper objectMapper) {
    this(youTube, videos, guides, jobs, access, jdbc, objectMapper, Clock.systemUTC());
  }

  VideoSelectionService(
      YouTubeClient youTube,
      VideoRepository videos,
      GuideRepository guides,
      AnalysisJobRepository jobs,
      AnalysisJobAccess access,
      JdbcTemplate jdbc,
      ObjectMapper objectMapper,
      Clock clock) {
    this.youTube = youTube;
    this.videos = videos;
    this.guides = guides;
    this.jobs = jobs;
    this.access = access;
    this.jdbc = jdbc;
    this.objectMapper = objectMapper;
    this.clock = clock;
  }

  @Transactional
  public VideoSelection select(UUID userId, VideoSelectionRequest request) {
    String youtubeVideoId = request == null ? null : request.youtubeVideoId();
    if (youtubeVideoId == null || !YOUTUBE_ID.matcher(youtubeVideoId).matches()) {
      ErrorCode code = ErrorCode.VALIDATION_FAILED;
      throw new BusinessException(
          code.status(),
          code.name(),
          code.message(),
          List.of(new ErrorResponse.FieldError("youtubeVideoId", "YouTube 영상 ID(11자)가 아닙니다.")),
          null);
    }

    YouTubeVideo found = fetch(youtubeVideoId);
    VideoErrors.checkAnalyzable(found);
    List<VideoChapter> chapters = ChapterParser.parse(found.description());

    Video video = upsert(found, chapters);
    Optional<Guide> approved =
        guides.findByVideoIdAndReviewStatus(video.getId(), ReviewStatus.APPROVED);
    Optional<AnalysisJob> active = jobs.findFirstByVideoIdAndStatusIn(video.getId(), ACTIVE);
    // 요청했거나 합류한 회원만 진행 중 작업 ID 를 받는다(상태 조회 · SSE 권한과 같은 기준)
    UUID analysisJobId =
        active.filter(j -> access.canView(userId, j)).map(AnalysisJob::getId).orElse(null);
    // 분석이 진행 중이면 이전 판 가이드 상태(예 REJECTED)보다 진행 중(NOT_READY)을 먼저 보인다
    ReviewStatus reviewStatus =
        active.isPresent()
            ? ReviewStatus.NOT_READY
            : guides
                .findFirstByVideoIdOrderByVersionDesc(video.getId())
                .map(Guide::getReviewStatus)
                .orElse(null);

    UUID guideId = approved.map(Guide::getId).orElse(null);
    return new VideoSelection(
        video.getId(),
        found.youtubeVideoId(),
        found.title(),
        found.channelTitle(),
        found.durationSeconds(),
        found.thumbnailUrl(),
        found.viewCount(),
        found.publishedAt(),
        chapters,
        guideId,
        guideId != null,
        analysisJobId,
        reviewStatus);
  }

  private YouTubeVideo fetch(String youtubeVideoId) {
    List<YouTubeVideo> found;
    try {
      found = youTube.videos(List.of(youtubeVideoId));
    } catch (YouTubeException e) {
      throw VideoErrors.forSelection(e);
    }
    if (found.isEmpty()) {
      // videos.list 는 없는 영상 · 지운 영상 · 비공개 영상을 똑같이 빼고 돌려준다. 명세가 비공개 · 삭제를 409 로 두므로 구분 없이 409 다
      throw VideoErrors.unsupported("없거나 비공개 · 삭제된 영상입니다.");
    }
    return found.getFirst();
  }

  private Video upsert(YouTubeVideo found, List<VideoChapter> chapters) {
    Timestamp now = Timestamp.from(Instant.now(clock));
    Instant publishedAt = found.publishedAt();
    jdbc.update(
        UPSERT,
        UUID.randomUUID(),
        found.youtubeVideoId(),
        truncate(found.title(), Video.TITLE_MAX_LENGTH),
        truncate(found.channelTitle(), Video.CHANNEL_TITLE_MAX_LENGTH),
        found.durationSeconds(),
        thumbnailOrNull(found.thumbnailUrl()),
        publishedAt == null ? null : Timestamp.from(publishedAt),
        objectMapper.writeValueAsString(chapters),
        now,
        now,
        now);
    return videos
        .findByYoutubeVideoId(found.youtubeVideoId())
        .orElseThrow(() -> new IllegalStateException("방금 저장한 영상을 찾지 못했습니다."));
  }

  private static String truncate(String value, int max) {
    return value.length() <= max ? value : value.substring(0, max);
  }

  private static String thumbnailOrNull(String url) {
    return url == null || url.length() > Video.THUMBNAIL_URL_MAX_LENGTH ? null : url;
  }
}
