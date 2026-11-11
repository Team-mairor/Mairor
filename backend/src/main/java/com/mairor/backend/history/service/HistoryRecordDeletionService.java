package com.mairor.backend.history.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.history.entity.HistoryRecord;
import com.mairor.backend.history.repository.HistoryRecordRepository;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.photos.service.PhotoCleanupService;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 리포트 삭제(API-REPORT-003). 리포트와 그 단계 사진 · 완성 사진 · 보관 얼굴 등록 사진을 모두 지운 뒤에만 성공한다(S15P31A306-404).
 *
 * <p>순서: ① 리포트를 잠그고 그 사진들을 정리 대기로 바꿔 바로 읽지 못하게 한다 ② 사진마다 사진 정리 서비스(S15P31A306-396)로 저장소 파일을 지운다 ③
 * 모두 지워졌으면 리포트 행을 지운다. 파일 하나라도 못 지우면 503 이고 리포트는 남는다. 정리 대기 사진은 사진 정리 주기도 지우므로, 다시 요청하면 남은 것을 이어서
 * 지우고 다 지워졌으면 리포트를 지운다. 리포트에 삭제 상태 칸을 두지 않고 사진 상태로 진행을 이어 간다.
 *
 * <p>실행 · 얼굴 등록 행은 남긴다. 서로 FK 로 묶여 있고 사진 행은 DELETED 로 남으므로, 지워지는 것은 이미지 파일과 리포트다.
 */
@Service
public class HistoryRecordDeletionService {

  public static final String REPORT_DELETE_FAILED = "REPORT_DELETE_FAILED";

  private static final Logger log = LoggerFactory.getLogger(HistoryRecordDeletionService.class);

  private final HistoryRecordRepository records;
  private final StoredPhotoRepository photos;
  private final PhotoCleanupService photoCleanup;
  private final TransactionTemplate transactions;
  private final Clock clock;

  public HistoryRecordDeletionService(
      HistoryRecordRepository records,
      StoredPhotoRepository photos,
      PhotoCleanupService photoCleanup,
      TransactionTemplate transactions,
      Clock clock) {
    this.records = records;
    this.photos = photos;
    this.photoCleanup = photoCleanup;
    this.transactions = transactions;
    this.clock = clock;
  }

  /**
   * @throws BusinessException 404 {@code NOT_FOUND} — 없거나 다른 회원의 리포트(이미 지운 것 포함), 503 {@code
   *     REPORT_DELETE_FAILED} — 사진 파일을 다 지우지 못함(리포트는 남는다)
   */
  public void delete(UUID userId, UUID recordId) {
    List<UUID> photoIds = transactions.execute(status -> blockPhotos(userId, recordId));
    int remaining = 0;
    for (UUID photoId : photoIds) {
      if (!photoCleanup.cleanup(photoId)) {
        remaining++;
      }
    }
    if (remaining > 0) {
      log.warn("리포트 사진을 다 지우지 못함 recordId={} remaining={}", recordId, remaining);
      throw failed();
    }
    transactions.executeWithoutResult(status -> deleteRecord(userId, recordId, photoIds));
    log.info("리포트 삭제 recordId={} photos={}", recordId, photoIds.size());
  }

  private List<UUID> blockPhotos(UUID userId, UUID recordId) {
    HistoryRecord record = lock(userId, recordId);
    List<UUID> photoIds = records.findPhotoIds(record.getId(), record.getExecutionId());
    Instant now = clock.instant();
    for (UUID photoId : photoIds) {
      photos.findByIdForUpdate(photoId).ifPresent(photo -> photo.requestCleanup(now));
    }
    return photoIds;
  }

  private void deleteRecord(UUID userId, UUID recordId, List<UUID> photoIds) {
    HistoryRecord record = lock(userId, recordId);
    boolean allDeleted =
        photos.findAllById(photoIds).stream()
            .allMatch(photo -> photo.getState() == PhotoState.DELETED);
    if (!allDeleted) {
      throw failed();
    }
    records.delete(record);
  }

  private HistoryRecord lock(UUID userId, UUID recordId) {
    return records
        .findByIdAndUserIdForUpdate(recordId, userId)
        .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
  }

  private static BusinessException failed() {
    return new BusinessException(
        HttpStatus.SERVICE_UNAVAILABLE, REPORT_DELETE_FAILED, "리포트를 다 지우지 못했습니다. 잠시 후 다시 시도해 주세요.");
  }
}
