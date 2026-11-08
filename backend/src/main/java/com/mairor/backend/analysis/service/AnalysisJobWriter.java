package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisJobRequestRecord;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.repository.AnalysisJobRequestRecordRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.EnumSet;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 작업 접수의 트랜잭션 한 번. 동시 요청이 유일 제약({@code uk_videos_youtube_video_id}·{@code
 * uk_analysis_jobs_video_active})에 걸리면 이 트랜잭션은 롤백되고, {@link AnalysisJobService}가 새 트랜잭션으로 다시 시도한다.
 */
@Component
class AnalysisJobWriter {

  static final EnumSet<AnalysisStatus> ACTIVE =
      EnumSet.of(AnalysisStatus.PENDING, AnalysisStatus.RUNNING);

  /** 같은 회원의 신규 접수를 줄 세운다(트랜잭션이 끝나면 풀림). 키는 회원 ID 의 해시다. */
  private static final String LOCK_MEMBER = "select pg_advisory_xact_lock(hashtextextended(?, 0))";

  private final VideoRepository videos;
  private final AnalysisJobRepository jobs;
  private final AnalysisJobRequestRecordRepository requests;
  private final AnalysisJobAccess access;
  private final JdbcTemplate jdbc;
  private final Clock clock;

  AnalysisJobWriter(
      VideoRepository videos,
      AnalysisJobRepository jobs,
      AnalysisJobRequestRecordRepository requests,
      AnalysisJobAccess access,
      JdbcTemplate jdbc,
      Clock clock) {
    this.videos = videos;
    this.jobs = jobs;
    this.requests = requests;
    this.access = access;
    this.jdbc = jdbc;
    this.clock = clock;
  }

  /** 회원 분석 요청의 접수 결과. {@code NEW_JOB} 또는 {@code JOINED_JOB}. */
  record MemberRegistration(UUID jobId, ReceiptType receiptType) {}

  /**
   * 회원 분석 요청(API-VIDEO-002)의 합류 · 신규 한 트랜잭션. 같은 회원의 신규 접수는 줄을 서므로 한도를 동시 요청으로 넘지 않는다. 같은 영상 동시 신규는
   * {@code uk_analysis_jobs_video_active}에 걸려 롤백되고, {@link AnalysisRequestService}가 새 트랜잭션으로 다시
   * 시도하면 합류가 된다.
   *
   * <ol>
   *   <li>진행 중 작업이 있으면 합류: 요청 기록을 남기고(이미 볼 수 있으면 그대로) 돌려준다. 한도를 세지 않는다
   *   <li>오늘(설정 시간대 0시부터) 이 회원의 신규 수가 한도 이상이면 429
   *   <li>영상 파일 키가 없으면 운영자 업로드와 같은 자리({@code videos/<youtubeVideoId>/source.mp4})로 정하고 새 작업 · 요청
   *       기록을 만든다
   * </ol>
   *
   * @throws BusinessException 404 {@code NOT_FOUND} — 영상이 없음
   * @throws AnalysisDailyLimitException 한도 초과
   */
  @Transactional
  MemberRegistration registerForMember(
      UUID videoId, UUID userId, int dailyLimit, Instant dayStart, Instant resetAt) {
    jdbc.query(LOCK_MEMBER, (ResultSetExtractor<Void>) rs -> null, userId.toString());
    Video video =
        videos.findById(videoId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    Instant now = clock.instant();

    Optional<AnalysisJob> active = jobs.findFirstByVideoIdAndStatusIn(video.getId(), ACTIVE);
    if (active.isPresent()) {
      AnalysisJob job = active.get();
      if (!access.canView(userId, job)) {
        requests.saveAndFlush(
            new AnalysisJobRequestRecord(job.getId(), userId, ReceiptType.JOINED_JOB, now));
      }
      return new MemberRegistration(job.getId(), ReceiptType.JOINED_JOB);
    }

    long used =
        requests.countByUserIdAndReceiptTypeAndCreatedAtGreaterThanEqual(
            userId, ReceiptType.NEW_JOB, dayStart);
    if (used >= dailyLimit) {
      throw new AnalysisDailyLimitException(resetAt, now);
    }

    if (video.getSourceObjectKey() == null) {
      video.useSourceObject(defaultSourceKey(video.getYoutubeVideoId()));
    }
    AnalysisJob job = jobs.saveAndFlush(new AnalysisJob(video, userId));
    requests.saveAndFlush(
        new AnalysisJobRequestRecord(job.getId(), userId, ReceiptType.NEW_JOB, now));
    return new MemberRegistration(job.getId(), ReceiptType.NEW_JOB);
  }

  /** 운영자가 영상 파일을 올리는 자리. 노트북 연결(-358) 전에는 이 자리에 파일이 없으면 작업이 SOURCE_NOT_FOUND 로 끝난다. */
  static String defaultSourceKey(String youtubeVideoId) {
    return "videos/" + youtubeVideoId + "/source.mp4";
  }

  /**
   * 영상이 없으면 만들고, 진행 중 작업이 있으면 그 작업을 돌려주고(JOINED_JOB), 없으면 영상 파일 키를 정해 새 작업을 만든다(NEW_JOB). 이미 있는 영상의
   * 메타는 바꾸지 않는다.
   */
  @Transactional
  AnalysisJobReceipt register(AnalysisJobRequest request) {
    Video video =
        videos
            .findByYoutubeVideoId(request.youtubeVideoId())
            .orElseGet(() -> videos.saveAndFlush(newVideo(request)));

    Optional<AnalysisJob> active = jobs.findFirstByVideoIdAndStatusIn(video.getId(), ACTIVE);
    if (active.isPresent()) {
      return AnalysisJobReceipt.of(active.get(), ReceiptType.JOINED_JOB);
    }
    video.useSourceObject(request.sourceObjectKey());
    AnalysisJob job = jobs.saveAndFlush(new AnalysisJob(video, null));
    return AnalysisJobReceipt.of(job, ReceiptType.NEW_JOB);
  }

  private Video newVideo(AnalysisJobRequest request) {
    return new Video(
        request.youtubeVideoId(),
        request.title(),
        request.channelTitle(),
        request.durationSeconds(),
        "https://i.ytimg.com/vi/" + request.youtubeVideoId() + "/hqdefault.jpg",
        null,
        "[]",
        clock.instant());
  }
}
