package com.mairor.backend.analysis.repository;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

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

  List<AnalysisJob> findByStatus(AnalysisStatus status);
}
