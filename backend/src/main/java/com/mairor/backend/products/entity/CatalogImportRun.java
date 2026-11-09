package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 카탈로그 적재 실행. 수집기가 한 번 돌린 실행 하나가 한 행이다. {@code runId}는 수집기가 실행 결과 파일 header 에 쓴 값이고 유니크라, 끊긴 실행을
 * 이어서 보내도 같은 행을 쓴다.
 *
 * <p>이미지 URL·영역·방법 같은 근거는 DB 에 두지 않고 {@code resultFile}(공유 볼륨의 상대 이름)에 둔다. 진행 중({@link
 * ImportRunStatus#RUNNING})에는 {@code finishedAt}이 없고, 끝나면 반드시 있다.
 */
@Entity
@Table(
    name = "catalog_import_runs",
    uniqueConstraints =
        @UniqueConstraint(name = CatalogImportRun.RUN_ID_UNIQUE, columnNames = "run_id"),
    indexes =
        @Index(
            name = CatalogImportRun.STATUS_HEARTBEAT_INDEX,
            columnList = "status, last_heartbeat_at"))
public class CatalogImportRun {

  public static final String RUN_ID_UNIQUE = "uk_catalog_import_runs_run_id";
  public static final String STATUS_HEARTBEAT_INDEX = "idx_catalog_import_runs_status_heartbeat";
  public static final String STATUS_CHECK = "ck_catalog_import_runs_status";
  public static final String FINISHED_CHECK = "ck_catalog_import_runs_finished";

  public static final int RUN_ID_MAX_LENGTH = 100;
  public static final int SEED_MAX_LENGTH = 100;
  public static final int COLLECTOR_VERSION_MAX_LENGTH = 50;
  public static final int RESULT_FILE_MAX_LENGTH = 200;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "run_id", nullable = false, length = RUN_ID_MAX_LENGTH)
  private String runId;

  @Column(length = SEED_MAX_LENGTH)
  private String seed;

  @Column(name = "collector_version", length = COLLECTOR_VERSION_MAX_LENGTH)
  private String collectorVersion;

  @Column(name = "result_file", length = RESULT_FILE_MAX_LENGTH)
  private String resultFile;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private ImportRunStatus status;

  /** 수집기가 header 에 적은 시작 시각. */
  @Column(name = "collector_started_at")
  private Instant collectorStartedAt;

  @Column(name = "last_heartbeat_at", nullable = false)
  private Instant lastHeartbeatAt;

  @Column(name = "finished_at")
  private Instant finishedAt;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected CatalogImportRun() {}

  /**
   * 새 실행을 진행 중으로 연다.
   *
   * @param now 서버가 받은 시각. 첫 하트비트 시각이 된다
   * @throws IllegalArgumentException {@code runId}가 비었거나, 값이 컬럼 길이를 넘으면
   */
  public CatalogImportRun(
      String runId,
      String seed,
      String collectorVersion,
      String resultFile,
      Instant collectorStartedAt,
      Instant now) {
    this.runId = require(runId, "runId", RUN_ID_MAX_LENGTH);
    this.seed = optional(seed, "seed", SEED_MAX_LENGTH);
    this.collectorVersion =
        optional(collectorVersion, "collectorVersion", COLLECTOR_VERSION_MAX_LENGTH);
    this.resultFile = optional(resultFile, "resultFile", RESULT_FILE_MAX_LENGTH);
    this.collectorStartedAt = collectorStartedAt;
    this.status = ImportRunStatus.RUNNING;
    this.lastHeartbeatAt = Objects.requireNonNull(now, "now");
  }

  /**
   * 살아 있다고 알린다.
   *
   * @throws IllegalStateException 이미 끝난 실행이면
   */
  public void heartbeat(Instant now) {
    requireRunning();
    this.lastHeartbeatAt = Objects.requireNonNull(now, "now");
  }

  /** 수집기가 끝났다고 알렸다. */
  public void complete(Instant now) {
    finish(ImportRunStatus.COMPLETED, now);
  }

  /** 수집기가 실행을 실패로 끝냈다. */
  public void fail(Instant now) {
    finish(ImportRunStatus.FAILED, now);
  }

  /** 하트비트가 끊겨 서버가 끝냈다. */
  public void abandon(Instant now) {
    finish(ImportRunStatus.ABANDONED, now);
  }

  /**
   * 진행 중인데 마지막 하트비트가 제한을 넘었는가.
   *
   * @param timeout 이 시간 안에 하트비트가 없으면 끊긴 것으로 본다
   */
  public boolean isAbandonedAt(Instant now, Duration timeout) {
    return status == ImportRunStatus.RUNNING
        && lastHeartbeatAt.plus(timeout).isBefore(Objects.requireNonNull(now, "now"));
  }

  private void finish(ImportRunStatus end, Instant now) {
    requireRunning();
    if (!end.isFinished()) {
      throw new IllegalArgumentException("끝내는 상태가 아니다: " + end);
    }
    this.status = end;
    this.finishedAt = Objects.requireNonNull(now, "now");
  }

  private void requireRunning() {
    if (status != ImportRunStatus.RUNNING) {
      throw new IllegalStateException("이미 끝난 실행이다: " + status);
    }
  }

  private static String require(String value, String field, int maxLength) {
    if (value == null || value.isBlank()) {
      throw new IllegalArgumentException(field + " 는 비어 있을 수 없다");
    }
    return optional(value, field, maxLength);
  }

  private static String optional(String value, String field, int maxLength) {
    if (value != null && value.length() > maxLength) {
      throw new IllegalArgumentException(field + " 는 " + maxLength + "자까지다");
    }
    return value;
  }

  public UUID getId() {
    return id;
  }

  public String getRunId() {
    return runId;
  }

  public String getSeed() {
    return seed;
  }

  public String getCollectorVersion() {
    return collectorVersion;
  }

  public String getResultFile() {
    return resultFile;
  }

  public ImportRunStatus getStatus() {
    return status;
  }

  public Instant getCollectorStartedAt() {
    return collectorStartedAt;
  }

  public Instant getLastHeartbeatAt() {
    return lastHeartbeatAt;
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
