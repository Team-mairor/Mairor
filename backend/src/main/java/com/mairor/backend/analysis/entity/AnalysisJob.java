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
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 영상 한 편의 분석 작업. 상태 전이는 S15P31A306-308 에서 이 클래스에 더한다.
 *
 * <p>같은 영상의 진행 중(PENDING·RUNNING) 작업은 하나뿐이다. JPA 로 표현할 수 없는 부분 유일 인덱스({@value
 * #VIDEO_ACTIVE_UNIQUE})라 {@code db/schema/analysis.sql}에만 있다. 동시에 두 요청이 작업을 만들면 나중 것이 이 인덱스에 막힌다.
 *
 * <p>{@code requestedBy}는 분석을 요청한 회원 ID 이고 운영 명령으로 만든 작업은 {@code null}이다. {@code aiJobId}는 AI 서버가
 * 돌려준 가이드 생성 작업 ID 로, 콜백을 이 값으로 찾는다.
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

  @Column(name = "requested_by")
  private UUID requestedBy;

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
  }

  /** worker 가 처리 중에 죽었다. 다시 기동할 때 대기열로 돌린다. RUNNING 일 때만. */
  public void requeueAfterCrash() {
    requireStatus(AnalysisStatus.RUNNING, "재시작 복구");
    this.status = AnalysisStatus.PENDING;
    this.startedAt = null;
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

  public UUID getRequestedBy() {
    return requestedBy;
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
