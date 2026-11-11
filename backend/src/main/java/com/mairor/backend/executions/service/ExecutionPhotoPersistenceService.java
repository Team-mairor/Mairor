package com.mairor.backend.executions.service;

import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.executions.dto.PhotoConsentResponse;
import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.entity.ExecutionStep;
import com.mairor.backend.executions.entity.GuideExecution;
import com.mairor.backend.executions.repository.ExecutionStepRepository;
import com.mairor.backend.executions.repository.GuideExecutionRepository;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.photos.service.PhotoRecordService;
import java.time.Clock;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Upload I/O 전후에 실행·단계·사진 행을 보호하는 짧은 DB 트랜잭션. */
@Service
public class ExecutionPhotoPersistenceService {
  private final GuideExecutionRepository executions;
  private final ExecutionStepRepository steps;
  private final PhotoRecordService records;
  private final StoredPhotoRepository photos;
  private final FaceRegistrationRepository faceRegistrations;
  private final Clock clock;

  public ExecutionPhotoPersistenceService(
      GuideExecutionRepository executions,
      ExecutionStepRepository steps,
      PhotoRecordService records,
      StoredPhotoRepository photos,
      FaceRegistrationRepository faceRegistrations,
      Clock clock) {
    this.executions = executions;
    this.steps = steps;
    this.records = records;
    this.photos = photos;
    this.faceRegistrations = faceRegistrations;
    this.clock = clock;
  }

  @Transactional
  public PhotoConsentResponse setConsent(
      UUID userId, String sessionId, UUID executionId, boolean enabled, String policyVersion) {
    GuideExecution execution = ownedActive(userId, sessionId, executionId);
    var now = clock.instant().truncatedTo(ChronoUnit.MICROS);
    execution.setPhotoConsent(enabled, policyVersion, now);
    return new PhotoConsentResponse(enabled, policyVersion, execution.getConsentedAt());
  }

  @Transactional
  public void validateUpload(UUID userId, String sessionId, UUID executionId, String stepId) {
    GuideExecution execution = ownedActive(userId, sessionId, executionId);
    requireConsent(execution);
    ExecutionStep step =
        steps.findByExecutionIdAndStepId(executionId, stepId).orElseThrow(this::notFound);
    requireAllowed(step);
  }

  @Transactional
  public UUID attach(UUID userId, String sessionId, UUID executionId, String stepId, UUID photoId) {
    GuideExecution execution = ownedActive(userId, sessionId, executionId);
    requireConsent(execution);
    ExecutionStep step =
        steps.findByExecutionIdAndStepIdForUpdate(executionId, stepId).orElseThrow(this::notFound);
    requireAllowed(step);
    StoredPhoto photo = records.attach(photoId, userId, sessionId);
    UUID oldPhotoId = step.getPhotoId();
    step.attachPhoto(photo);
    return oldPhotoId;
  }

  @Transactional(readOnly = true)
  public PhotoDownload getDownload(UUID userId, String sessionId, UUID photoId) {
    StoredPhoto photo = photos.findByIdAndUserId(photoId, userId).orElseThrow(this::notFound);
    if (photo.getState() != PhotoState.AVAILABLE || photo.getExpiresAt() != null) {
      throw notFound();
    }
    if (photo.getKind() == PhotoKind.STEP) {
      ExecutionStep step = steps.findByPhotoId(photoId).orElseThrow(this::notFound);
      GuideExecution execution =
          executions.findByIdAndUserId(step.getExecutionId(), userId).orElseThrow(this::notFound);
      if (!readable(execution, sessionId)) throw notFound();
    } else {
      FaceRegistration registration =
          faceRegistrations.findByPhotoIdAndUserId(photoId, userId).orElseThrow(this::notFound);
      if (registration.getDiscardedAt() != null) throw notFound();
      if (registration.getStatus() == FaceRegistrationStatus.REGISTERED) {
        if (!sessionId.equals(registration.getSessionId())) throw notFound();
      } else {
        GuideExecution execution =
            executions
                .findByIdAndUserId(registration.getExecutionId(), userId)
                .orElseThrow(this::notFound);
        if (!readable(execution, sessionId)) throw notFound();
      }
    }
    return new PhotoDownload(photo.getStorageKey(), photo.getContentType());
  }

  private boolean readable(GuideExecution execution, String sessionId) {
    return execution.getStatus() != ExecutionStatus.ABANDONED
        && (execution.getStatus() == ExecutionStatus.COMPLETED
            || sessionId.equals(execution.getSessionId()));
  }

  public record PhotoDownload(String storageKey, String contentType) {}

  private void requireAllowed(ExecutionStep step) {
    if (step.isSkipped()) {
      throw new BusinessException(
          HttpStatus.CONFLICT, "GUIDE_STEP_PHOTO_NOT_ALLOWED", "선택하지 않은 단계에는 사진을 연결할 수 없습니다.");
    }
  }

  private GuideExecution ownedActive(UUID userId, String sessionId, UUID executionId) {
    GuideExecution execution =
        executions.findOwnedForUpdate(executionId, userId).orElseThrow(this::notFound);
    if (!sessionId.equals(execution.getSessionId())) throw notFound();
    if (execution.getStatus() != ExecutionStatus.IN_PROGRESS) {
      throw new BusinessException(
          HttpStatus.CONFLICT, "GUIDE_EXECUTION_NOT_ACTIVE", "진행 중인 실행에서만 사진 동의와 업로드를 변경할 수 있습니다.");
    }
    return execution;
  }

  private void requireConsent(GuideExecution execution) {
    if (!Boolean.TRUE.equals(execution.getPhotoConsent())) {
      throw new BusinessException(
          HttpStatus.CONFLICT, "GUIDE_PHOTO_CONSENT_REQUIRED", "단계 사진을 저장하려면 사진 저장에 동의해야 합니다.");
    }
  }

  private BusinessException notFound() {
    return new BusinessException(ErrorCode.NOT_FOUND);
  }
}
