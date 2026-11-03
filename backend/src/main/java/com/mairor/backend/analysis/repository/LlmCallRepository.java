package com.mairor.backend.analysis.repository;

import com.mairor.backend.analysis.entity.LlmCall;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LlmCallRepository extends JpaRepository<LlmCall, UUID> {

  List<LlmCall> findByAnalysisJobIdOrderByCreatedAtAsc(UUID analysisJobId);
}
