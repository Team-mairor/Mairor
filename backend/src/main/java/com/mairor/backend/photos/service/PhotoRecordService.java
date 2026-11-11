package com.mairor.backend.photos.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import java.time.Clock;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 파일 I/O와 별도로 커밋되는 업로드 원장. 도메인 연결은 호출자의 DB 트랜잭션에 참여한다. */
@Service
public class PhotoRecordService {
  private final StoredPhotoRepository photos;
  private final PhotoStorageProperties properties;
  private final Clock clock;

  public PhotoRecordService(
      StoredPhotoRepository photos, PhotoStorageProperties properties, Clock clock) {
    this.photos = photos;
    this.properties = properties;
    this.clock = clock;
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public UUID stage(
      UUID userId,
      String sessionId,
      PhotoKind kind,
      String stepId,
      String key,
      ValidatedPhoto file) {
    StoredPhoto photo =
        new StoredPhoto(
            userId,
            sessionId,
            kind,
            stepId,
            key,
            file.contentType(),
            file.byteSize(),
            file.width(),
            file.height(),
            clock.instant().plus(properties.stagingTimeout()));
    return photos.saveAndFlush(photo).getId();
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void requestCleanup(UUID photoId) {
    photos.findByIdForUpdate(photoId).ifPresent(photo -> photo.requestCleanup(clock.instant()));
  }

  /** 재촬영/삭제 도메인 상태 변경과 함께 커밋한다. 파일 정리는 커밋 이후에만 시도한다. */
  @Transactional(propagation = Propagation.MANDATORY)
  public void requestCleanupInCurrentTransaction(UUID photoId) {
    photos.findByIdForUpdate(photoId).ifPresent(photo -> photo.requestCleanup(clock.instant()));
  }

  /** 얼굴 등록/실행 저장과 같은 트랜잭션에서만 호출한다. 실패/롤백 시 임시 만료 시각이 남는다. */
  @Transactional(propagation = Propagation.MANDATORY)
  public StoredPhoto attach(UUID photoId, UUID userId, String sessionId) {
    StoredPhoto photo =
        photos
            .findByIdForUpdate(photoId)
            .filter(
                value -> value.getUserId().equals(userId) && value.getSessionId().equals(sessionId))
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    if (photo.getState() != PhotoState.AVAILABLE
        || photo.getExpiresAt() == null
        || !photo.getExpiresAt().isAfter(clock.instant())) {
      throw new BusinessException(ErrorCode.NOT_FOUND);
    }
    photo.markAttached();
    return photo;
  }
}
