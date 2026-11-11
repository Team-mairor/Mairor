package com.mairor.backend.photos.service;

import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PhotoCleanupService {
  private static final Logger log = LoggerFactory.getLogger(PhotoCleanupService.class);
  private final PhotoCleanupMetrics metrics;
  private final StoredPhotoRepository photos;
  private final ObjectStorage storage;
  private final PhotoStorageProperties properties;
  private final Clock clock;

  public PhotoCleanupService(
      StoredPhotoRepository photos,
      ObjectStorage storage,
      PhotoStorageProperties properties,
      Clock clock,
      PhotoCleanupMetrics metrics) {
    this.photos = photos;
    this.storage = storage;
    this.properties = properties;
    this.clock = clock;
    this.metrics = metrics;
  }

  /** 업로드/도메인 연결 중인 행은 기다리지 않고 다음 주기에 처리한다. */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public boolean cleanup(UUID photoId) {
    Optional<StoredPhoto> found = photos.findByIdForCleanup(photoId);
    if (found.isEmpty()) {
      return false;
    }
    StoredPhoto photo = found.orElseThrow();
    if (photo.getState() == PhotoState.DELETED) {
      return true;
    }
    Instant now = clock.instant();
    if (photo.getState() != PhotoState.CLEANUP_PENDING) {
      if (photo.getExpiresAt() == null || photo.getExpiresAt().isAfter(now)) {
        return false;
      }
      photo.requestCleanup(now);
    }
    if (photo.getNextCleanupAt().isAfter(now)) {
      return false;
    }
    try {
      storage.delete(photo.getStorageKey());
      photo.markDeleted(now);
      return true;
    } catch (StorageException e) {
      photo.recordCleanupFailure(now.plus(properties.cleanupRetryDelay()));
      metrics.failed();
      log.warn(
          "사진 저장소 삭제 실패 photoId={} attempts={}. 권한과 저장소 상태를 확인한다",
          photoId,
          photo.getCleanupAttempts());
      return false;
    }
  }
}
