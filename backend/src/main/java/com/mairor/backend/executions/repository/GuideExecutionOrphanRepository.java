package com.mairor.backend.executions.repository;

import com.mairor.backend.common.security.SessionLookup;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.session.Session;
import org.springframework.stereotype.Repository;

/** Finds in-progress executions whose owning login session no longer exists. */
@Repository
public class GuideExecutionOrphanRepository {

  private final JdbcTemplate jdbc;

  /** 한 번에 읽는 후보 페이지 수 상한. 세션이 살아 있는 후보가 대부분이어도 한 주기에 표 전체를 훑지 않는다. */
  static final int MAX_PAGES_PER_SWEEP = 10;

  private final SessionLookup sessions;

  /** 다음 주기가 이어서 읽을 위치. 끝까지 읽으면 처음으로 돌아가 모든 후보를 차례로 확인한다. */
  private final AtomicInteger cursor = new AtomicInteger();

  public GuideExecutionOrphanRepository(JdbcTemplate jdbc, SessionLookup sessions) {
    this.jdbc = jdbc;
    this.sessions = sessions;
  }

  public List<OrphanExecution> findMissingSessions(int limit) {
    if (limit < 1) {
      return List.of();
    }
    int pageSize = Math.max(limit, 100);
    int offset = cursor.get();
    int pages = 0;
    List<OrphanExecution> missing = new ArrayList<>();
    Map<UUID, Set<String>> activeSessionsByUser = new HashMap<>();
    while (missing.size() < limit) {
      List<OrphanExecution> candidates =
          jdbc.query(
              "select e.user_id, e.session_id from guide_executions e"
                  + " where e.status = 'IN_PROGRESS'"
                  + " order by e.created_at, e.id limit ? offset ?",
              (rs, row) ->
                  new OrphanExecution(
                      rs.getObject("user_id", UUID.class), rs.getString("session_id")),
              pageSize,
              offset);
      if (candidates.isEmpty()) {
        offset = 0;
        break;
      }
      int scanned = 0;
      for (OrphanExecution candidate : candidates) {
        scanned++;
        Set<String> activeIds =
            activeSessionsByUser.computeIfAbsent(candidate.userId(), this::activeSessionIdsFor);
        if (!activeIds.contains(candidate.sessionId())) {
          missing.add(candidate);
          if (missing.size() == limit) {
            break;
          }
        }
      }
      // limit 을 채워 페이지 중간에 멈췄으면 실제로 확인한 후보까지만 넘긴다. 남은 후보는 다음 주기가 확인한다
      offset += scanned;
      pages++;
      if (scanned == candidates.size() && candidates.size() < pageSize) {
        offset = 0;
        break;
      }
      if (pages == MAX_PAGES_PER_SWEEP) {
        break;
      }
    }
    // 이번에 찾은 고아는 호출한 쪽이 정리해 다음 조회 결과에서 빠지므로, 그만큼 위치를 당겨야 남은 후보를 건너뛰지 않는다
    cursor.set(offset == 0 ? 0 : Math.max(0, offset - missing.size()));
    return missing;
  }

  private Set<String> activeSessionIdsFor(UUID userId) {
    Set<String> ids = new HashSet<>();
    // 값을 읽을 수 없는 세션은 다시 쓸 수 없으므로 살아 있는 세션으로 치지 않는다
    for (Map.Entry<String, Session> entry : sessions.byPrincipal(userId.toString()).entrySet()) {
      if (entry.getValue() != null && !entry.getValue().isExpired()) {
        ids.add(entry.getKey());
      }
    }
    return ids;
  }

  public record OrphanExecution(UUID userId, String sessionId) {}
}
