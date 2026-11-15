package com.mairor.backend.photos.entity;

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
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import lombok.Getter;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/** 이미지 바이트가 아닌 비공개 저장소 참조. 엔티티를 API 응답으로 직접 직렬화하지 않는다. */
@Getter
@Entity
@Table(
    name = "photos",
    uniqueConstraints = {
      @UniqueConstraint(name = "uk_photos_storage_key", columnNames = "storage_key"),
      @UniqueConstraint(
          name = "uk_photos_owner_session",
          columnNames = {"id", "user_id", "session_id"})
    },
    indexes = {
      @Index(name = "idx_photos_cleanup", columnList = "state, next_cleanup_at"),
      @Index(name = "idx_photos_expiry", columnList = "state, expires_at")
    })
public class StoredPhoto {
  public static final long MAX_BYTE_SIZE = 5L * 1024 * 1024;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "user_id")
  private UUID userId;

  /** Spring Session 식별자. 로그·응답·toString에 출력하지 않는다. */
  @Column(name = "session_id", length = 128)
  private String sessionId;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 24)
  private PhotoKind kind;

  @Column(name = "step_id", length = 200)
  private String stepId;

  @Column(name = "storage_key", nullable = false, length = 500)
  private String storageKey;

  @Column(name = "content_type", nullable = false, length = 32)
  private String contentType;

  @Column(name = "byte_size", nullable = false)
  private long byteSize;

  @Column(nullable = false)
  private int width;

  @Column(nullable = false)
  private int height;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 24)
  private PhotoState state;

  @Column(name = "expires_at")
  private Instant expiresAt;

  @Column(name = "cleanup_requested_at")
  private Instant cleanupRequestedAt;

  @Column(name = "next_cleanup_at")
  private Instant nextCleanupAt;

  @Column(name = "cleanup_attempts", nullable = false)
  private int cleanupAttempts;

  @Column(name = "deleted_at")
  private Instant deletedAt;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected StoredPhoto() {}

  /** 저장소 업로드 전에 행을 남길 수 있도록 PENDING_UPLOAD로 시작한다. */
  public StoredPhoto(
      UUID userId,
      String sessionId,
      PhotoKind kind,
      String stepId,
      String storageKey,
      String contentType,
      long byteSize,
      int width,
      int height,
      Instant expiresAt) {
    this.userId = userId;
    this.sessionId = sessionId == null ? null : required(sessionId, 128);
    this.kind = Objects.requireNonNull(kind, "kind");
    this.stepId = stepId == null ? null : required(stepId, 200);
    if (kind == PhotoKind.PHOTO_BOOTH) {
      if (userId != null || sessionId != null || this.stepId != null) {
        throw new IllegalArgumentException("네컷 공유 사진은 회원·세션·단계에 연결하지 않는다");
      }
    } else if (userId == null
        || this.sessionId == null
        || (kind == PhotoKind.STEP) != (this.stepId != null)) {
      throw new IllegalArgumentException("사진 종류에 맞는 회원·세션·단계 정보가 필요하다");
    }
    this.storageKey = required(storageKey, 500);
    if (!"image/jpeg".equals(contentType) && !"image/png".equals(contentType)) {
      throw new IllegalArgumentException("JPEG 또는 PNG만 저장할 수 있다");
    }
    if (byteSize < 1 || byteSize > MAX_BYTE_SIZE || width < 1 || height < 1) {
      throw new IllegalArgumentException("사진 크기와 해상도가 유효하지 않다");
    }
    this.contentType = contentType;
    this.byteSize = byteSize;
    this.width = width;
    this.height = height;
    this.expiresAt = expiresAt;
    this.state = PhotoState.PENDING_UPLOAD;
  }

  public void markAvailable() {
    if (state != PhotoState.PENDING_UPLOAD) {
      throw new IllegalStateException("업로드 대기 사진만 공개 가능한 상태로 전환할 수 있다");
    }
    state = PhotoState.AVAILABLE;
  }

  /** 도메인 행과 연결하는 트랜잭션에서 호출한다. 이후 수명은 얼굴 등록/실행 도메인이 관리한다. */
  public void markAttached() {
    if (state != PhotoState.AVAILABLE) {
      throw new IllegalStateException("저장 완료 사진만 연결할 수 있다");
    }
    expiresAt = null;
  }

  /** 읽기 차단과 삭제 예약은 같은 DB 트랜잭션에서 처리한다. 중복 요청은 일정을 초기화하지 않는다. */
  public void requestCleanup(Instant now) {
    Objects.requireNonNull(now, "now");
    if (state == PhotoState.DELETED || state == PhotoState.CLEANUP_PENDING) {
      return;
    }
    state = PhotoState.CLEANUP_PENDING;
    cleanupRequestedAt = now;
    nextCleanupAt = now;
  }

  public void recordCleanupFailure(Instant retryAt) {
    if (state != PhotoState.CLEANUP_PENDING) {
      throw new IllegalStateException("정리 대기 사진만 재시도할 수 있다");
    }
    nextCleanupAt = Objects.requireNonNull(retryAt, "retryAt");
    cleanupAttempts = Math.incrementExact(cleanupAttempts);
  }

  public void markDeleted(Instant now) {
    Objects.requireNonNull(now, "now");
    if (state == PhotoState.DELETED) {
      return;
    }
    if (state != PhotoState.CLEANUP_PENDING) {
      throw new IllegalStateException("정리 대기 사진만 삭제 완료할 수 있다");
    }
    state = PhotoState.DELETED;
    deletedAt = now;
    nextCleanupAt = null;
  }

  private static String required(String value, int max) {
    Objects.requireNonNull(value, "text");
    if (value.isBlank() || value.length() > max) {
      throw new IllegalArgumentException("사진 메타데이터 길이가 유효하지 않다");
    }
    return value;
  }
}
