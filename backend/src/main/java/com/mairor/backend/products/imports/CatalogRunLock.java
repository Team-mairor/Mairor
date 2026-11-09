package com.mairor.backend.products.imports;

import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * 적재 실행 하나에 대한 트랜잭션 단위 잠금. 건 처리는 **공유 잠금**, 실행을 끝내는 쪽(끝내기·끊긴 실행 정리)은 **배타 잠금**을 잡는다.
 *
 * <p>그래서 진행 중인 건이 모두 확정된 뒤에야 실행이 끝나고, 실행이 끝난 뒤에 시작한 건은 끝난 실행의 상태를 보고 거절된다. 건끼리는 서로 막지 않는다. 반드시 트랜잭션
 * 안에서 불러야 하며 잠금은 트랜잭션이 끝날 때 풀린다.
 */
@Component
class CatalogRunLock {

  private final JdbcTemplate jdbc;

  CatalogRunLock(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  /** 건 처리용. 같은 실행의 다른 건과는 함께 잡을 수 있고, 배타 잠금과는 함께 잡을 수 없다. */
  void shared(UUID runId) {
    jdbc.queryForList("select pg_advisory_xact_lock_shared(hashtextextended(?, 0))", key(runId));
  }

  /** 실행을 끝내는 쪽용. 진행 중인 건이 모두 끝날 때까지 기다리고, 그동안 새 건 처리를 막는다. */
  void exclusive(UUID runId) {
    jdbc.queryForList("select pg_advisory_xact_lock(hashtextextended(?, 0))", key(runId));
  }

  private static String key(UUID runId) {
    return "catalog-import-run:" + runId;
  }
}
