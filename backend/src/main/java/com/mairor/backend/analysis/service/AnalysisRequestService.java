package com.mairor.backend.analysis.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.external.youtube.YouTubeClient;
import com.mairor.backend.common.external.youtube.YouTubeException;
import com.mairor.backend.common.external.youtube.YouTubeVideo;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import com.mairor.backend.videos.support.VideoErrors;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

/**
 * 회원 분석 요청(API-VIDEO-002). 명세 순서대로 재사용 → 합류 → 신규를 가린다.
 *
 * <ol>
 *   <li>내부 영상이 없으면 404
 *   <li>YouTube 에서 공개 · CC BY 등을 다시 확인한다(라이선스는 저장하지 않고 요청 때마다). 어긋나면 409, YouTube 실패는 503
 *   <li>승인 가이드가 있으면 재사용(작업 없음, 한도 차감 없음)
 *   <li>진행 중 작업이 있으면 합류(한도 차감 없음), 없으면 일일 한도를 보고 새 작업 — {@link AnalysisJobWriter}의 한 트랜잭션
 * </ol>
 *
 * 새 작업은 지금 worker 흐름에 들어간다. 노트북 수집 에이전트 연결은 S15P31A306-358 이다.
 */
@Service
public class AnalysisRequestService {

  private static final Logger log = LoggerFactory.getLogger(AnalysisRequestService.class);

  private final VideoRepository videos;
  private final GuideRepository guides;
  private final YouTubeClient youTube;
  private final AnalysisJobWriter writer;
  private final AnalysisJobStatusService statuses;
  private final AnalysisRequestProperties properties;
  private final Clock clock;

  AnalysisRequestService(
      VideoRepository videos,
      GuideRepository guides,
      YouTubeClient youTube,
      AnalysisJobWriter writer,
      AnalysisJobStatusService statuses,
      AnalysisRequestProperties properties,
      Clock clock) {
    this.videos = videos;
    this.guides = guides;
    this.youTube = youTube;
    this.writer = writer;
    this.statuses = statuses;
    this.properties = properties;
    this.clock = clock;
  }

  /**
   * @param rawVideoId 요청 본문의 내부 영상 ID(문자열). UUID 가 아니면 400
   */
  public AnalysisRequestReceipt request(UUID userId, String rawVideoId) {
    UUID videoId = parseVideoId(rawVideoId);
    Video video =
        videos.findById(videoId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    VideoErrors.checkAnalyzable(fetch(video.getYoutubeVideoId()));

    Optional<Guide> approved = guides.findByVideoIdAndReviewStatus(videoId, ReviewStatus.APPROVED);
    if (approved.isPresent()) {
      log.info("분석 요청 재사용 videoId={} guideId={}", videoId, approved.get().getId());
      return AnalysisRequestReceipt.reused(videoId, approved.get().getId());
    }

    ZonedDateTime today =
        LocalDate.now(clock.withZone(properties.zone())).atStartOfDay(properties.zone());
    Instant dayStart = today.toInstant();
    Instant resetAt = today.plusDays(1).toInstant();
    int limit = properties.dailyLimitPerUser();

    AnalysisJobWriter.MemberRegistration registration;
    try {
      registration = writer.registerForMember(videoId, userId, limit, dayStart, resetAt);
    } catch (DataIntegrityViolationException conflict) {
      // 다른 회원이 같은 영상의 새 작업을 먼저 만들었다. 다시 하면 그 작업에 합류한다
      log.info("분석 요청이 동시 요청과 겹쳐 다시 시도합니다. videoId={}", videoId);
      registration = writer.registerForMember(videoId, userId, limit, dayStart, resetAt);
    }
    log.info(
        "분석 요청 접수 jobId={} videoId={} receipt={}",
        registration.jobId(),
        videoId,
        registration.receiptType());
    AnalysisJobStatusView status =
        statuses
            .find(userId, registration.jobId())
            .orElseThrow(() -> new IllegalStateException("방금 접수한 작업을 찾지 못했습니다."));
    return AnalysisRequestReceipt.of(registration.receiptType(), status);
  }

  private static UUID parseVideoId(String raw) {
    if (raw != null) {
      try {
        String trimmed = raw.trim();
        if (trimmed.length() == 36) {
          return UUID.fromString(trimmed);
        }
      } catch (IllegalArgumentException ignored) {
        // 아래에서 400
      }
    }
    ErrorCode code = ErrorCode.VALIDATION_FAILED;
    throw new BusinessException(
        code.status(),
        code.name(),
        code.message(),
        List.of(new ErrorResponse.FieldError("videoId", "내부 영상 ID(UUID)가 아닙니다.")),
        null);
  }

  private YouTubeVideo fetch(String youtubeVideoId) {
    List<YouTubeVideo> found;
    try {
      found = youTube.videos(List.of(youtubeVideoId));
    } catch (YouTubeException e) {
      throw VideoErrors.forAnalysisRequest(e);
    }
    if (found.isEmpty()) {
      throw VideoErrors.unsupported("없거나 비공개 · 삭제된 영상입니다.");
    }
    return found.getFirst();
  }
}
