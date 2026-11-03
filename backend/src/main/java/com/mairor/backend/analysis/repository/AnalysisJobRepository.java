package com.mairor.backend.analysis.repository;

import com.mairor.backend.analysis.entity.AnalysisJob;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AnalysisJobRepository extends JpaRepository<AnalysisJob, UUID> {

  /** AI 서버가 돌려준 가이드 생성 작업 ID 로 찾는다. 콜백 처리에 쓴다. */
  Optional<AnalysisJob> findByAiJobId(String aiJobId);
}
