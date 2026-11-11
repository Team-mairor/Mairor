package com.mairor.backend.analysis.repository;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AnalysisJobRepository extends JpaRepository<AnalysisJob, UUID> {

  /** AI 서버가 돌려준 가이드 생성 작업 ID 로 찾는다. 콜백 처리에 쓴다. */
  Optional<AnalysisJob> findByAiJobId(String aiJobId);

  /** 영상의 진행 중(PENDING·RUNNING) 작업. {@code uk_analysis_jobs_video_active}가 많아야 하나임을 보장한다. */
  Optional<AnalysisJob> findFirstByVideoIdAndStatusIn(
      UUID videoId, Collection<AnalysisStatus> statuses);

  /**
   * 가장 오래 기다린 PENDING 작업 하나를 행 잠금과 함께 집는다. 다른 트랜잭션이 잠근 행은 건너뛰므로(SKIP LOCKED) worker 가 겹쳐 떠도 같은 작업을
   * 두 번 집지 않는다. 호출하는 트랜잭션 안에서 바로 RUNNING 으로 바꿔야 한다.
   */
  @Query(
      value =
          "select * from analysis_jobs where status = 'PENDING'"
              + " order by created_at, id limit 1 for update skip locked",
      nativeQuery = true)
  Optional<AnalysisJob> lockNextPending();

  /**
   * 노트북이 가져갈 작업 하나: 가장 오래 기다린 PENDING, 또는 노트북 임대가 지난 RUNNING. 다른 트랜잭션이 잠근 행은 건너뛴다. 호출하는 트랜잭션 안에서 바로
   * 임대를 걸어야 한다(S15P31A306-357).
   */
  @Query(
      value =
          "select * from analysis_jobs"
              + " where status = 'PENDING'"
              + " or (status = 'RUNNING' and processor_lease_until <= :now)"
              + " order by created_at, id limit 1 for update skip locked",
      nativeQuery = true)
  Optional<AnalysisJob> lockNextForProcessor(@Param("now") Instant now);

  /** 노트북이 끝냈다고 알렸고 아직 AI 에 맡기지 않은 작업 하나(가장 오래된 것). S15P31A306-358. */
  Optional<AnalysisJob>
      findFirstByStatusAndProcessorRequestKeyIsNotNullAndAiJobIdIsNullOrderByUpdatedAtAsc(
          AnalysisStatus status);

  /**
   * 노트북을 너무 오래 기다린 작업: {@code before} 전에 만들어졌는데 아무도 가져가지 않은 PENDING, 또는 임대가 {@code before} 전에 끝났는데
   * 아무도 다시 가져가지 않은 RUNNING. S15P31A306-358. 노트북이 일하는 중인지는 {@link #existsTouchedByProcessorSince}로
   * 따로 본다.
   */
  @Query(
      value =
          "select id from analysis_jobs"
              + " where (status = 'PENDING' and created_at < :before)"
              + " or (status = 'RUNNING' and processor_lease_until < :before)",
      nativeQuery = true)
  List<UUID> findIdsWaitingForProcessorSince(@Param("before") Instant before);

  /**
   * 노트북이 {@code since} 뒤로 만진(가져감 · 진행 알림 · 완료) 작업이 있는가. 노트북은 한 번에 하나씩 처리하므로, 일하는 동안 줄 선 작업은 차례를
   * 기다리는 것이지 노트북이 꺼진 것이 아니다(S15P31A306-408). 완료 뒤 AI 진행 알림도 {@code updated_at}을 바꾸므로 노트북이 꺼진 것은 그만큼
   * 늦게 알아챈다.
   */
  @Query(
      value =
          "select exists(select 1 from analysis_jobs"
              + " where processor_claims > 0 and updated_at >= :since)",
      nativeQuery = true)
  boolean existsTouchedByProcessorSince(@Param("since") Instant since);

  /** 행을 잠그고 찾는다. 노트북 알림(완료 · 실패 · 진행)이 임대 다시 내주기와 겹치지 않게 한다. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select j from AnalysisJob j where j.id = :id")
  Optional<AnalysisJob> lockById(@Param("id") UUID id);

  List<AnalysisJob> findByStatus(AnalysisStatus status);

  /** worker 재시작 때 되돌릴 작업: RUNNING 이면서 AI 에 맡기기 전인 것. */
  List<AnalysisJob> findByStatusAndAiJobIdIsNull(AnalysisStatus status);

  /**
   * AI 콜백을 기다리는 작업({@code status}·AI 작업 ID 있음) 중 AI 에 맡긴 시각이 {@code before} 보다 앞선 것. 진행 숫자를 저장하면
   * {@code updated_at}이 바뀌므로 맡긴 시각으로 본다. 맡긴 시각이 빈 행(칸이 생기기 전에 맡김)은 {@code updated_at}으로 본다({@link
   * AnalysisJob#aiTimeoutBaseline()}과 같은 규칙).
   */
  @Query(
      "select j from AnalysisJob j where j.status = :status and j.aiJobId is not null"
          + " and coalesce(j.aiRequestedAt, j.updatedAt) < :before")
  List<AnalysisJob> findAwaitingAiRequestedBefore(
      @Param("status") AnalysisStatus status, @Param("before") Instant before);

  /** 콜백과 시간 초과 감시가 같은 작업을 동시에 끝내지 않게 행을 잠그고 찾는다. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select j from AnalysisJob j where j.aiJobId = :aiJobId")
  Optional<AnalysisJob> lockByAiJobId(@Param("aiJobId") String aiJobId);
}
