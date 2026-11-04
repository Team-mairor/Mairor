package com.mairor.backend.pouch.repository;

import java.util.List;
import java.util.OptionalLong;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** JPA 엔티티 캐시를 거치지 않고 회원 버전을 읽고 갱신한다. */
@Repository
public class PouchVersionRepository {

  private final JdbcTemplate jdbc;

  public PouchVersionRepository(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  public OptionalLong findByUserId(UUID userId) {
    return read("select pouch_version from users where id = ?", userId);
  }

  /** 파우치 쓰기는 이 회원 행을 먼저 잠근 뒤 개인 항목을 조회한다. 잠금은 호출자 트랜잭션 끝까지 유지된다. */
  @Transactional(propagation = Propagation.MANDATORY)
  public OptionalLong lockByUserId(UUID userId) {
    return read("select pouch_version from users where id = ? for update", userId);
  }

  /** 회원 잠금·항목 저장과 같은 트랜잭션에서 호출한다. JPA flush는 호출자가 먼저 수행한다. */
  @Transactional(propagation = Propagation.MANDATORY)
  public long increment(UUID userId) {
    return jdbc.queryForObject(
        "update users set pouch_version = pouch_version + 1 where id = ? returning pouch_version",
        Long.class,
        userId);
  }

  private OptionalLong read(String sql, UUID userId) {
    List<Long> values = jdbc.query(sql, (rs, row) -> rs.getLong(1), userId);
    return values.isEmpty() ? OptionalLong.empty() : OptionalLong.of(values.getFirst());
  }
}
