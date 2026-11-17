package com.mairor.backend.users.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import com.mairor.backend.common.security.SessionEndNotifier;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.common.security.SessionLookup;
import com.mairor.backend.common.security.SessionMetrics;
import com.mairor.backend.common.security.UnreadableSessionCleaner;
import com.mairor.backend.common.security.UnreadableSessionException;
import com.mairor.backend.testsupport.MutableClock;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.MapSession;

class UserSessionServiceTest {

  private static final Duration THREE_DAYS = Duration.ofDays(3);
  private static final Duration THIRTY_DAYS = Duration.ofDays(30);

  private final UUID userId = UUID.randomUUID();
  private final Map<String, MapSession> stored = new LinkedHashMap<>();
  private final MutableClock clock = new MutableClock(Instant.now());

  @SuppressWarnings("unchecked")
  private final FindByIndexNameSessionRepository<MapSession> sessions =
      mock(FindByIndexNameSessionRepository.class);

  private final SessionEndHook hook = mock(SessionEndHook.class);
  private final SessionEndNotifier notifier = notifierWith(hook);
  private final UnreadableSessionCleaner unreadable = mock(UnreadableSessionCleaner.class);
  private UserSessionService service;

  private static SessionEndNotifier notifierWith(SessionEndHook... hooks) {
    DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
    for (int i = 0; i < hooks.length; i++) {
      factory.registerSingleton("hook" + i, hooks[i]);
    }
    return new SessionEndNotifier(
        factory.getBeanProvider(SessionEndHook.class),
        new SessionMetrics(new SimpleMeterRegistry()));
  }

  @BeforeEach
  void setUp() {
    when(sessions.findByPrincipalName(userId.toString())).thenAnswer(call -> Map.copyOf(stored));
    when(sessions.findByPrincipalName(
            org.mockito.ArgumentMatchers.argThat(id -> !userId.toString().equals(id))))
        .thenReturn(Map.of());
    service = new UserSessionService(new SessionLookup(sessions, unreadable), notifier);
  }

  /** 로그인 시각이 있는 세션. */
  private MapSession session(String id, Instant lastAccessed) {
    MapSession session = new MapSession(id);
    session.setMaxInactiveInterval(THREE_DAYS);
    session.setLastAccessedTime(lastAccessed);
    session.setAttribute(SessionAttributes.AUTHENTICATED_AT, clock.instant());
    stored.put(id, session);
    return session;
  }

  // ---- 전체 로그아웃 ----

  @Test
  void revokeAllDeletesEverySessionOfTheUserIncludingUnusableOnes() {
    session("phone", Instant.now());
    session("expired", Instant.now().minus(Duration.ofDays(4)));
    stored.put("no-attributes", new MapSession("no-attributes"));

    int count = service.revokeAll(userId);

    assertThat(count).isEqualTo(3);
    verify(sessions).deleteById("phone");
    verify(sessions).deleteById("expired");
    verify(sessions).deleteById("no-attributes");
  }

  @Test
  void revokeAllEndsTheCurrentSessionLast() {
    session("current", Instant.now());
    session("phone", Instant.now());
    session("tablet", Instant.now());

    int count = service.revokeAll(userId, "current");

    assertThat(count).isEqualTo(3);
    // 다른 기기끼리의 순서는 정하지 않는다. 현재 세션만 반드시 마지막이다
    ArgumentCaptor<String> deleted = ArgumentCaptor.forClass(String.class);
    verify(sessions, times(3)).deleteById(deleted.capture());
    assertThat(deleted.getAllValues()).containsExactlyInAnyOrder("current", "phone", "tablet");
    assertThat(deleted.getAllValues().get(2)).isEqualTo("current");
  }

  @Test
  void whenAnotherDeviceFailsTheCurrentSessionIsLeftAndTheRestAreStillTried() {
    session("current", Instant.now());
    session("phone", Instant.now());
    session("tablet", Instant.now());
    doThrow(new IllegalStateException("store down")).when(sessions).deleteById("phone");

    assertThatThrownBy(() -> service.revokeAll(userId, "current"))
        .isInstanceOf(IllegalStateException.class)
        .hasMessage("store down");

    verify(sessions).deleteById("tablet");
    verify(sessions, never()).deleteById("current");
  }

  @Test
  void whenSeveralDevicesFailTheFirstFailureIsThrownWithTheOthersAttached() {
    session("current", Instant.now());
    session("phone", Instant.now());
    session("tablet", Instant.now());
    doThrow(new IllegalStateException("first")).when(sessions).deleteById("phone");
    doThrow(new IllegalStateException("second")).when(sessions).deleteById("tablet");

    assertThatThrownBy(() -> service.revokeAll(userId, "current"))
        .isInstanceOf(IllegalStateException.class)
        .satisfies(
            e -> {
              // 어느 쪽이 먼저 실패하든 하나는 던져지고 다른 하나는 suppressed 로 붙는다
              assertThat(e.getMessage()).isIn("first", "second");
              assertThat(e.getSuppressed()).hasSize(1);
            });
    verify(sessions).deleteById("phone");
    verify(sessions).deleteById("tablet");
    verify(sessions, never()).deleteById("current");
  }

  @Test
  void revokeAllWithAnUnknownCurrentSessionDeletesEverythingElse() {
    session("phone", Instant.now());

    assertThat(service.revokeAll(userId, "not-mine")).isEqualTo(1);

    verify(sessions).deleteById("phone");
    verify(sessions, never()).deleteById("not-mine");
  }

  @Test
  void revokeAllWithoutSessionsDoesNothing() {
    assertThat(service.revokeAll(userId)).isZero();

    verify(sessions, never()).deleteById(anyString());
  }

  @Test
  void revokeAllNeverTouchesAnotherUsersSessions() {
    session("phone", Instant.now());

    assertThat(service.revokeAll(UUID.randomUUID())).isZero();

    verify(sessions, never()).deleteById(anyString());
  }

  // ---- 종료 훅 ----

  private static SessionEnd end(String sessionId, SessionEndReason reason, UUID user) {
    return new SessionEnd(user.toString(), sessionId, reason);
  }

  @Test
  void beforeLogoutCallsTheHookWithTheLogoutReason() {
    service.beforeLogout(userId, "tablet");

    verify(hook).beforeSessionEnds(end("tablet", SessionEndReason.LOGOUT, userId));
  }

  @Test
  void beforeLogoutPropagatesAFailingHookSoTheCallerKeepsTheSession() {
    doThrow(new IllegalStateException("cleanup failed")).when(hook).beforeSessionEnds(any());

    assertThatThrownBy(() -> service.beforeLogout(userId, "tablet"))
        .isInstanceOf(IllegalStateException.class);
  }

  @Test
  void revokeAllCallsTheHookForEverySessionBeforeDeletingIt() {
    session("current", Instant.now());
    session("phone", Instant.now());

    service.revokeAll(userId, "current");

    InOrder order = inOrder(hook, sessions);
    order
        .verify(hook)
        .beforeSessionEnds(end("phone", SessionEndReason.ALL_DEVICES_REVOKED, userId));
    order.verify(sessions).deleteById("phone");
    order
        .verify(hook)
        .beforeSessionEnds(end("current", SessionEndReason.ALL_DEVICES_REVOKED, userId));
    order.verify(sessions).deleteById("current");
  }

  @Test
  void revokeAllKeepsTheSessionWhoseHookFailedAndTheCurrentOneButTriesTheRest() {
    session("current", Instant.now());
    session("blocked", Instant.now());
    session("tablet", Instant.now());
    doThrow(new IllegalStateException("cleanup failed"))
        .when(hook)
        .beforeSessionEnds(end("blocked", SessionEndReason.ALL_DEVICES_REVOKED, userId));

    assertThatThrownBy(() -> service.revokeAll(userId, "current"))
        .isInstanceOf(IllegalStateException.class);

    verify(sessions).deleteById("tablet");
    verify(sessions, never()).deleteById("blocked");
    verify(sessions, never()).deleteById("current");
    // 현재 기기는 다른 기기가 모두 정리되기 전에는 훅도 호출하지 않는다
    verify(hook, never())
        .beforeSessionEnds(end("current", SessionEndReason.ALL_DEVICES_REVOKED, userId));
  }

  @Test
  void revokeAllWithoutACurrentSessionCallsTheHookForEverySession() {
    session("phone", Instant.now());
    session("tablet", Instant.now());

    assertThat(service.revokeAll(userId)).isEqualTo(2);

    verify(hook).beforeSessionEnds(end("phone", SessionEndReason.ALL_DEVICES_REVOKED, userId));
    verify(hook).beforeSessionEnds(end("tablet", SessionEndReason.ALL_DEVICES_REVOKED, userId));
  }

  @Test
  void revokeAllNeverCallsTheHookForAnotherUsersSessions() {
    session("phone", Instant.now());

    service.revokeAll(UUID.randomUUID(), "x");

    verify(hook, never()).beforeSessionEnds(any());
  }

  // ---- 손상된 세션 ----

  private static UnreadableSessionException unreadableValue() {
    return new UnreadableSessionException("읽지 못함(테스트)", new IllegalStateException());
  }

  /** "good" 은 정상, "broken" 은 값을 읽을 수 없는 세션. 회원 색인 조회는 "broken" 때문에 통째로 실패한다. */
  private void oneSessionIsUnreadable() {
    MapSession good = session("good", Instant.now());
    when(sessions.findByPrincipalName(userId.toString())).thenThrow(unreadableValue());
    when(unreadable.sessionIdsOf(userId.toString())).thenReturn(List.of("good", "broken"));
    when(sessions.findById("good")).thenReturn(good);
    when(sessions.findById("broken")).thenThrow(unreadableValue());
    doThrow(unreadableValue()).when(sessions).deleteById("broken");
  }

  @Test
  void aNewLoginStillReplacesSessionsWhenOneOfThemCannotBeRead() {
    oneSessionIsUnreadable();

    assertThat(service.replaceForNewLogin(userId)).isEqualTo(2);

    verify(sessions).deleteById("good");
    verify(unreadable).remove(userId.toString(), "broken");
    verify(hook).beforeSessionEnds(end("good", SessionEndReason.REPLACED_BY_LOGIN, userId));
    verify(hook).beforeSessionEnds(end("broken", SessionEndReason.REPLACED_BY_LOGIN, userId));
  }

  @Test
  void revokeAllStillEndsEverySessionWhenOneOfThemCannotBeRead() {
    oneSessionIsUnreadable();

    assertThat(service.revokeAll(userId)).isEqualTo(2);

    verify(sessions).deleteById("good");
    verify(unreadable).remove(userId.toString(), "broken");
  }

  @Test
  void otherStoreFailuresAreNotTreatedAsUnreadableSessions() {
    when(sessions.findByPrincipalName(userId.toString()))
        .thenThrow(new IllegalStateException("store down"));

    assertThatThrownBy(() -> service.replaceForNewLogin(userId))
        .isInstanceOf(IllegalStateException.class);

    verify(unreadable, never()).sessionIdsOf(anyString());
    verify(unreadable, never()).remove(anyString(), anyString());
  }
}
