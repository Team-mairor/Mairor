package com.mairor.backend.common.security;

import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.stereotype.Component;

/**
 * 만료된 세션을 지운다. Spring Session JDBC 는 만료·삭제 이벤트를 발행하지 않고 정리 작업이 행을 지우기만 하므로, 유휴 만료로 끝나는 세션에 종료
 * 훅({@link SessionEndHook})을 호출할 방법이 없다. 그래서 Spring 의 정리 작업을 끄고(설정 {@code
 * spring.session.jdbc.cleanup-cron: "-"}) 이 클래스가 대신한다.
 *
 * <p>정리 순서: 만료된 행({@code EXPIRY_TIME < 지금}, Spring 의 정리와 같은 기준)을 조회한다 → 행마다 종료 훅을 호출한다({@link
 * SessionEndReason#IDLE_EXPIRED}) → 성공한 행만 지운다. 훅이 실패한 행은 <b>지우지 않고</b> 남겨 다시 시도한다. 세션은 이미 만료로 판정되어
 * 쓸 수 없으므로 남아 있어도 안전하다. 그래서 훅은 <b>최소 한 번</b> 호출된다(멱등이어야 한다). 서버가 여러 대면 같은 행에 훅이 두 번 불릴 수 있다.
 *
 * <p>실패하는 행이 뒤의 정상 행을 막지 않게, 실패한 행은 {@link SessionSweepProperties#retryDelay()} 동안 건너뛰고(조회 범위를 이어서
 * 넘긴다) 정상 행을 계속 처리한다. 건너뛴 행은 시도한 수에 세지 않는다. 한 번 실행에서 시도하는 행 수는 {@link
 * SessionSweepProperties#batchSize()} 로 제한한다.
 *
 * <p>로그인한 적 없는 세션(예: 로그인 화면에서 CSRF 토큰만 받은 익명 세션)은 주인이 없으므로 훅 없이 지운다.
 *
 * <p>만료 기준 시각은 Spring Session 이 쓰는 실제 시각이다. 서비스의 {@code Clock} 빈(테스트에서 옮겨지는 시계)과 섞지 않는다.
 */
@Component
public class ExpiredSessionSweeper {

  private static final Logger log = LoggerFactory.getLogger(ExpiredSessionSweeper.class);
  private static final Pattern TABLE_NAME = Pattern.compile("[A-Za-z_][A-Za-z0-9_]*");

  /** 정리 대상 행 하나. */
  private record Row(String sessionId, String principalName, long expiryTime) {}

  private final JdbcTemplate jdbc;
  private final FindByIndexNameSessionRepository<?> sessions;
  private final SessionEndNotifier sessionEnd;
  private final SessionMetrics metrics;
  private final SessionSweepProperties properties;
  private final Clock clock;
  private final String selectSql;

  /** 정리에 실패한 세션 ID → 이 시각(밀리초)까지는 건너뛴다. */
  private final Map<String, Long> retryAfter = new ConcurrentHashMap<>();

  @Autowired
  public ExpiredSessionSweeper(
      JdbcTemplate jdbc,
      FindByIndexNameSessionRepository<?> sessions,
      SessionEndNotifier sessionEnd,
      SessionMetrics metrics,
      SessionSweepProperties properties,
      @Value("${spring.session.jdbc.table-name:SPRING_SESSION}") String tableName) {
    this(jdbc, sessions, sessionEnd, metrics, properties, tableName, Clock.systemUTC());
  }

  ExpiredSessionSweeper(
      JdbcTemplate jdbc,
      FindByIndexNameSessionRepository<?> sessions,
      SessionEndNotifier sessionEnd,
      SessionMetrics metrics,
      SessionSweepProperties properties,
      String tableName,
      Clock clock) {
    if (!TABLE_NAME.matcher(tableName).matches()) {
      throw new IllegalArgumentException("세션 테이블 이름이 올바르지 않습니다: " + tableName);
    }
    this.jdbc = jdbc;
    this.sessions = sessions;
    this.sessionEnd = sessionEnd;
    this.metrics = metrics;
    this.properties = properties;
    this.clock = clock;
    this.selectSql =
        "select session_id, principal_name, expiry_time from "
            + tableName
            + " where expiry_time < ? and (expiry_time > ? or (expiry_time = ? and session_id > ?))"
            + " order by expiry_time, session_id limit ?";
  }

  /**
   * 만료된 세션을 한 번 정리한다.
   *
   * @return 지운 세션 수
   */
  public int sweep() {
    long now = clock.millis();
    retryAfter.values().removeIf(until -> until <= now);

    int attempted = 0;
    int removed = 0;
    long cursorExpiry = Long.MIN_VALUE;
    String cursorId = "";
    int pageSize = properties.batchSize();
    while (attempted < properties.batchSize()) {
      List<Row> page =
          jdbc.query(
              selectSql,
              (rs, i) ->
                  new Row(
                      rs.getString("session_id"),
                      rs.getString("principal_name"),
                      rs.getLong("expiry_time")),
              now,
              cursorExpiry,
              cursorExpiry,
              cursorId,
              pageSize);
      if (page.isEmpty()) {
        break;
      }
      for (Row row : page) {
        cursorExpiry = row.expiryTime();
        cursorId = row.sessionId();
        if (retryAfter.containsKey(row.sessionId())) {
          continue;
        }
        attempted++;
        if (end(row, now)) {
          removed++;
        }
        if (attempted >= properties.batchSize()) {
          break;
        }
      }
      if (page.size() < pageSize) {
        break;
      }
    }
    return removed;
  }

  private boolean end(Row row, long now) {
    try {
      if (row.principalName() != null && !row.principalName().isBlank()) {
        sessionEnd.strict(
            new SessionEnd(row.principalName(), row.sessionId(), SessionEndReason.IDLE_EXPIRED));
      }
      sessions.deleteById(row.sessionId());
      retryAfter.remove(row.sessionId());
      metrics.sweepRemoved();
      return true;
    } catch (RuntimeException e) {
      Duration delay = properties.retryDelay();
      retryAfter.put(row.sessionId(), now + delay.toMillis());
      metrics.sweepFailed();
      // 훅 실패의 스택은 알림 처리기가 이미 남겼다. 세션 ID 는 로그에 쓰지 않는다
      log.warn("만료된 세션을 정리하지 못했습니다. {} 뒤에 다시 시도합니다. 원인: {}", delay, e.getClass().getSimpleName());
      log.debug("만료된 세션 정리 실패 상세", e);
      return false;
    }
  }
}
