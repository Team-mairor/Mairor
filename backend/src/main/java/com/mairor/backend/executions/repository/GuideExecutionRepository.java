package com.mairor.backend.executions.repository;

import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.entity.GuideExecution;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface GuideExecutionRepository extends JpaRepository<GuideExecution, UUID> {
  Optional<GuideExecution> findByIdAndUserId(UUID id, UUID userId);

  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select e from GuideExecution e where e.id = :id and e.userId = :userId")
  Optional<GuideExecution> findOwnedForUpdate(@Param("id") UUID id, @Param("userId") UUID userId);

  /** 호출자는 회원 잠금을 먼저 잡는다. 같은 세션의 생성/종료는 이 잠금 규칙으로 직렬화한다. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  List<GuideExecution> findByUserIdAndSessionIdAndStatusOrderById(
      UUID userId, String sessionId, ExecutionStatus status);
}
