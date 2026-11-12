package com.mairor.backend.executions.entity;

import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.Objects;
import java.util.UUID;
import lombok.Getter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** 단계·선택 제품/색 스냅샷은 불변이며 현재 사진 참조만 교체한다. 삭제된 파우치 항목에 FK를 두지 않는다. */
@Getter
@Entity
@Table(
    name = "execution_steps",
    uniqueConstraints = {
      @UniqueConstraint(
          name = "uk_execution_steps_step",
          columnNames = {"execution_id", "step_id"}),
      @UniqueConstraint(
          name = "uk_execution_steps_position",
          columnNames = {"execution_id", "position"}),
      @UniqueConstraint(name = "uk_execution_steps_photo", columnNames = "photo_id")
    })
public class ExecutionStep {
  @Id private UUID id;

  @Column(name = "execution_id", nullable = false, updatable = false)
  private UUID executionId;

  @Column(name = "user_id", nullable = false, updatable = false)
  private UUID userId;

  @Column(name = "session_id", nullable = false, updatable = false, length = 128)
  private String sessionId;

  @Column(name = "step_id", nullable = false, updatable = false, length = 200)
  private String stepId;

  @Column(nullable = false, updatable = false)
  private int position;

  @Column(nullable = false, updatable = false)
  private boolean skipped;

  /** GuideStep/MatchStep·최종 선택 제품·색 칸/색·선택 이유. 사진은 이 JSON에 저장하지 않는다. */
  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "step_snapshot", nullable = false, updatable = false)
  private String stepSnapshot;

  @Column(name = "photo_id")
  private UUID photoId;

  protected ExecutionStep() {}

  public ExecutionStep(
      GuideExecution execution, String stepId, int position, boolean skipped, String stepSnapshot) {
    Objects.requireNonNull(execution, "execution");
    if (execution.getStatus() != ExecutionStatus.IN_PROGRESS) {
      throw new IllegalArgumentException("진행 중인 실행에만 단계 스냅샷을 생성할 수 있다");
    }
    if (stepId == null || stepId.isBlank() || stepId.length() > 200 || position < 0) {
      throw new IllegalArgumentException("단계 ID와 순서가 유효하지 않다");
    }
    if (stepSnapshot == null || stepSnapshot.isBlank()) {
      throw new IllegalArgumentException("단계 스냅샷이 필요하다");
    }
    this.id = UUID.randomUUID();
    this.executionId = execution.getId();
    this.userId = execution.getUserId();
    this.sessionId = execution.getSessionId();
    this.stepId = stepId;
    this.position = position;
    this.skipped = skipped;
    this.stepSnapshot = stepSnapshot;
  }

  /** 호출자는 실행의 상태·동의를 잠금 안에서 검증하고 PhotoRecordService.attach를 먼저 호출한다. */
  public void attachPhoto(StoredPhoto photo) {
    Objects.requireNonNull(photo, "photo");
    if (photo.getKind() != PhotoKind.STEP
        || photo.getState() != PhotoState.AVAILABLE
        || photo.getExpiresAt() != null
        || !userId.equals(photo.getUserId())
        || !sessionId.equals(photo.getSessionId())
        || !stepId.equals(photo.getStepId())) {
      throw new IllegalArgumentException("해당 단계에 연결할 수 없는 사진이다");
    }
    photoId = Objects.requireNonNull(photo.getId(), "photoId");
  }
}
