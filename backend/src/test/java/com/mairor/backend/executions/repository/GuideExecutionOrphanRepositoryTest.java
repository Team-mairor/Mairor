package com.mairor.backend.executions.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.security.SessionLookup;
import com.mairor.backend.executions.repository.GuideExecutionOrphanRepository.OrphanExecution;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.session.MapSession;
import org.springframework.session.Session;

/**
 * 고아 실행 찾기는 한 주기에 읽는 양을 제한하고 다음 주기가 이어서 읽는다. 찾은 고아는 호출한 쪽이 정리해 다음 조회에서 빠지므로, 여러 주기에 걸쳐도 남은 후보를 건너뛰지
 * 않아야 한다.
 */
class GuideExecutionOrphanRepositoryTest {

  private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
  private final SessionLookup sessions = mock(SessionLookup.class);
  private final GuideExecutionOrphanRepository repository =
      new GuideExecutionOrphanRepository(jdbc, sessions);

  /** 진행 중인 실행(정렬된 상태). 고아로 찾아 정리하면 여기서 빠진다. */
  private final List<OrphanExecution> inProgress = new ArrayList<>();

  private final Map<UUID, String> liveSessionOf = new HashMap<>();

  @BeforeEach
  @SuppressWarnings("unchecked")
  void setUp() {
    when(jdbc.query(anyString(), any(RowMapper.class), any(), any()))
        .thenAnswer(
            call -> {
              int limit = call.getArgument(2);
              int offset = call.getArgument(3);
              int from = Math.min(offset, inProgress.size());
              return List.copyOf(
                  inProgress.subList(from, Math.min(from + limit, inProgress.size())));
            });
    when(sessions.byPrincipal(anyString()))
        .thenAnswer(
            call -> {
              String live = liveSessionOf.get(UUID.fromString(call.getArgument(0)));
              if (live == null) {
                return Map.<String, Session>of();
              }
              MapSession session = new MapSession(live);
              session.setMaxInactiveInterval(Duration.ofDays(3));
              session.setLastAccessedTime(Instant.now());
              return Map.<String, Session>of(live, session);
            });
  }

  /** 실행 {@code count} 개 중 {@code orphans} 번째만 세션이 끝났다. */
  private Set<String> executions(int count, Set<Integer> orphans) {
    Set<String> orphanSessions = new HashSet<>();
    for (int i = 0; i < count; i++) {
      UUID user = UUID.randomUUID();
      String session = "session-" + i;
      inProgress.add(new OrphanExecution(user, session));
      if (orphans.contains(i)) {
        orphanSessions.add(session);
      } else {
        liveSessionOf.put(user, session);
      }
    }
    return orphanSessions;
  }

  /** 한 주기: 고아를 찾고, 호출한 쪽처럼 정리해 진행 중 목록에서 뺀다. */
  private List<String> sweep(int limit) {
    List<OrphanExecution> found = repository.findMissingSessions(limit);
    inProgress.removeAll(found);
    return found.stream().map(OrphanExecution::sessionId).toList();
  }

  @Test
  void stoppingInTheMiddleOfAPageDoesNotSkipTheRestOfIt() {
    Set<String> orphans = executions(250, Set.of(5, 150, 151, 240));

    Set<String> found = new HashSet<>();
    for (int run = 0; run < 3; run++) {
      found.addAll(sweep(2));
    }

    assertThat(found).containsExactlyInAnyOrderElementsOf(orphans);
  }

  @Test
  void aSweepReadsAtMostTheCappedNumberOfPagesAndTheNextSweepContinues() {
    int pages = GuideExecutionOrphanRepository.MAX_PAGES_PER_SWEEP;
    int lastIndex = pages * 100 + 50;
    Set<String> orphans = executions(lastIndex + 1, Set.of(lastIndex));

    assertThat(sweep(10)).isEmpty();
    assertThat(sweep(10)).containsExactlyElementsOf(orphans);
  }

  @Test
  void afterReachingTheEndTheNextSweepStartsOver() {
    executions(30, Set.of());
    assertThat(sweep(10)).isEmpty();

    // 앞쪽 실행의 세션이 나중에 끝나도 다음 주기가 처음부터 다시 읽어 찾는다
    liveSessionOf.remove(inProgress.get(0).userId());

    assertThat(sweep(10)).containsExactly("session-0");
  }
}
