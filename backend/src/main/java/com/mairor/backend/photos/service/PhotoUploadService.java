package com.mairor.backend.photos.service;

import com.mairor.backend.photos.entity.PhotoKind;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/** 저장 뒤 도메인 연결이 실패하면 discard를 호출한다. 프로세스 중단은 만료 원장 정리가 복구한다. */
@Service
public class PhotoUploadService {
  private final PhotoFileValidator validator;
  private final PhotoRecordService records;
  private final PhotoTransferService transfers;
  private final PhotoCleanupService cleanup;

  public PhotoUploadService(
      PhotoFileValidator validator,
      PhotoRecordService records,
      PhotoTransferService transfers,
      PhotoCleanupService cleanup) {
    this.validator = validator;
    this.records = records;
    this.transfers = transfers;
    this.cleanup = cleanup;
  }

  @Transactional(propagation = Propagation.NEVER)
  public UUID store(
      UUID userId, String sessionId, PhotoKind kind, String stepId, MultipartFile upload) {
    try (ValidatedPhoto file = validator.validate(upload)) {
      UUID photoId =
          records.stage(userId, sessionId, kind, stepId, "photos/" + UUID.randomUUID(), file);
      try {
        transfers.upload(photoId, file.path());
        return photoId;
      } catch (RuntimeException failure) {
        try {
          discard(photoId);
        } catch (RuntimeException compensation) {
          // 원장이 먼저 커밋됐으므로 DB 장애로 보상 예약이 실패해도 stagingTimeout 이후 정리된다.
          failure.addSuppressed(compensation);
        }
        throw failure;
      }
    }
  }

  @Transactional(propagation = Propagation.NEVER)
  public boolean discard(UUID photoId) {
    records.requestCleanup(photoId);
    return cleanup.cleanup(photoId);
  }
}
