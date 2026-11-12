package com.mairor.backend.analysis.entity;

import com.mairor.backend.videos.entity.Video;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

/**
 * 영상 한 편의 분석 작업. 상태 전이는 S15P31A306-308 에서 이 클래스에 더한다.
 *
 * <p>같은 영상의 진행 중(PENDING·RUNNING) 작업은 하나뿐이다. JPA 로 표현할 수 없는 부분 유일 인덱스({@value
 * #VIDEO_ACTIVE_UNIQUE})라 {@code db/schema/analysis.sql}에만 있다. 동시에 두 요청이 작업을 만들면 나중 것이 이 인덱스에 막힌다.
 *
 * <p>{@code requestedBy}는 분석을 요청한 회원 ID 이고 운영 명령으로 만든 작업은 {@code null}이다. {@code aiJobId}는 AI 서버가
 * 돌려준 가이드 생성 작업 ID 로, 콜백을 이 값으로 찾는다.
 *
 * <p>영상 전처리 노트북(S15P31A306-357)이 작업을 가져가면 임대({@code processorLeaseUntil})가 걸리고, 끝났다고 알리면 AI 요청 JSON
 * 의 저장소 키({@code processorRequestKey})가 남는다. 임대가 지나면 다른 노트북이 다시 가져갈 수 있다.
 */
@Entity
@Table(
    name = "analysis_jobs",
    uniqueConstraints =
        @UniqueConstraint(name = AnalysisJob.AI_JOB_ID_UNIQUE, columnNames = "ai_job_id"))
public class AnalysisJob {

  public static final String VIDEO_FK = "fk_analysis_jobs_video";
  public static final String REQUESTED_BY_FK = "fk_analysis_jobs_requested_by";
  public static final String AI_JOB_ID_UNIQUE = "uk_analysis_jobs_ai_job_id";
  public static final String VIDEO_ACTIVE_UNIQUE = "uk_analysis_jobs_video_active";

  public static final int FAILURE_CODE_MAX_LENGTH = 50;
  public static final int FAILURE_MESSAGE_MAX_LENGTH = 500;
  public static final int AI_JOB_ID_MAX_LENGTH = 64;
  public static final int PROCESSOR_REQUEST_KEY_MAX_LENGTH = 500;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "video_id", nullable = false, foreignKey = @ForeignKey(name = VIDEO_FK))
  private Video video;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private AnalysisStatus status;

  @Enumerated(EnumType.STRING)
  @Column(name = "progress_stage", nullable = false, length = 30)
  private ProgressStage progressStage;

  /** 0~100. 실제로 계산할 수 있을 때만 값이 있다(API 명세 v2). */
  @Column(name = "progress_percent")
  private Integer progressPercent;

  @Column(nullable = false)
  private boolean retryable;

  @Column(name = "failure_code", length = FAILURE_CODE_MAX_LENGTH)
  private String failureCode;

  @Column(name = "failure_message", length = FAILURE_MESSAGE_MAX_LENGTH)
  private String failureMessage;

  @Column(name = "ai_job_id", length = AI_JOB_ID_MAX_LENGTH)
  private String aiJobId;

  /**
   * AI 에 가이드 생성을 맡긴 시각. 콜백 시간 초과의 기준이다. {@code updatedAt}은 진행 숫자를 저장할 때마다 바뀌어 기준으로 쓸 수 없다. 이 칸이 생기기
   * 전에 맡긴 작업은 비어 있다({@link #recordAiProgress} 참고).
   */
  @Column(name = "ai_requested_at")
  private Instant aiRequestedAt;

  /** AI 진행 알림의 숫자 원본(JSON). 진행 알림을 받기 전에는 {@code null}. */
  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "ai_progress")
  private String aiProgress;

  @Column(name = "requested_by")
  private UUID requestedBy;

  /** 노트북 임대가 끝나는 시각. 노트북이 가져가 처리 중일 때만 있다. 지나면 다시 내준다. */
  @Column(name = "processor_lease_until")
  private Instant processorLeaseUntil;

  /** 노트북이 이 작업을 가져간 횟수. 임대가 거듭 만료되면(노트북 꺼짐) 실패로 끝내는 데 쓴다. */
  @Column(name = "processor_claims", nullable = false)
  private int processorClaims;

  /** 노트북이 끝났다고 알린 AI 요청 JSON 의 저장소 키. 이 값이 있으면 BE 가 AI 에 맡길 차례다(S15P31A306-358). */
  @Column(name = "processor_request_key", length = PROCESSOR_REQUEST_KEY_MAX_LENGTH)
  private String processorRequestKey;

  /** 몇 번째 시도인지. 처음 만들 때 1, 재시도마다 1씩 오른다. */
  @Column(nullable = false)
  private int attempt;

  @Column(name = "started_at")
  private Instant startedAt;

  @Column(name = "finished_at")
  private Instant finishedAt;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected AnalysisJob() {}

  /**
   * 대기 중(PENDING · QUEUED) 작업을 만든다.
   *
   * @param requestedBy 요청한 회원 ID. 운영 명령이면 {@code null}
   */
  public AnalysisJob(Video video, UUID requestedBy) {
    this.video = Objects.requireNonNull(video, "video");
    this.requestedBy = requestedBy;
    this.status = AnalysisStatus.PENDING;
    this.progressStage = ProgressStage.QUEUED;
    this.retryable = false;
    this.attempt = 1;
  }

  // --- 상태 전이 (PENDING → RUNNING → COMPLETED | FAILED, 재시작 복구 RUNNING → PENDING) ---

  /** worker 가 작업을 집었다. PENDING 일 때만. */
  public void start(Instant now) {
    requireStatus(AnalysisStatus.PENDING, "시작");
    this.status = AnalysisStatus.RUNNING;
    this.startedAt = Objects.requireNonNull(now, "now");
  }

  /** 다음 진행 단계로 넘어간다. RUNNING 일 때만, 대기(QUEUED)·완료(DONE)로는 넘어가지 않는다. */
  public void advanceTo(ProgressStage stage) {
    requireStatus(AnalysisStatus.RUNNING, "단계 진행");
    if (stage == ProgressStage.QUEUED || stage == ProgressStage.DONE) {
      throw new IllegalArgumentException("진행 단계로 " + stage + " 를 쓸 수 없습니다.");
    }
    this.progressStage = stage;
  }

  /** 모든 단계를 마쳤다. RUNNING 일 때만. */
  public void complete(Instant now) {
    requireStatus(AnalysisStatus.RUNNING, "완료");
    this.status = AnalysisStatus.COMPLETED;
    this.progressStage = ProgressStage.DONE;
    this.progressPercent = 100;
    this.finishedAt = Objects.requireNonNull(now, "now");
  }

  /**
   * 실패로 끝낸다. 진행 단계는 멈춘 단계로 남는다(API 명세 v2: FAILED 면 progressStage = 멈춘 단계). RUNNING 일 때만.
   *
   * @param message 운영자가 볼 원인. 길면 자른다. {@code null}이면 코드의 기본 문구
   */
  public void fail(AnalysisFailureCode code, String message, Instant now) {
    requireStatus(AnalysisStatus.RUNNING, "실패 처리");
    this.status = AnalysisStatus.FAILED;
    this.failureCode = Objects.requireNonNull(code, "code").name();
    this.failureMessage = truncate(message == null ? code.defaultMessage() : message);
    this.retryable = code.retryable();
    this.finishedAt = Objects.requireNonNull(now, "now");
    this.processorLeaseUntil = null;
  }

  /**
   * {@link #fail(AnalysisFailureCode, String, Instant)}와 같지만 재시도 여부를 따로 정한다. 노트북이 보낸 모르는 실패 코드처럼 코드
   * 하나로 판단할 수 없을 때만 쓴다.
   */
  public void fail(AnalysisFailureCode code, String message, boolean retryable, Instant now) {
    fail(code, message, now);
    this.retryable = retryable;
  }

  // --- 영상 전처리 노트북 (S15P31A306-357) ---

  /** 시작하지 못한 채 실패로 끝낸다(노트북이 오래 가져가지 않음, S15P31A306-358). PENDING 일 때만. 진행 단계는 대기(QUEUED)로 남는다. */
  public void failBeforeStart(AnalysisFailureCode code, String message, Instant now) {
    requireStatus(AnalysisStatus.PENDING, "시작 전 실패 처리");
    this.status = AnalysisStatus.RUNNING;
    fail(code, message, now);
  }

  /** 노트북이 가져갈 수 있는가: 대기 중이거나, 노트북이 가져갔는데 임대가 지났다(끝났다는 알림 없이). */
  public boolean isClaimableByProcessor(Instant now) {
    return status == AnalysisStatus.PENDING || isProcessorLeaseExpired(now);
  }

  /** 노트북이 가져가 처리 중인데 임대가 지났다. */
  public boolean isProcessorLeaseExpired(Instant now) {
    return status == AnalysisStatus.RUNNING
        && processorLeaseUntil != null
        && !processorLeaseUntil.isAfter(now);
  }

  /** 노트북이 가져가 처리 중이다(임대가 지났어도 아직 아무도 다시 가져가지 않았으면 포함). */
  public boolean isWithProcessor() {
    return status == AnalysisStatus.RUNNING && processorLeaseUntil != null;
  }

  /** 노트북이 끝났다고 알려 BE 가 AI 에 맡길 차례다. */
  public boolean isProcessed() {
    return status == AnalysisStatus.RUNNING && processorRequestKey != null && aiJobId == null;
  }

  /**
   * 노트북이 가져갔다: RUNNING · LOADING_VIDEO, 임대 시작, 가져간 횟수 1 증가. 대기 중이면 시작 시각을 적고, 임대가 지난 작업을 다시 가져가면
   * 단계를 처음(LOADING_VIDEO)으로 되돌린다.
   */
  public void claimByProcessor(Instant now, Duration lease) {
    if (!isClaimableByProcessor(now)) {
      throw new IllegalStateException("분석 작업 " + id + " 은 노트북이 가져갈 수 없는 상태입니다(" + status + ").");
    }
    if (status == AnalysisStatus.PENDING) {
      start(now);
    }
    this.progressStage = ProgressStage.LOADING_VIDEO;
    this.processorLeaseUntil = now.plus(lease);
    this.processorClaims++;
  }

  /**
   * 노트북 진행 알림: 단계를 앞으로만 옮기고(늦게 온 알림이 되돌리지 않게) 임대를 다시 늘린다. 노트북이 처리 중일 때만.
   *
   * @param stage {@code LOADING_VIDEO} · {@code EXTRACTING_STEPS} · {@code SEGMENTING} 중 하나
   * @return 단계가 바뀌었으면 true
   */
  public boolean progressByProcessor(ProgressStage stage, Instant now, Duration lease) {
    if (!isWithProcessor()) {
      throw new IllegalStateException("분석 작업 " + id + " 은 노트북이 처리 중이 아닙니다.");
    }
    int next = processorStageRank(stage);
    if (next < 0) {
      throw new IllegalArgumentException("노트북 진행 단계로 " + stage + " 를 쓸 수 없습니다.");
    }
    this.processorLeaseUntil = now.plus(lease);
    if (next <= processorStageRank(progressStage)) {
      return false;
    }
    this.progressStage = stage;
    return true;
  }

  /** 노트북이 끝났다: AI 요청 JSON 키를 남기고 임대를 비운다. 단계는 BUILDING_GUIDE. 노트북이 처리 중일 때만. */
  public void completeByProcessor(String requestKey) {
    if (!isWithProcessor()) {
      throw new IllegalStateException("분석 작업 " + id + " 은 노트북이 처리 중이 아닙니다.");
    }
    if (requestKey == null
        || requestKey.isBlank()
        || requestKey.length() > PROCESSOR_REQUEST_KEY_MAX_LENGTH) {
      throw new IllegalArgumentException("AI 요청 JSON 키가 비었거나 너무 깁니다.");
    }
    this.processorRequestKey = requestKey;
    this.processorLeaseUntil = null;
    this.progressStage = ProgressStage.BUILDING_GUIDE;
  }

  /** 노트북 진행 단계 순서. 노트북은 영상 받기와 단계 추출(Gemini)을 함께 하고 프레임을 마지막에 뽑는다. 그 밖의 단계는 -1. */
  private static int processorStageRank(ProgressStage stage) {
    return switch (stage) {
      case LOADING_VIDEO -> 1;
      case EXTRACTING_STEPS -> 2;
      case SEGMENTING -> 3;
      default -> -1;
    };
  }

  /**
   * AI 서버에 가이드 생성을 맡겼다. 작업은 RUNNING 으로 남아 콜백(또는 시간 초과 감시)이 끝낸다. RUNNING 일 때만.
   *
   * @param aiJobId AI 서버가 돌려준 작업 ID. 콜백을 이 값으로 찾는다
   * @param now 맡긴 시각. 콜백 시간 초과의 기준이 된다
   */
  public void awaitAi(String aiJobId, Instant now) {
    requireStatus(AnalysisStatus.RUNNING, "AI 요청 기록");
    this.aiJobId = Objects.requireNonNull(aiJobId, "aiJobId");
    this.aiRequestedAt = Objects.requireNonNull(now, "now");
  }

  /**
   * AI 진행 알림의 숫자를 저장한다. AI 콜백을 기다리는 중일 때만 저장하고, 끝난 작업의 늦은 알림은 버린다. 숫자 검사는 부르는 쪽이 한다.
   *
   * <p>{@link #aiRequestedAt}이 비어 있으면(이 칸이 생기기 전에 맡긴 작업) 바뀌기 전의 {@code updatedAt}으로 먼저 채운다. 진행 숫자를
   * 처음 저장하기 전의 마지막 변경은 AI 접수라 맡긴 시각 근처이고, 이렇게 고정해 두면 이후 진행 숫자 저장이 시간 초과 기준을 밀지 않는다.
   *
   * @param progressJson 검사를 통과한 진행 숫자 JSON
   * @return 저장했으면 true. 콜백을 기다리는 중이 아니면 false
   */
  public boolean recordAiProgress(String progressJson) {
    Objects.requireNonNull(progressJson, "progressJson");
    if (!isAwaitingAi()) {
      return false;
    }
    if (aiRequestedAt == null) {
      this.aiRequestedAt = updatedAt;
    }
    this.aiProgress = progressJson;
    return true;
  }

  /**
   * 콜백 시간 초과의 기준 시각. AI 에 맡긴 시각이고, 비어 있으면(칸이 생기기 전에 맡긴 작업) 마지막 변경 시각이다. 감시 쿼리({@code
   * AnalysisJobRepository.findAwaitingAiRequestedBefore})와 같은 규칙이다.
   */
  public Instant aiTimeoutBaseline() {
    return aiRequestedAt != null ? aiRequestedAt : updatedAt;
  }

  /** AI 콜백을 기다리는 중인지. worker 재시작 때 대기열로 되돌리지 않는다(AI 에서는 아직 돌고 있을 수 있다). */
  public boolean isAwaitingAi() {
    return status == AnalysisStatus.RUNNING && aiJobId != null;
  }

  // --- 재시도 (API-VIDEO-006) ---

  /**
   * 실패한 작업을 다시 돌린다. 재시도할 수 있는 실패일 때만. 시도 횟수가 1 오르고 실패 · 진행 · AI 칸을 비운다.
   *
   * <p>노트북이 끝낸 작업(AI 요청 JSON 키가 있음)은 AI 에 맡길 차례(RUNNING · BUILDING_GUIDE)로 돌아가 같은 요청 JSON 으로 다시
   * 맡긴다. 그 전에 멈춘 작업은 노트북 · worker 가 중간부터 이어 받을 수 없어 대기열(PENDING · QUEUED)로 돌아가 처음부터 한다.
   */
  public void retry() {
    requireStatus(AnalysisStatus.FAILED, "재시도");
    if (!retryable) {
      throw new IllegalStateException("분석 작업 " + id + " 은 재시도할 수 없는 실패(" + failureCode + ")입니다.");
    }
    this.attempt++;
    this.failureCode = null;
    this.failureMessage = null;
    this.retryable = false;
    this.finishedAt = null;
    this.progressPercent = null;
    this.aiJobId = null;
    this.aiRequestedAt = null;
    this.aiProgress = null;
    this.processorLeaseUntil = null;
    this.processorClaims = 0;
    if (processorRequestKey != null) {
      this.status = AnalysisStatus.RUNNING;
      this.progressStage = ProgressStage.BUILDING_GUIDE;
    } else {
      this.status = AnalysisStatus.PENDING;
      this.progressStage = ProgressStage.QUEUED;
      this.startedAt = null;
    }
  }

  /** worker 가 처리 중에 죽었다. 다시 기동할 때 대기열로 돌린다. RUNNING 일 때만. */
  public void requeueAfterCrash() {
    requireStatus(AnalysisStatus.RUNNING, "재시작 복구");
    this.status = AnalysisStatus.PENDING;
    this.startedAt = null;
    // 노트북 연결 모드를 끈 뒤 되돌린 노트북 작업이면 임대를 비워 worker 가 처음부터 다시 처리하게 한다
    this.processorLeaseUntil = null;
  }

  private void requireStatus(AnalysisStatus expected, String action) {
    if (status != expected) {
      throw new IllegalStateException(
          "분석 작업 " + id + " 은 " + status + " 상태라 " + action + " 할 수 없습니다.");
    }
  }

  private static String truncate(String message) {
    return message.length() <= FAILURE_MESSAGE_MAX_LENGTH
        ? message
        : message.substring(0, FAILURE_MESSAGE_MAX_LENGTH);
  }

  public UUID getId() {
    return id;
  }

  public Video getVideo() {
    return video;
  }

  public AnalysisStatus getStatus() {
    return status;
  }

  public ProgressStage getProgressStage() {
    return progressStage;
  }

  public Integer getProgressPercent() {
    return progressPercent;
  }

  public boolean isRetryable() {
    return retryable;
  }

  public String getFailureCode() {
    return failureCode;
  }

  public String getFailureMessage() {
    return failureMessage;
  }

  public String getAiJobId() {
    return aiJobId;
  }

  public Instant getAiRequestedAt() {
    return aiRequestedAt;
  }

  public String getAiProgress() {
    return aiProgress;
  }

  public UUID getRequestedBy() {
    return requestedBy;
  }

  public Instant getProcessorLeaseUntil() {
    return processorLeaseUntil;
  }

  public int getProcessorClaims() {
    return processorClaims;
  }

  public String getProcessorRequestKey() {
    return processorRequestKey;
  }

  public int getAttempt() {
    return attempt;
  }

  public Instant getStartedAt() {
    return startedAt;
  }

  public Instant getFinishedAt() {
    return finishedAt;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
