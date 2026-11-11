package com.mairor.backend.history.repository;

import com.mairor.backend.history.entity.HistoryRecord;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface HistoryRecordRepository extends JpaRepository<HistoryRecord, UUID> {
  Optional<HistoryRecord> findByExecutionId(UUID executionId);
}
