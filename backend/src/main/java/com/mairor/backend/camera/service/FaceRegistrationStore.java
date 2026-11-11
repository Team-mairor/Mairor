package com.mairor.backend.camera.service;

import com.mairor.backend.camera.dto.FaceRegistrationRequest;
import com.mairor.backend.camera.dto.FaceRegistrationResponse;
import com.mairor.backend.camera.entity.FaceChecks;
import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.photos.service.PhotoRecordService;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.videos.repository.VideoRepository;
import java.time.Clock;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 회원 → 얼굴 등록 → 사진 순서로 잠근다. 파일 전송/삭제는 이 트랜잭션 밖에서 수행한다. */
@Service
public class FaceRegistrationStore {
  private final FaceRegistrationRepository registrations;
  private final StoredPhotoRepository photos;
  private final PhotoRecordService photoRecords;
  private final UserRepository users;
  private final VideoRepository videos;
  private final GuideRepository guides;
  private final Clock clock;

  public FaceRegistrationStore(
      FaceRegistrationRepository registrations,
      StoredPhotoRepository photos,
      PhotoRecordService photoRecords,
      UserRepository users,
      VideoRepository videos,
      GuideRepository guides,
      Clock clock) {
    this.registrations = registrations;
    this.photos = photos;
    this.photoRecords = photoRecords;
    this.users = users;
    this.videos = videos;
    this.guides = guides;
    this.clock = clock;
  }

  @Transactional(readOnly = true)
  public void validateReferences(FaceRegistrationRequest request) {
    if (!videos.existsById(request.videoId())) {
      throw notFound();
    }
    if (request.guideId() != null) {
      guides
          .findById(request.guideId())
          .filter(
              guide ->
                  guide.getVideo().getId().equals(request.videoId())
                      && guide.getReviewStatus() == ReviewStatus.APPROVED)
          .orElseThrow(FaceRegistrationStore::notFound);
    }
  }

  @Transactional
  public Saved register(
      UUID userId, String sessionId, UUID photoId, FaceRegistrationRequest request) {
    users.findByIdForUpdate(userId).orElseThrow(FaceRegistrationStore::notFound);
    validateReferences(request);
    FaceRegistration old =
        registrations
            .findByUserIdAndSessionIdAndVideoIdAndStatusAndDiscardedAtIsNull(
                userId, sessionId, request.videoId(), FaceRegistrationStatus.REGISTERED)
            .orElse(null);
    StoredPhoto photo = photoRecords.attach(photoId, userId, sessionId);
    UUID oldPhotoId = null;
    if (old != null) {
      oldPhotoId = old.getPhotoId();
      old.discard(clock.instant());
      photoRecords.requestCleanupInCurrentTransaction(oldPhotoId);
      // 부분 유일 인덱스 때문에 새 INSERT보다 옛 등록 폐기 UPDATE를 먼저 보낸다.
      registrations.flush();
    }
    FaceRegistration registration =
        new FaceRegistration(
            photo,
            request.videoId(),
            request.guideId(),
            new FaceChecks(
                request.checks().lighting(),
                request.checks().distance(),
                request.checks().frontal(),
                request.checks().unobstructed(),
                request.checks().makeupDetected()),
            request.noticeVersion(),
            clock.instant());
    registrations.saveAndFlush(registration);
    return new Saved(FaceRegistrationResponse.from(registration, photo), oldPhotoId);
  }

  @Transactional(readOnly = true)
  public FaceRegistrationResponse get(UUID userId, String sessionId, UUID registrationId) {
    FaceRegistration registration =
        registrations
            .findByIdAndUserId(registrationId, userId)
            .orElseThrow(FaceRegistrationStore::notFound);
    requireSession(registration, sessionId);
    if (registration.getDiscardedAt() != null) {
      throw notFound();
    }
    StoredPhoto photo =
        photos
            .findByIdAndUserId(registration.getPhotoId(), userId)
            .filter(value -> value.getState() == PhotoState.AVAILABLE)
            .orElseThrow(FaceRegistrationStore::notFound);
    return FaceRegistrationResponse.from(registration, photo);
  }

  /** 폐기 상태도 삭제 실패 재시도에는 허용한다. 파일이 이미 삭제 완료면 404다. */
  @Transactional
  public UUID discard(UUID userId, String sessionId, UUID registrationId) {
    users.findByIdForUpdate(userId).orElseThrow(FaceRegistrationStore::notFound);
    FaceRegistration registration =
        registrations
            .findOwnedForUpdate(registrationId, userId)
            .orElseThrow(FaceRegistrationStore::notFound);
    requireSession(registration, sessionId);
    if (registration.getStatus() != FaceRegistrationStatus.REGISTERED) {
      throw new BusinessException(
          HttpStatus.CONFLICT,
          "FACE_REGISTRATION_IN_USE",
          "실행 또는 리포트에 연결된 얼굴 등록은 해당 실행·리포트에서 정리해야 합니다.");
    }
    StoredPhoto photo =
        photos
            .findByIdAndUserId(registration.getPhotoId(), userId)
            .orElseThrow(FaceRegistrationStore::notFound);
    if (photo.getState() == PhotoState.DELETED) {
      throw notFound();
    }
    registration.discard(clock.instant());
    photoRecords.requestCleanupInCurrentTransaction(registration.getPhotoId());
    return registration.getPhotoId();
  }

  private void requireSession(FaceRegistration registration, String sessionId) {
    if (registration.getStatus() != FaceRegistrationStatus.RETAINED
        && !registration.getSessionId().equals(sessionId)) {
      throw notFound();
    }
  }

  private static BusinessException notFound() {
    return new BusinessException(ErrorCode.NOT_FOUND);
  }

  public record Saved(FaceRegistrationResponse response, UUID replacedPhotoId) {}
}
