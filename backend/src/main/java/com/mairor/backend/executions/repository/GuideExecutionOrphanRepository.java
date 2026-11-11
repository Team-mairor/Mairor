package com.mairor.backend.executions.repository;

import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** 세션 종료 훅이 실행되지 못한 뒤 세션 행까지 사라진 진행 실행을 찾는다. */
@Repository
public class GuideExecutionOrphanRepository {
  private final JdbcTemplate jdbc;
  private final String sessionTable;

  public GuideExecutionOrphanRepository(
      JdbcTemplate jdbc,
      @Value("${spring.session.jdbc.table-name:SPRING_SESSION}") String sessionTable) {
    if (sessionTable == null || !sessionTable.matches("[A-Za-z_][A-Za-z0-9_]*")) {
      throw new IllegalArgumentException("세션 테이블 이름이 올바르지 않습니다.");
    }
    this.jdbc = jdbc;
    this.sessionTable = sessionTable;
  }

  public List<OrphanExecution> findMissingSessions(int limit) {
    return jdbc.query(
        "select e.user_id, e.session_id from guide_executions e"
            + " where e.status = 'IN_PROGRESS'"
            + " and not exists (select 1 from "
            + sessionTable
            + " s where s.session_id = e.session_id)"
            + " order by e.created_at, e.id limit ?",
        (rs, row) ->
            new OrphanExecution(rs.getObject("user_id", UUID.class), rs.getString("session_id")),
        limit);
  }

  public record OrphanExecution(UUID userId, String sessionId) {}
}
