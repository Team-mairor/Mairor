package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.CatalogImportRun;
import com.mairor.backend.products.entity.ImportRunStatus;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface CatalogImportRunRepository extends JpaRepository<CatalogImportRun, UUID> {

  /** 수집기가 header 에 쓴 runId 로 실행을 찾는다. 끊긴 실행을 이어서 보낼 때 같은 행을 쓴다. */
  Optional<CatalogImportRun> findByRunId(String runId);

  /**
   * 진행 중인 실행의 하트비트를 갱신한다. 이미 끝났으면 갱신하지 않는다(0건).
   *
   * <p>조건부 갱신이라 다른 쪽이 먼저 끝낸 실행을 되살리지 못한다. 엔티티를 읽어 고쳐 쓰면 읽은 뒤에 끝난 실행의 상태를 {@code RUNNING}으로 덮어쓸 수
   * 있다.
   */
  @Transactional
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      "update CatalogImportRun r set r.lastHeartbeatAt = :now, r.updatedAt = :now"
          + " where r.id = :id and r.status = com.mairor.backend.products.entity.ImportRunStatus.RUNNING")
  int touchIfRunning(@Param("id") UUID id, @Param("now") Instant now);

  /** 진행 중인 실행을 끝낸다. 이미 끝났으면 바꾸지 않는다(0건). */
  @Transactional
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      "update CatalogImportRun r set r.status = :status, r.finishedAt = :now, r.updatedAt = :now"
          + " where r.id = :id and r.status = com.mairor.backend.products.entity.ImportRunStatus.RUNNING")
  int finishIfRunning(
      @Param("id") UUID id, @Param("status") ImportRunStatus status, @Param("now") Instant now);

  /** 마지막 하트비트가 {@code cutoff}보다 오래된 진행 중 실행의 id. */
  @Query(
      "select r.id from CatalogImportRun r"
          + " where r.status = com.mairor.backend.products.entity.ImportRunStatus.RUNNING"
          + " and r.lastHeartbeatAt < :cutoff")
  List<UUID> findStaleIds(@Param("cutoff") Instant cutoff);

  /** 하트비트가 {@code cutoff}보다 오래된 진행 중 실행 하나를 {@code ABANDONED}로 끝낸다. 조건이 맞지 않으면 바꾸지 않는다(0건). */
  @Transactional
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      "update CatalogImportRun r set r.status = com.mairor.backend.products.entity.ImportRunStatus.ABANDONED,"
          + " r.finishedAt = :now, r.updatedAt = :now"
          + " where r.id = :id and r.status = com.mairor.backend.products.entity.ImportRunStatus.RUNNING"
          + " and r.lastHeartbeatAt < :cutoff")
  int abandonIfStale(
      @Param("id") UUID id, @Param("cutoff") Instant cutoff, @Param("now") Instant now);
}
