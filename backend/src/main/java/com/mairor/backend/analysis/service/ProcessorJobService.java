package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.log.AnalysisLogContext;
import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.storage.ObjectStorage;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 영상 전처리 노트북(형준 {@code video-processor})과 주고받는 작업 처리(S15P31A306-357, 계약 {@code
 * docs/references/processor-api.md}).
 *
 * <ul>
 *   <li>claim: 가장 오래 기다린 작업에 임대를 걸어 내준다. 임대가 지난 작업도 다시 내주되, 정해진 횟수만큼 가져간 작업이면 재시도 가능 실패({@code
 *       PROCESSOR_TIMEOUT})로 끝내고 다음 작업을 본다
 *   <li>complete: AI 요청 JSON 의 저장소 키를 받아 둔다. 그 뒤 AI 요청은 S15P31A306-358
 *   <li>fail: 노트북 실패 코드를 BE 실패 코드로 바꿔 끝낸다
 *   <li>progress: 단계를 앞으로 옮기고 임대를 늘린다
 * </ul>
 *
 * 상태가 바뀌면 같은 트랜잭션에서 {@link AnalysisJobNotifier}로 알린다(분석 상태 SSE).
 */
@Service
public class ProcessorJobService {

  /** 노트북 실패 코드 → BE 실패 코드. 표에 없는 코드는 {@code PROCESSOR_FAILED}이고 재시도 여부는 노트북 값을 따른다. */
  static final Map<String, AnalysisFailureCode> FAILURES =
      Map.of(
          "DOWNLOAD_REJECTED", AnalysisFailureCode.VIDEO_DOWNLOAD_REJECTED,
          "VIDEO_UNAVAILABLE", AnalysisFailureCode.SOURCE_NOT_FOUND,
          "STEP_EXTRACTION_FAILED", AnalysisFailureCode.LLM_UNAVAILABLE,
          "FRAME_EXTRACTION_FAILED", AnalysisFailureCode.FRAME_EXTRACTION_FAILED,
          "UPLOAD_FAILED", AnalysisFailureCode.STORAGE_UNAVAILABLE);

  private static final String CONFLICT_CODE = "PROCESSOR_JOB_CONFLICT";
  private static final Logger log = LoggerFactory.getLogger(ProcessorJobService.class);

  private final AnalysisJobRepository jobs;
  private final AnalysisJobNotifier notifier;
  private final ObjectStorage storage;
  private final ProcessorProperties properties;
  private final Clock clock;

  ProcessorJobService(
      AnalysisJobRepository jobs,
      AnalysisJobNotifier notifier,
      ObjectStorage storage,
      ProcessorProperties properties,
      Clock clock) {
    this.jobs = jobs;
    this.notifier = notifier;
    this.storage = storage;
    this.properties = properties;
    this.clock = clock;
  }

  /** 노트북에 내준 작업. */
  public record Claim(
      UUID jobId, String youtubeVideoId, String youtubeUrl, String s3Prefix, long leaseSeconds) {}

  /**
   * 노트북에 작업 하나를 내준다.
   *
   * @return 할 일이 없거나 연결 모드가 꺼져 있으면 빈 값
   */
  @Transactional
  public Optional<Claim> claim() {
    if (!properties.enabled()) {
      return Optional.empty();
    }
    Instant now = clock.instant();
    while (true) {
      Optional<AnalysisJob> next = jobs.lockNextForProcessor(now);
      if (next.isEmpty()) {
        return Optional.empty();
      }
      AnalysisJob job = next.get();
      if (job.isProcessorLeaseExpired(now) && job.getProcessorClaims() >= properties.maxClaims()) {
        job.fail(
            AnalysisFailureCode.PROCESSOR_TIMEOUT,
            "노트북 임대가 " + job.getProcessorClaims() + "번 모두 끝났습니다(노트북 꺼짐 또는 멈춤).",
            now);
        jobs.flush();
        notifier.changed(job.getId());
        try (var ignored = AnalysisLogContext.of(job)) {
          log.warn(
              "노트북 임대 만료가 반복돼 실패 처리 jobId={} claims={}", job.getId(), job.getProcessorClaims());
        }
        continue;
      }
      boolean reclaim = job.getStatus() == AnalysisStatus.RUNNING;
      job.claimByProcessor(now, properties.lease());
      notifier.changed(job.getId());
      String youtubeVideoId = job.getVideo().getYoutubeVideoId();
      try (var ignored = AnalysisLogContext.of(job)) {
        log.info(
            "노트북에 작업을 내줌 jobId={} youtubeVideoId={} claims={} reclaim={}",
            job.getId(),
            youtubeVideoId,
            job.getProcessorClaims(),
            reclaim);
      }
      return Optional.of(
          new Claim(
              job.getId(),
              youtubeVideoId,
              "https://www.youtube.com/watch?v=" + youtubeVideoId,
              s3Prefix(job),
              properties.lease().toSeconds()));
    }
  }

  /**
   * 노트북이 끝났다고 알렸다. 같은 키로 다시 알리면 아무것도 바꾸지 않는다.
   *
   * @throws BusinessException 404 없는 작업, 400 키가 이 작업 경로 밖이거나 저장소에 없음, 409 노트북이 처리 중인 작업이 아님 · 다른 키로
   *     이미 끝남
   */
  @Transactional
  public void complete(UUID jobId, String guideJobRequestKey) {
    AnalysisJob job = load(jobId);
    String prefix = s3Prefix(job) + "/";
    if (guideJobRequestKey == null
        || !guideJobRequestKey.startsWith(prefix)
        || !guideJobRequestKey.endsWith(".json")
        || guideJobRequestKey.contains("..")
        || guideJobRequestKey.length() > AnalysisJob.PROCESSOR_REQUEST_KEY_MAX_LENGTH) {
      throw invalid("guideJobRequestKey", prefix + " 아래의 .json 키여야 합니다.");
    }
    if (guideJobRequestKey.equals(job.getProcessorRequestKey())) {
      log.info("같은 완료 알림을 다시 받음 jobId={}", jobId);
      return;
    }
    if (job.getProcessorRequestKey() != null || !job.isWithProcessor()) {
      throw conflict(job, "완료");
    }
    if (!storage.exists(guideJobRequestKey)) {
      throw invalid("guideJobRequestKey", "저장소에 파일이 없습니다: " + guideJobRequestKey);
    }
    job.completeByProcessor(guideJobRequestKey);
    notifier.changed(jobId);
    log.info("노트북 처리 완료 jobId={} key={}", jobId, guideJobRequestKey);
  }

  /**
   * 노트북이 실패했다고 알렸다. 이미 실패로 끝난 작업이면 아무것도 바꾸지 않는다.
   *
   * @throws BusinessException 404 없는 작업, 400 코드 없음, 409 노트북이 처리 중인 작업이 아님
   */
  @Transactional
  public void fail(UUID jobId, String code, Boolean retryable, String message) {
    if (code == null || code.isBlank()) {
      throw invalid("code", "실패 코드가 없습니다.");
    }
    AnalysisJob job = load(jobId);
    if (job.getStatus() == AnalysisStatus.FAILED) {
      log.info("이미 실패한 작업의 실패 알림 jobId={} code={}", jobId, code);
      return;
    }
    if (!job.isWithProcessor()) {
      throw conflict(job, "실패");
    }
    String text = "[" + code + "] " + (message == null || message.isBlank() ? "" : message);
    AnalysisFailureCode mapped = FAILURES.get(code);
    Instant now = clock.instant();
    if (mapped != null) {
      job.fail(mapped, text.strip(), now);
    } else {
      job.fail(
          AnalysisFailureCode.PROCESSOR_FAILED, text.strip(), retryable == null || retryable, now);
    }
    notifier.changed(jobId);
    log.warn(
        "노트북 처리 실패 jobId={} code={} failureCode={} retryable={} message={}",
        jobId,
        code,
        job.getFailureCode(),
        job.isRetryable(),
        message);
  }

  /**
   * 노트북 진행 알림. 단계를 앞으로만 옮기고 임대를 늘린다.
   *
   * @throws BusinessException 404 없는 작업, 400 노트북 단계가 아님, 409 노트북이 처리 중인 작업이 아님
   */
  @Transactional
  public void progress(UUID jobId, String stage, Integer percent) {
    ProgressStage parsed = parseStage(stage);
    AnalysisJob job = load(jobId);
    if (!job.isWithProcessor()) {
      throw conflict(job, "진행");
    }
    boolean moved = job.progressByProcessor(parsed, clock.instant(), properties.lease());
    if (moved) {
      notifier.changed(jobId);
    }
    // 같은 단계 안의 진행률도 남긴다(단계 안 숫자는 아직 앱에 보내지 않는다)
    log.info(
        "노트북 진행 jobId={} stage={} percent={} now={}",
        jobId,
        parsed,
        percent,
        job.getProgressStage());
  }

  /**
   * 노트북을 너무 오래 기다린 작업을 {@code PROCESSOR_TIMEOUT}(재시도 가능)으로 끝낸다: 아무도 가져가지 않은 대기 작업, 임대가 지나고 아무도 다시
   * 가져가지 않은 작업. 연결 모드가 꺼져 있으면 하지 않는다(worker 가 대기 작업을 처리한다). S15P31A306-358.
   *
   * <p>노트북이 그동안 어떤 작업이든 만졌으면(가져감 · 진행 알림 · 완료) 아무것도 끝내지 않는다. 노트북은 한 번에 하나씩 처리해서 앞 작업이 길면 줄 선 작업이 만든
   * 지 기다림 시간을 넘길 수 있는데, 이것은 노트북이 꺼진 것이 아니다(S15P31A306-408).
   *
   * @return 끝낸 작업 수
   */
  @Transactional
  public int expireWaiting() {
    if (!properties.enabled()) {
      return 0;
    }
    Instant now = clock.instant();
    Instant before = now.minus(properties.waitTimeout());
    if (jobs.existsTouchedByProcessorSince(before)) {
      return 0;
    }
    int expired = 0;
    for (UUID id : jobs.findIdsWaitingForProcessorSince(before)) {
      AnalysisJob job = jobs.lockById(id).orElse(null);
      if (job == null) {
        continue;
      }
      if (job.getStatus() == AnalysisStatus.PENDING && job.getUpdatedAt().isBefore(before)) {
        job.failBeforeStart(
            AnalysisFailureCode.PROCESSOR_TIMEOUT,
            "영상 전처리 노트북이 " + properties.waitTimeout().toMinutes() + "분 동안 작업을 가져가지 않았습니다.",
            now);
      } else if (job.isWithProcessor() && job.getProcessorLeaseUntil().isBefore(before)) {
        job.fail(
            AnalysisFailureCode.PROCESSOR_TIMEOUT, "영상 전처리 노트북이 처리 중에 멈췄고 다시 가져가지 않았습니다.", now);
      } else {
        continue;
      }
      notifier.changed(id);
      expired++;
      try (var ignored = AnalysisLogContext.of(job)) {
        log.warn("노트북을 기다리다 시간 초과 jobId={}", id);
      }
    }
    return expired;
  }

  /**
   * 노트북 응답 없음(S15P31A306-406).
   *
   * @param waiting 노트북을 기다리는 작업 수
   * @param oldestWait 그중 가장 오래 기다린 시간(마지막으로 바뀐 때부터)
   * @param checkedAt 본 시각
   */
  public record Stall(int waiting, Duration oldestWait, Instant checkedAt) {}

  /**
   * 노트북이 {@code warn-after} 동안 아무 작업도 만지지 않았는데 그보다 오래 기다린 작업이 있으면 돌려준다. {@link #expireWaiting()}과
   * 같은 기준을 더 짧게 봐서, 시간 초과로 실패하기 전에 알 수 있게 한다. 연결 모드가 꺼져 있으면 빈 값.
   */
  @Transactional(readOnly = true)
  public Optional<Stall> stalled() {
    if (!properties.enabled()) {
      return Optional.empty();
    }
    Instant now = clock.instant();
    Instant before = now.minus(properties.warnAfter());
    if (jobs.existsTouchedByProcessorSince(before)) {
      return Optional.empty();
    }
    List<UUID> ids = jobs.findIdsWaitingForProcessorSince(before);
    if (ids.isEmpty()) {
      return Optional.empty();
    }
    Instant oldest =
        jobs.findAllById(ids).stream()
            .map(AnalysisJob::getUpdatedAt)
            .min(Comparator.naturalOrder())
            .orElse(now);
    return Optional.of(new Stall(ids.size(), Duration.between(oldest, now), now));
  }

  /** 노트북이 이 작업의 파일을 두는 자리. 같은 영상을 다시 분석해도 이전 결과를 덮지 않게 작업마다 나눈다. */
  static String s3Prefix(AnalysisJob job) {
    return "videos/" + job.getVideo().getYoutubeVideoId() + "/jobs/" + job.getId();
  }

  private AnalysisJob load(UUID jobId) {
    return jobs.lockById(jobId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
  }

  private static ProgressStage parseStage(String stage) {
    if (stage != null) {
      switch (stage) {
        case "LOADING_VIDEO":
          return ProgressStage.LOADING_VIDEO;
        case "EXTRACTING_STEPS":
          return ProgressStage.EXTRACTING_STEPS;
        case "SEGMENTING":
          return ProgressStage.SEGMENTING;
        default:
          break;
      }
    }
    throw invalid("stage", "LOADING_VIDEO · EXTRACTING_STEPS · SEGMENTING 중 하나여야 합니다.");
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

  private static BusinessException conflict(AnalysisJob job, String action) {
    return new BusinessException(
        HttpStatus.CONFLICT,
        CONFLICT_CODE,
        "노트북이 처리 중인 작업이 아니라 " + action + " 알림을 받을 수 없습니다(" + job.getStatus() + ").");
  }
}
