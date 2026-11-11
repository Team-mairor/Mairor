package com.mairor.backend.analysis.repository;

import com.mairor.backend.analysis.entity.AnalysisJobRequestRecord;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.service.AnalysisJobSummaryView;
import com.mairor.backend.analysis.service.ReceiptType;
import com.mairor.backend.guides.entity.ReviewStatus;
import java.time.Instant;
import java.util.Collection;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AnalysisJobRequestRecordRepository
    extends JpaRepository<AnalysisJobRequestRecord, UUID> {

  /** 회원이 이 작업을 요청했거나 합류했는가. 조회 권한에 쓴다. */
  boolean existsByAnalysisJobIdAndUserId(UUID analysisJobId, UUID userId);

  /** 회원이 {@code since} 이후 남긴 요청 수. 일일 신규 분석 한도는 {@code NEW_JOB}만 센다. */
  long countByUserIdAndReceiptTypeAndCreatedAtGreaterThanEqual(
      UUID userId, ReceiptType receiptType, Instant since);

  /**
   * 회원이 요청하거나 합류한 작업 중 작업 상태가 {@code status}이고 가이드 검수 상태가 {@code reviewStatuses}인 것(내 분석 목록). 회원이
   * 요청 · 합류한 시각의 최신순이고, 같은 시각이면 요청 기록 ID 로 순서를 고정한다.
   */
  @Query(
      """
      select new com.mairor.backend.analysis.service.AnalysisJobSummaryView(
          j.id, v.id, v.youtubeVideoId, v.title, v.thumbnailUrl,
          g.reviewStatus, g.id, r.createdAt, g.reviewedAt)
      from AnalysisJobRequestRecord r
      join AnalysisJob j on j.id = r.analysisJobId
      join j.video v
      join Guide g on g.analysisJob = j
      where r.userId = :userId
        and j.status = :status
        and g.reviewStatus in :reviewStatuses
      order by r.createdAt desc, r.id desc
      """)
  Slice<AnalysisJobSummaryView> findSummaries(
      @Param("userId") UUID userId,
      @Param("status") AnalysisStatus status,
      @Param("reviewStatuses") Collection<ReviewStatus> reviewStatuses,
      Pageable pageable);
}
