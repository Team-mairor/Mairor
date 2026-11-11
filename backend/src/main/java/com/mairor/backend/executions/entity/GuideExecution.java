package com.mairor.backend.executions.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import lombok.Getter;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

/** 실행 당시의 가이드·버전은 불변이다. 회원 잠금 후 실행 행을 잠가 상태 전이를 직렬화한다. */
@Getter
@Entity
@Table(
    name = "guide_executions",
    uniqueConstraints = {
      @UniqueConstraint(name = "uk_guide_executions_face", columnNames = "face_registration_id"),
      @UniqueConstraint(name = "uk_guide_executions_record", columnNames = "record_id"),
      @UniqueConstraint(
          name = "uk_guide_executions_owner_session",
          columnNames = {"id", "user_id", "session_id"})
    },
    indexes =
        @Index(name = "idx_guide_executions_session", columnList = "user_id, session_id, status"))
public class GuideExecution {
  @Id private UUID id;

  @Column(name = "user_id", nullable = false, updatable = false)
  private UUID userId;

  /** 내부 인가용. API·로그·toString에 노출하지 않는다. 세션 삭제 이후 정리를 위해 세션 FK는 두지 않는다. */
  @Column(name = "session_id", nullable = false, updatable = false, length = 128)
  private String sessionId;

  @Column(name = "guide_id", nullable = false, updatable = false)
  private UUID guideId;

  @Column(name = "match_id", nullable = false, updatable = false)
  private UUID matchId;

  @Column(name = "face_registration_id", nullable = false, updatable = false)
  private UUID faceRegistrationId;

  @Column(name = "guide_version", nullable = false, updatable = false)
  private int guideVersion;

  @Column(name = "pouch_version", nullable = false, updatable = false)
  private long pouchVersion;

  @Column(name = "reference_version", nullable = false, updatable = false)
  private int referenceVersion;

  @Column(name = "compatibility_version", nullable = false, updatable = false)
  private int compatibilityVersion;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "guide_snapshot", nullable = false, updatable = false)
  private String guideSnapshot;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 16)
  private ExecutionStatus status;

  @Column(name = "photo_consent")
  private Boolean photoConsent;

  @Column(name = "consent_policy_version", length = 50)
  private String consentPolicyVersion;

  @Column(name = "consented_at")
  private Instant consentedAt;

  /** 완료 시 history_records.id를 보관한다. history_records.execution_id가 이 실행을 참조하므로 순환 FK는 두지 않는다. */
  @Column(name = "record_id")
  private UUID recordId;

  @Column(name = "completed_at")
  private Instant completedAt;

  @Column(name = "abandoned_at")
  private Instant abandonedAt;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected GuideExecution() {}

  public GuideExecution(
      UUID id,
      UUID userId,
      String sessionId,
      UUID guideId,
      UUID matchId,
      UUID faceRegistrationId,
      int guideVersion,
      long pouchVersion,
      int referenceVersion,
      int compatibilityVersion,
      String guideSnapshot) {
    this.id = Objects.requireNonNull(id, "id");
    this.userId = Objects.requireNonNull(userId, "userId");
    this.sessionId = text(sessionId, 128);
    this.guideId = Objects.requireNonNull(guideId, "guideId");
    this.matchId = Objects.requireNonNull(matchId, "matchId");
    this.faceRegistrationId = Objects.requireNonNull(faceRegistrationId, "faceRegistrationId");
    if (guideVersion < 1 || pouchVersion < 0 || referenceVersion < 0 || compatibilityVersion < 1) {
      throw new IllegalArgumentException("실행 버전이 유효하지 않다");
    }
    this.guideVersion = guideVersion;
    this.pouchVersion = pouchVersion;
    this.referenceVersion = referenceVersion;
    this.compatibilityVersion = compatibilityVersion;
    this.guideSnapshot = text(guideSnapshot, Integer.MAX_VALUE);
    this.status = ExecutionStatus.IN_PROGRESS;
  }

  /** 기록 저장·얼굴 보관과 같은 트랜잭션에서 사용한다. 기록 생성 자체는 이 엔티티의 책임이 아니다. */
  public void complete(UUID recordId, Instant now) {
    Objects.requireNonNull(recordId, "recordId");
    Objects.requireNonNull(now, "now");
    if (status == ExecutionStatus.COMPLETED && recordId.equals(this.recordId)) {
      return;
    }
    requireActive();
    this.recordId = recordId;
    this.completedAt = now;
    this.status = ExecutionStatus.COMPLETED;
  }

  /** 실행 중에만 사진 동의를 기록한다. 철회 시각은 최신 동의 시각으로 다시 기록한다. */
  public void setPhotoConsent(boolean enabled, String policyVersion, Instant now) {
    Objects.requireNonNull(now, "now");
    requireActive();
    if (policyVersion == null || policyVersion.isBlank() || policyVersion.length() > 50) {
      throw new IllegalArgumentException("사진 동의 정책 버전이 유효하지 않다");
    }
    boolean alreadyConsented = Boolean.TRUE.equals(photoConsent) && consentedAt != null;
    photoConsent = enabled;
    consentPolicyVersion = policyVersion;
    if (enabled) {
      if (!alreadyConsented) consentedAt = now;
    } else {
      consentedAt = null;
    }
  }

  /** 사진 읽기 차단·삭제 예약과 같은 트랜잭션에서 사용한다. 완료 실행은 포기할 수 없다. */
  public void abandon(Instant now) {
    Objects.requireNonNull(now, "now");
    if (status == ExecutionStatus.ABANDONED) {
      return;
    }
    requireActive();
    abandonedAt = now;
    status = ExecutionStatus.ABANDONED;
  }

  private void requireActive() {
    if (status != ExecutionStatus.IN_PROGRESS) {
      throw new IllegalStateException("진행 중인 실행만 종료할 수 있다");
    }
  }

  private static String text(String value, int max) {
    if (value == null || value.isBlank() || value.length() > max) {
      throw new IllegalArgumentException("실행 스냅샷 또는 세션 값이 유효하지 않다");
    }
    return value;
  }
}
