package com.mairor.backend.camera.repository;

import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** 종료 훅 누락/프로세스 중단으로 실제 세션이 사라진 미연결 등록만 찾는다. */
@Repository
public class FaceRegistrationOrphanRepository {
  private final JdbcTemplate jdbc;
  private final String tableName;

  public FaceRegistrationOrphanRepository(
      JdbcTemplate jdbc,
      @Value("${spring.session.jdbc.table-name:SPRING_SESSION}") String tableName) {
    if (tableName == null || !tableName.matches("[A-Za-z_][A-Za-z0-9_]*")) {
      throw new IllegalArgumentException("세션 테이블 이름이 올바르지 않다");
    }
    this.jdbc = jdbc;
    this.tableName = tableName;
  }

  public List<Orphan> findMissingSessions(int limit) {
    return jdbc.query(
        "select r.id, r.user_id from face_registrations r"
            + " where r.status = 'REGISTERED' and r.discarded_at is null"
            + " and not exists (select 1 from "
            + tableName
            + " s where s.session_id = r.session_id)"
            + " order by r.created_at, r.id limit ?",
        (rs, row) ->
            new Orphan(rs.getObject("id", UUID.class), rs.getObject("user_id", UUID.class)),
        limit);
  }

  public boolean sessionExists(String sessionId) {
    return Boolean.TRUE.equals(
        jdbc.queryForObject(
            "select exists (select 1 from " + tableName + " where session_id = ?)",
            Boolean.class,
            sessionId));
  }

  public record Orphan(UUID registrationId, UUID userId) {}
}
