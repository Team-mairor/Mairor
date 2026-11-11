package com.mairor.backend.camera.service;

import com.mairor.backend.camera.dto.FaceChecksData;
import com.mairor.backend.camera.dto.FaceRegistrationRequest;
import com.mairor.backend.camera.dto.FaceRegistrationResponse;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.service.PhotoCleanupService;
import com.mairor.backend.photos.service.PhotoUploadService;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/** 파일 처리와 얼굴 등록 DB 트랜잭션을 분리하고 저장 실패를 보상한다. */
@Service
public class FaceRegistrationService {
  private static final Logger log = LoggerFactory.getLogger(FaceRegistrationService.class);
  private final FaceRegistrationStore store;
  private final FaceRegistrationProperties properties;
  private final PhotoUploadService uploads;
  private final PhotoCleanupService cleanup;

  public FaceRegistrationService(
      FaceRegistrationStore store,
      FaceRegistrationProperties properties,
      PhotoUploadService uploads,
      PhotoCleanupService cleanup) {
    this.store = store;
    this.properties = properties;
    this.uploads = uploads;
    this.cleanup = cleanup;
  }

  @Transactional(propagation = Propagation.NEVER)
  public FaceRegistrationResponse register(
      UUID userId, String sessionId, FaceRegistrationRequest request, MultipartFile image) {
    validate(request);
    store.validateReferences(request);
    UUID photoId;
    try {
      photoId = uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image);
    } catch (StorageException e) {
      throw unavailable();
    }
    FaceRegistrationStore.Saved saved;
    try {
      saved = store.register(userId, sessionId, photoId, request);
    } catch (RuntimeException failure) {
      try {
        uploads.discard(photoId);
      } catch (RuntimeException compensation) {
        failure.addSuppressed(compensation);
      }
      throw failure;
    }
    if (saved.replacedPhotoId() != null) {
      try {
        cleanup.cleanup(saved.replacedPhotoId());
      } catch (RuntimeException e) {
        log.warn("재촬영 후 이전 사진 정리는 다음 주기에 재시도한다 photoId={}", saved.replacedPhotoId());
      }
    }
    return saved.response();
  }

  public FaceRegistrationResponse get(UUID userId, String sessionId, UUID registrationId) {
    return store.get(userId, sessionId, registrationId);
  }

  @Transactional(propagation = Propagation.NEVER)
  public void delete(UUID userId, String sessionId, UUID registrationId) {
    UUID photoId = store.discard(userId, sessionId, registrationId);
    if (!cleanup.cleanup(photoId)) {
      throw unavailable();
    }
  }

  private void validate(FaceRegistrationRequest request) {
    if (request == null || request.videoId() == null || request.checks() == null) {
      throw new BusinessException(ErrorCode.VALIDATION_FAILED);
    }
    if (!Boolean.TRUE.equals(request.agreed())) {
      throw new BusinessException(
          HttpStatus.BAD_REQUEST, "FACE_CONSENT_REQUIRED", "얼굴 등록 안내 동의가 필요합니다.");
    }
    if (!properties.noticeVersion().equals(request.noticeVersion())) {
      throw new BusinessException(
          HttpStatus.BAD_REQUEST, "FACE_NOTICE_VERSION_INVALID", "현재 얼굴 등록 안내 버전으로 동의해야 합니다.");
    }
    FaceChecksData checks = request.checks();
    if (!Boolean.TRUE.equals(checks.lighting())
        || !Boolean.TRUE.equals(checks.distance())
        || !Boolean.TRUE.equals(checks.frontal())
        || !Boolean.TRUE.equals(checks.unobstructed())) {
      throw new BusinessException(
          HttpStatus.BAD_REQUEST, "FACE_CONDITIONS_NOT_MET", "필수 촬영 조건을 모두 만족해야 합니다.");
    }
    if (checks.makeupDetected() == null) {
      throw new BusinessException(ErrorCode.VALIDATION_FAILED);
    }
  }

  private BusinessException unavailable() {
    return new BusinessException(
        ErrorCode.SERVICE_UNAVAILABLE, "사진 저장소 처리에 실패했습니다. 잠시 후 다시 시도해 주세요.");
  }
}
