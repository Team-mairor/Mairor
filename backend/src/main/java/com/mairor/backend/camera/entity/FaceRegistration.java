package com.mairor.backend.camera.entity;

import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
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

/** 실행마다 새로 등록하는 기준 얼굴 한 장. 사진 파일·특징점·얼굴 프로필을 담지 않는다. */
@Getter
@Entity
@Table(
    name = "face_registrations",
    uniqueConstraints = {
      @UniqueConstraint(name = "uk_face_registrations_photo", columnNames = "photo_id"),
      @UniqueConstraint(name = "uk_face_registrations_execution", columnNames = "execution_id")
    },
    indexes =
        @Index(name = "idx_face_registrations_session", columnList = "user_id, session_id, status"))
public class FaceRegistration {
  public static final String ACTIVE_UNIQUE = "uk_face_registrations_registered";

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "user_id", nullable = false)
  private UUID userId;

  @Column(name = "session_id", nullable = false, length = 128)
  private String sessionId;

  @Column(name = "video_id", nullable = false)
  private UUID videoId;

  @Column(name = "guide_id")
  private UUID guideId;

  @Column(name = "photo_id", nullable = false)
  private UUID photoId;

  /** 실행 테이블 FK는 S15P31A306-395에서 추가한다. */
  @Column(name = "execution_id")
  private UUID executionId;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 16)
  private FaceRegistrationStatus status;

  @Embedded private FaceChecks checks;

  @Column(name = "notice_version", nullable = false, length = 50)
  private String noticeVersion;

  @Column(name = "agreed_at", nullable = false)
  private Instant agreedAt;

  @Column(name = "discarded_at")
  private Instant discardedAt;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected FaceRegistration() {}

  public FaceRegistration(
      StoredPhoto photo,
      UUID videoId,
      UUID guideId,
      FaceChecks checks,
      String noticeVersion,
      Instant agreedAt) {
    Objects.requireNonNull(photo, "photo");
    if (photo.getKind() != PhotoKind.FACE_REGISTRATION
        || photo.getState() != PhotoState.AVAILABLE) {
      throw new IllegalArgumentException("저장 완료된 얼굴 등록 사진만 연결할 수 있다");
    }
    this.photoId = Objects.requireNonNull(photo.getId(), "photoId");
    this.userId = photo.getUserId();
    this.sessionId = photo.getSessionId();
    this.videoId = Objects.requireNonNull(videoId, "videoId");
    this.guideId = guideId;
    this.checks = Objects.requireNonNull(checks, "checks");
    if (noticeVersion == null || noticeVersion.isBlank() || noticeVersion.length() > 50) {
      throw new IllegalArgumentException("얼굴 등록 안내 버전이 유효하지 않다");
    }
    this.noticeVersion = noticeVersion;
    this.agreedAt = Objects.requireNonNull(agreedAt, "agreedAt");
    this.status = FaceRegistrationStatus.REGISTERED;
  }

  /** 본인 실행 연결 검증 후 같은 DB 트랜잭션에서 호출한다. */
  public void linkToExecution(UUID guideId, UUID executionId) {
    if (status != FaceRegistrationStatus.REGISTERED || discardedAt != null) {
      throw new IllegalStateException("유효한 미연결 얼굴 등록만 실행에 연결할 수 있다");
    }
    this.guideId = Objects.requireNonNull(guideId, "guideId");
    this.executionId = Objects.requireNonNull(executionId, "executionId");
    status = FaceRegistrationStatus.LINKED;
  }

  /** 완료 재시도에서 같은 실행의 보관 전환은 멱등이다. */
  public void retain(UUID executionId) {
    if (!Objects.equals(this.executionId, executionId)
        || discardedAt != null
        || (status != FaceRegistrationStatus.LINKED && status != FaceRegistrationStatus.RETAINED)) {
      throw new IllegalStateException("해당 실행에 연결된 얼굴 등록만 보관할 수 있다");
    }
    status = FaceRegistrationStatus.RETAINED;
  }

  /** 파일 삭제 전 폐기 시각을 먼저 저장해 조회를 차단한다. */
  public void discard(Instant now) {
    Objects.requireNonNull(now, "now");
    if (discardedAt == null) {
      discardedAt = now;
    }
  }
}
