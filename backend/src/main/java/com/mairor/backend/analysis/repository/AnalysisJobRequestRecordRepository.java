package com.mairor.backend.analysis.repository;

import com.mairor.backend.analysis.entity.AnalysisJobRequestRecord;
import com.mairor.backend.analysis.service.ReceiptType;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AnalysisJobRequestRecordRepository
    extends JpaRepository<AnalysisJobRequestRecord, UUID> {

  /** 회원이 이 작업을 요청했거나 합류했는가. 조회 권한에 쓴다. */
  boolean existsByAnalysisJobIdAndUserId(UUID analysisJobId, UUID userId);

  /** 회원이 {@code since} 이후 남긴 요청 수. 일일 신규 분석 한도는 {@code NEW_JOB}만 센다. */
  long countByUserIdAndReceiptTypeAndCreatedAtGreaterThanEqual(
      UUID userId, ReceiptType receiptType, Instant since);
}
