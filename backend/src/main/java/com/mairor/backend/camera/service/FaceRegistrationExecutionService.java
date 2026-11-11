package com.mairor.backend.camera.service;

import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.photos.service.PhotoRecordService;
import com.mairor.backend.users.repository.UserRepository;
import java.time.Clock;
import java.util.Objects;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 395가 실행 생성/완료/중도 종료 DB 트랜잭션 안에서 호출한다. 호출자는 회원 잠금을 실행 행보다 먼저 잡아 회원 → 실행/등록 → 사진 순서를 지킨다. 파일 삭제는 커밋
 * 뒤 사진 정리 작업이 처리한다.
 */
@Service
@Transactional(propagation = Propagation.MANDATORY)
public class FaceRegistrationExecutionService {
  private final FaceRegistrationRepository registrations;
  private final StoredPhotoRepository photos;
  private final PhotoRecordService photoRecords;
  private final GuideRepository guides;
  private final UserRepository users;
  private final Clock clock;

  public FaceRegistrationExecutionService(
      FaceRegistrationRepository registrations,
      StoredPhotoRepository photos,
      PhotoRecordService photoRecords,
      GuideRepository guides,
      UserRepository users,
      Clock clock) {
    this.registrations = registrations;
    this.photos = photos;
    this.photoRecords = photoRecords;
    this.guides = guides;
    this.users = users;
    this.clock = clock;
  }

  public void link(
      UUID userId,
      String sessionId,
      UUID registrationId,
      UUID videoId,
      UUID guideId,
      UUID executionId) {
    Objects.requireNonNull(executionId, "executionId");
    FaceRegistration registration = owned(userId, sessionId, registrationId);
    if (registration.getDiscardedAt() != null || !registration.getVideoId().equals(videoId)) {
      throw notFound();
    }
    if (registration.getStatus() != FaceRegistrationStatus.REGISTERED) {
      throw new BusinessException(
          HttpStatus.CONFLICT, "FACE_REGISTRATION_ALREADY_USED", "다른 실행에 이미 사용한 얼굴 등록입니다.");
    }
    guides
        .findById(guideId)
        .filter(
            guide ->
                guide.getVideo().getId().equals(videoId)
                    && guide.getReviewStatus() == ReviewStatus.APPROVED)
        .orElseThrow(FaceRegistrationExecutionService::notFound);
    photos
        .findByIdForUpdate(registration.getPhotoId())
        .filter(
            photo ->
                photo.getKind() == PhotoKind.FACE_REGISTRATION
                    && photo.getState() == PhotoState.AVAILABLE)
        .orElseThrow(FaceRegistrationExecutionService::notFound);
    registration.linkToExecution(guideId, executionId);
  }

  public void retain(UUID userId, String sessionId, UUID registrationId, UUID executionId) {
    FaceRegistration registration = forExecution(userId, sessionId, registrationId, executionId);
    if (registration.getDiscardedAt() != null) {
      throw notFound();
    }
    if (registration.getStatus() != FaceRegistrationStatus.LINKED
        && registration.getStatus() != FaceRegistrationStatus.RETAINED) {
      throw inUse();
    }
    registration.retain(executionId);
  }

  public UUID abandon(UUID userId, String sessionId, UUID registrationId, UUID executionId) {
    FaceRegistration registration = forExecution(userId, sessionId, registrationId, executionId);
    if (registration.getStatus() != FaceRegistrationStatus.LINKED) {
      throw inUse();
    }
    registration.discard(clock.instant());
    photoRecords.requestCleanupInCurrentTransaction(registration.getPhotoId());
    return registration.getPhotoId();
  }

  private FaceRegistration forExecution(
      UUID userId, String sessionId, UUID registrationId, UUID executionId) {
    FaceRegistration registration = owned(userId, sessionId, registrationId);
    if (!Objects.equals(registration.getExecutionId(), executionId) || executionId == null) {
      throw notFound();
    }
    return registration;
  }

  private FaceRegistration owned(UUID userId, String sessionId, UUID registrationId) {
    users.findByIdForUpdate(userId).orElseThrow(FaceRegistrationExecutionService::notFound);
    return registrations
        .findOwnedForUpdate(registrationId, userId)
        .filter(value -> value.getSessionId().equals(sessionId))
        .orElseThrow(FaceRegistrationExecutionService::notFound);
  }

  private static BusinessException notFound() {
    return new BusinessException(ErrorCode.NOT_FOUND);
  }

  private static BusinessException inUse() {
    return new BusinessException(
        HttpStatus.CONFLICT, "FACE_REGISTRATION_IN_USE", "현재 실행 상태에서는 얼굴 등록을 변경할 수 없습니다.");
  }
}
