package com.mairor.backend.history.repository;

import com.mairor.backend.history.entity.HistoryRecord;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface HistoryRecordRepository extends JpaRepository<HistoryRecord, UUID> {
  Optional<HistoryRecord> findByExecutionId(UUID executionId);

  /**
   * 회원의 리포트(API-REPORT-001). 완료 시각 최신순, 같으면 리포트 ID 내림차순. 인덱스 {@code
   * idx_history_records_owner_completed}.
   */
  @Query(
      "select r from HistoryRecord r where r.userId = :userId"
          + " order by r.completedAt desc, r.id desc")
  Slice<HistoryRecord> findPageByUserId(@Param("userId") UUID userId, Pageable pageable);

  /** 회원의 리포트 하나. 다른 회원 것은 없는 것과 같다(404). */
  Optional<HistoryRecord> findByIdAndUserId(UUID id, UUID userId);

  /** 삭제할 때 같은 리포트를 동시에 지우지 않게 잠근다. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select r from HistoryRecord r where r.id = :id and r.userId = :userId")
  Optional<HistoryRecord> findByIdAndUserIdForUpdate(
      @Param("id") UUID id, @Param("userId") UUID userId);

  /**
   * 리포트를 지울 때 함께 지울 사진(S15P31A306-404): 그 실행의 단계 사진, 보관(RETAINED) 얼굴 등록 사진, 완성 사진(보통 마지막 단계 사진과
   * 같다).
   */
  @Query(
      value =
          "select photo_id from execution_steps"
              + " where execution_id = :executionId and photo_id is not null"
              + " union"
              + " select photo_id from face_registrations"
              + " where execution_id = :executionId and status = 'RETAINED'"
              + " union"
              + " select completed_photo_id from history_records"
              + " where id = :recordId and completed_photo_id is not null",
      nativeQuery = true)
  List<UUID> findPhotoIds(@Param("recordId") UUID recordId, @Param("executionId") UUID executionId);
}
