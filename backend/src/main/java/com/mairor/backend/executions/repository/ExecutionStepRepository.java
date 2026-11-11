package com.mairor.backend.executions.repository;

import com.mairor.backend.executions.entity.ExecutionStep;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ExecutionStepRepository extends JpaRepository<ExecutionStep, UUID> {
  List<ExecutionStep> findByExecutionIdOrderByPosition(UUID executionId);

  Optional<ExecutionStep> findByExecutionIdAndStepId(UUID executionId, String stepId);

  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query(
      "select step from ExecutionStep step where step.executionId = :executionId and step.stepId = :stepId")
  Optional<ExecutionStep> findByExecutionIdAndStepIdForUpdate(
      @Param("executionId") UUID executionId, @Param("stepId") String stepId);

  Optional<ExecutionStep> findByPhotoId(UUID photoId);
}
