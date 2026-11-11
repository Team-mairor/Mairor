package com.mairor.backend.executions.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.storage.ObjectNotFoundException;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.photos.dto.PhotoResponse;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.photos.service.PhotoCleanupService;
import com.mairor.backend.photos.service.PhotoRecordService;
import com.mairor.backend.photos.service.PhotoTemporaryFiles;
import com.mairor.backend.photos.service.PhotoUploadService;
import java.io.IOException;
import java.nio.file.Files;
import java.time.Clock;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/** 실행 사진 동의와 단계 사진 연결. 객체 저장소 I/O는 DB 트랜잭션 밖에서 수행한다. */
@Service
public class ExecutionPhotoService {
  public static final String POLICY_VERSION = "v1";
  private final ExecutionPhotoPersistenceService persistence;
  private final StoredPhotoRepository photos;
  private final PhotoUploadService uploads;
  private final PhotoRecordService records;
  private final PhotoCleanupService cleanup;
  private final ObjectStorage storage;
  private final PhotoTemporaryFiles temporaryFiles;
  private final Clock clock;

  public ExecutionPhotoService(
      ExecutionPhotoPersistenceService persistence,
      StoredPhotoRepository photos,
      PhotoUploadService uploads,
      PhotoRecordService records,
      PhotoCleanupService cleanup,
      ObjectStorage storage,
      PhotoTemporaryFiles temporaryFiles,
      Clock clock) {
    this.persistence = persistence;
    this.photos = photos;
    this.uploads = uploads;
    this.records = records;
    this.cleanup = cleanup;
    this.storage = storage;
    this.temporaryFiles = temporaryFiles;
    this.clock = clock;
  }

  public com.mairor.backend.executions.dto.PhotoConsentResponse setConsent(
      UUID userId, String sessionId, UUID executionId, boolean enabled) {
    return persistence.setConsent(userId, sessionId, executionId, enabled, POLICY_VERSION);
  }

  @Transactional(propagation = Propagation.NEVER)
  public PhotoResponse upload(
      UUID userId, String sessionId, UUID executionId, String stepId, MultipartFile image) {
    persistence.validateUpload(userId, sessionId, executionId, stepId);
    UUID photoId;
    try {
      photoId = uploads.store(userId, sessionId, PhotoKind.STEP, stepId, image);
    } catch (StorageException failure) {
      throw unavailable();
    }
    UUID oldPhotoId;
    try {
      oldPhotoId = persistence.attach(userId, sessionId, executionId, stepId, photoId);
    } catch (RuntimeException failure) {
      try {
        uploads.discard(photoId);
      } catch (RuntimeException cleanupFailure) {
        failure.addSuppressed(cleanupFailure);
      }
      throw failure;
    }
    if (oldPhotoId != null) {
      try {
        records.requestCleanup(oldPhotoId);
        cleanup.cleanup(oldPhotoId);
      } catch (RuntimeException ignored) {
        // 이전 파일은 이미 참조가 끊겼다. cleanup scheduler가 재시도한다.
      }
    }
    return photos.findById(photoId).map(PhotoResponse::from).orElseThrow();
  }

  public PhotoContent get(UUID userId, String sessionId, UUID photoId) {
    var photo = persistence.getDownload(userId, sessionId, photoId);
    try (var lease = temporaryFiles.create()) {
      storage.download(photo.storageKey(), lease.path());
      byte[] bytes = Files.readAllBytes(lease.path());
      return new PhotoContent(photo.contentType(), bytes);
    } catch (IOException | ObjectNotFoundException | StorageException failure) {
      throw unavailable();
    }
  }

  private BusinessException unavailable() {
    return new BusinessException(ErrorCode.SERVICE_UNAVAILABLE, "사진 저장소를 처리하지 못했습니다.");
  }

  public record PhotoContent(String contentType, byte[] bytes) {}
}
