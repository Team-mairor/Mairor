package com.mairor.backend.testsupport;

import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 만료된 세션 정리를 검증하는 테스트용 훅. {@link RecordingSessionEndHook} 은 호출 시점에 세션이 있었는지를 {@code findById} 로
 * 확인하는데, 만료된 세션에 대한 {@code findById} 는 Spring Session 이 그 행을 지워 버린다(부작용). 그래서 이 훅은 SQL 로 행이 있는지만
 * 센다.
 */
public class SweepProbeHook implements SessionEndHook {

  /** 기록된 호출 하나. {@code rowExisted} 는 호출 시점에 세션 행이 DB 에 있었는지. */
  public record Probe(SessionEnd end, boolean rowExisted) {}

  public final List<Probe> calls = new CopyOnWriteArrayList<>();
  public final Set<String> failingSessionIds = ConcurrentHashMap.newKeySet();
  private final JdbcTemplate jdbc;

  public SweepProbeHook(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  @Override
  public void beforeSessionEnds(SessionEnd end) {
    Integer rows =
        jdbc.queryForObject(
            "select count(*) from spring_session where session_id = ?",
            Integer.class,
            end.sessionId());
    calls.add(new Probe(end, rows != null && rows > 0));
    if (failingSessionIds.contains(end.sessionId())) {
      throw new IllegalStateException("정리 실패(테스트가 주입)");
    }
  }

  public void reset() {
    calls.clear();
    failingSessionIds.clear();
  }
}
