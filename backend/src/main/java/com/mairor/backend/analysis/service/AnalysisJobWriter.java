package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisJobRequestRecord;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
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

  private static final Logger log = LoggerFactory.getLogger(AnalysisJobWriter.class);

  /** 재시도할 수 없는 작업(API-VIDEO-006 409). */
  static final String NOT_RETRYABLE = "ANALYSIS_NOT_RETRYABLE";

  static final EnumSet<AnalysisStatus> ACTIVE =
      EnumSet.of(AnalysisStatus.PENDING, AnalysisStatus.RUNNING);

  /** 같은 회원의 신규 접수를 줄 세운다(트랜잭션이 끝나면 풀림). 키는 회원 ID 의 해시다. */
  private static final String LOCK_MEMBER = "select pg_advisory_xact_lock(hashtextextended(?, 0))";

  private final VideoRepository videos;
  private final AnalysisJobRepository jobs;
  private final AnalysisJobRequestRecordRepository requests;
  private final AnalysisJobAccess access;
  private final AnalysisJobNotifier notifier;
  private final JdbcTemplate jdbc;
  private final Clock clock;

  AnalysisJobWriter(
      VideoRepository videos,
      AnalysisJobRepository jobs,
      AnalysisJobRequestRecordRepository requests,
      AnalysisJobAccess access,
      AnalysisJobNotifier notifier,
      JdbcTemplate jdbc,
      Clock clock) {
    this.videos = videos;
    this.jobs = jobs;
    this.requests = requests;
    this.access = access;
    this.notifier = notifier;
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

  /**
   * 회원 분석 재시도(API-VIDEO-006)의 한 트랜잭션. 작업 행을 잠가 두 회원이 동시에 눌러도 한 번만 다시 돌린다.
   *
   * <ol>
   *   <li>없거나 내가 요청 · 합류한 작업이 아니면 404
   *   <li>재시도로 다시 도는 중이면(누가 먼저 재시도함, 시도 2번째부터) 그대로 돌려준다
   *   <li>재시도할 수 없으면(처음 도는 중 · 완료 · 재시도 불가 실패 · 시도 횟수 상한) 409
   *   <li>같은 영상의 다른 진행 중 작업이 있으면(실패 뒤 누가 새로 요청함) 그 작업에 합류한다. 같은 영상의 진행 중 작업은 하나뿐이다
   *   <li>아니면 {@link AnalysisJob#retry()}. 하루 분석 한도는 세지 않는다. TODO(확인 필요 4): 재시도 차감 정책이 정해지면 바꾼다
   * </ol>
   *
   * 새 분석 요청과 동시에 겹치면 {@code uk_analysis_jobs_video_active}에 걸려 롤백되고, 부르는 쪽이 새 트랜잭션으로 다시 하면 합류가 된다.
   *
   * @return 이어서 볼 작업 ID. 다른 진행 중 작업에 합류했으면 그 작업
   */
  @Transactional
  UUID retryForMember(UUID jobId, UUID userId, AnalysisRequestProperties policy) {
    AnalysisJob job =
        jobs.lockById(jobId)
            .filter(found -> access.canView(userId, found))
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    boolean retriedAndRunning = ACTIVE.contains(job.getStatus()) && job.getAttempt() > 1;
    if (retriedAndRunning) {
      return job.getId();
    }
    if (!policy.canRetry(job)) {
      log.info(
          "재시도할 수 없는 분석 작업 jobId={} status={} failureCode={} attempt={}",
          job.getId(),
          job.getStatus(),
          job.getFailureCode(),
          job.getAttempt());
      throw new BusinessException(
          HttpStatus.CONFLICT, NOT_RETRYABLE, "이 분석은 다시 시도할 수 없습니다. 다른 영상을 골라 주세요.");
    }
    Optional<AnalysisJob> other =
        jobs.findFirstByVideoIdAndStatusIn(job.getVideo().getId(), ACTIVE);
    if (other.isPresent()) {
      AnalysisJob active = other.get();
      if (!access.canView(userId, active)) {
        requests.saveAndFlush(
            new AnalysisJobRequestRecord(
                active.getId(), userId, ReceiptType.JOINED_JOB, clock.instant()));
      }
      log.info("분석 재시도 대신 진행 중 작업에 합류 jobId={} activeJobId={}", job.getId(), active.getId());
      return active.getId();
    }
    String failureCode = job.getFailureCode();
    job.retry();
    jobs.saveAndFlush(job);
    notifier.changed(job.getId());
    log.info(
        "분석 재시도 jobId={} failureCode={} attempt={} stage={}",
        job.getId(),
        failureCode,
        job.getAttempt(),
        job.getProgressStage());
    return job.getId();
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
