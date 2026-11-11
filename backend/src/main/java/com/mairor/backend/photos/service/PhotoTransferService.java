package com.mairor.backend.photos.service;

import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import java.nio.file.Path;
import java.time.Clock;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 작은 업로드 동안 사진 행 하나만 잠가 정리 작업과 업로드가 엇갈리지 않게 한다. */
@Service
public class PhotoTransferService {
  private final StoredPhotoRepository photos;
  private final ObjectStorage storage;
  private final Clock clock;

  public PhotoTransferService(StoredPhotoRepository photos, ObjectStorage storage, Clock clock) {
    this.photos = photos;
    this.storage = storage;
    this.clock = clock;
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void upload(UUID photoId, Path source) {
    StoredPhoto photo = photos.findByIdForUpdate(photoId).orElseThrow();
    if (photo.getState() != PhotoState.PENDING_UPLOAD
        || photo.getExpiresAt() == null
        || !photo.getExpiresAt().isAfter(clock.instant())) {
      throw new StorageException("사진 업로드 대기 상태가 만료됐습니다", null);
    }
    storage.upload(source, photo.getStorageKey(), photo.getContentType());
    photo.markAvailable();
    photos.flush();
  }
}
