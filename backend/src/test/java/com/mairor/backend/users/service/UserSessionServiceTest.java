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
import com.mairor.backend.common.security.SessionLifetimePolicy;
import com.mairor.backend.common.security.SessionMetrics;
import com.mairor.backend.testsupport.MutableClock;
import com.mairor.backend.users.dto.response.SessionItemResponse;
import com.mairor.backend.users.support.UserSessionAttributes;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
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
    service =
        new UserSessionService(
            sessions,
            new SessionLifetimePolicy(THREE_DAYS, THREE_DAYS, THIRTY_DAYS),
            notifier,
            clock);
  }

  /** 기기 정보가 모두 있는 유효한 세션. */
  private MapSession device(String id, UUID ref, String device, Instant lastAccessed) {
    MapSession session = new MapSession(id);
    session.setMaxInactiveInterval(THREE_DAYS);
    session.setLastAccessedTime(lastAccessed);
    session.setAttribute(SessionAttributes.AUTHENTICATED_AT, clock.instant());
    session.setAttribute(UserSessionAttributes.SESSION_REF, ref);
    if (device != null) {
      session.setAttribute(UserSessionAttributes.DEVICE, device);
    }
    stored.put(id, session);
    return session;
  }

  // ---- 목록 ----

  @Test
  void listsActiveDevicesNewestFirstAndMarksTheCurrentOne() {
    Instant now = Instant.now();
    UUID phoneRef = UUID.randomUUID();
    UUID tabletRef = UUID.randomUUID();
    MapSession phone = device("phone", phoneRef, "Safari · iOS", now.minusSeconds(3_600));
    MapSession tablet = device("tablet", tabletRef, "Chrome · Windows", now.minusSeconds(60));

    List<SessionItemResponse> items = service.list(userId, "tablet");

    assertThat(items).hasSize(2);
    assertThat(items.get(0))
        .isEqualTo(
            new SessionItemResponse(
                tabletRef.toString(),
                "Chrome · Windows",
                clock.instant(),
                tablet.getLastAccessedTime(),
                true));
    assertThat(items.get(1))
        .isEqualTo(
            new SessionItemResponse(
                phoneRef.toString(),
                "Safari · iOS",
                clock.instant(),
                phone.getLastAccessedTime(),
                false));
  }

  /** 익명 세션을 재사용해 로그인하면 세션 생성 시각이 로그인 시각보다 앞선다. 목록에는 로그인 시각을 보여 준다. */
  @Test
  void createdAtIsTheLoginTimeNotTheTimeTheSessionWasCreated() {
    MapSession phone = device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());
    Instant loggedInAt = clock.instant().minus(Duration.ofDays(2));
    phone.setAttribute(SessionAttributes.AUTHENTICATED_AT, loggedInAt);

    SessionItemResponse item = service.list(userId, "phone").get(0);

    assertThat(item.createdAt()).isEqualTo(loggedInAt).isNotEqualTo(phone.getCreationTime());
  }

  @Test
  void noDeviceIsCurrentWhenTheCurrentSessionIsUnknown() {
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());

    assertThat(service.list(userId, null))
        .extracting(SessionItemResponse::current)
        .containsOnly(false);
  }

  @Test
  void aSessionWithoutADeviceNameIsShownAsUnknown() {
    device("phone", UUID.randomUUID(), null, Instant.now());

    assertThat(service.list(userId, "phone"))
        .extracting(SessionItemResponse::device)
        .containsExactly("알 수 없는 기기");
  }

  @Test
  void leavesOutSessionsThatAreNotUsableDevices() {
    Instant now = Instant.now();
    UUID goodRef = UUID.randomUUID();
    device("good", goodRef, "Chrome · Windows", now);
    // 서버 유휴 만료가 지난 세션 (저장소가 아직 지우지 않았다)
    device("idle-expired", UUID.randomUUID(), "Chrome · Windows", now.minus(Duration.ofDays(4)));
    // 절대 만료가 지난 세션
    MapSession absoluteExpired =
        device("absolute-expired", UUID.randomUUID(), "Chrome · Windows", now);
    absoluteExpired.setAttribute(
        SessionAttributes.AUTHENTICATED_AT, clock.instant().minus(THIRTY_DAYS));
    // 기기 식별자가 없는 세션
    MapSession noRef = new MapSession("no-ref");
    noRef.setAttribute(SessionAttributes.AUTHENTICATED_AT, clock.instant());
    stored.put("no-ref", noRef);
    // 로그인 시각이 없는 세션
    MapSession noLoginTime = new MapSession("no-login-time");
    noLoginTime.setAttribute(UserSessionAttributes.SESSION_REF, UUID.randomUUID());
    stored.put("no-login-time", noLoginTime);

    List<SessionItemResponse> items = service.list(userId, "good");

    assertThat(items)
        .extracting(SessionItemResponse::sessionRef)
        .containsExactly(goodRef.toString());
  }

  @Test
  void listIsEmptyWhenThereAreNoSessions() {
    assertThat(service.list(userId, null)).isEmpty();
  }

  // ---- 기기 하나 로그아웃 ----

  @Test
  void revokesOnlyTheDeviceWithTheMatchingReference() {
    UUID phoneRef = UUID.randomUUID();
    device("phone", phoneRef, "Safari · iOS", Instant.now());
    device("tablet", UUID.randomUUID(), "Chrome · Windows", Instant.now());

    Optional<String> revoked = service.revoke(userId, phoneRef, "tablet");

    assertThat(revoked).contains("phone");
    verify(sessions).deleteById("phone");
    verify(sessions, never()).deleteById("tablet");
  }

  @Test
  void revokingAnUnknownReferenceDeletesNothing() {
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());

    assertThat(service.revoke(userId, UUID.randomUUID(), null)).isEmpty();

    verify(sessions, never()).deleteById(anyString());
  }

  @Test
  void aReferenceOfAnotherUsersDeviceFindsNothing() {
    UUID ref = UUID.randomUUID();
    device("phone", ref, "Safari · iOS", Instant.now());
    UUID otherUser = UUID.randomUUID();

    // 조회는 호출한 회원의 principal 로만 하므로 다른 회원의 sessionRef 로는 찾을 수 없다
    assertThat(service.revoke(otherUser, ref, null)).isEmpty();

    verify(sessions, never()).deleteById(anyString());
  }

  @Test
  void anExpiredDeviceCannotBeRevokedByItsReference() {
    UUID ref = UUID.randomUUID();
    device("idle-expired", ref, "Chrome · Windows", Instant.now().minus(Duration.ofDays(4)));

    assertThat(service.revoke(userId, ref, null)).isEmpty();
  }

  // ---- 전체 로그아웃 ----

  @Test
  void revokeAllDeletesEverySessionOfTheUserIncludingUnusableOnes() {
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());
    device(
        "expired", UUID.randomUUID(), "Chrome · Windows", Instant.now().minus(Duration.ofDays(4)));
    stored.put("no-attributes", new MapSession("no-attributes"));

    int count = service.revokeAll(userId);

    assertThat(count).isEqualTo(3);
    verify(sessions).deleteById("phone");
    verify(sessions).deleteById("expired");
    verify(sessions).deleteById("no-attributes");
  }

  @Test
  void revokeAllEndsTheCurrentSessionLast() {
    device("current", UUID.randomUUID(), "Chrome · Windows", Instant.now());
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());
    device("tablet", UUID.randomUUID(), "Chrome · Windows", Instant.now());

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
    device("current", UUID.randomUUID(), "Chrome · Windows", Instant.now());
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());
    device("tablet", UUID.randomUUID(), "Chrome · Windows", Instant.now());
    doThrow(new IllegalStateException("store down")).when(sessions).deleteById("phone");

    assertThatThrownBy(() -> service.revokeAll(userId, "current"))
        .isInstanceOf(IllegalStateException.class)
        .hasMessage("store down");

    verify(sessions).deleteById("tablet");
    verify(sessions, never()).deleteById("current");
  }

  @Test
  void whenSeveralDevicesFailTheFirstFailureIsThrownWithTheOthersAttached() {
    device("current", UUID.randomUUID(), "Chrome · Windows", Instant.now());
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());
    device("tablet", UUID.randomUUID(), "Chrome · Windows", Instant.now());
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
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());

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
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());

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
  void revokeCallsTheHookBeforeDeletingTheDevice() {
    UUID phoneRef = UUID.randomUUID();
    device("phone", phoneRef, "Safari · iOS", Instant.now());

    service.revoke(userId, phoneRef, "tablet");

    InOrder order = inOrder(hook, sessions);
    order.verify(hook).beforeSessionEnds(end("phone", SessionEndReason.DEVICE_REVOKED, userId));
    order.verify(sessions).deleteById("phone");
  }

  @Test
  void revokingTheCurrentDeviceUsesTheLogoutReason() {
    UUID ref = UUID.randomUUID();
    device("tablet", ref, "Chrome · Windows", Instant.now());

    service.revoke(userId, ref, "tablet");

    verify(hook).beforeSessionEnds(end("tablet", SessionEndReason.LOGOUT, userId));
  }

  @Test
  void aFailingHookKeepsTheDeviceAndPropagates() {
    UUID phoneRef = UUID.randomUUID();
    device("phone", phoneRef, "Safari · iOS", Instant.now());
    doThrow(new IllegalStateException("cleanup failed")).when(hook).beforeSessionEnds(any());

    assertThatThrownBy(() -> service.revoke(userId, phoneRef, "tablet"))
        .isInstanceOf(IllegalStateException.class);

    verify(sessions, never()).deleteById(anyString());
  }

  @Test
  void anUnknownReferenceDoesNotCallTheHook() {
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());

    assertThat(service.revoke(userId, UUID.randomUUID(), "tablet")).isEmpty();

    verify(hook, never()).beforeSessionEnds(any());
  }

  @Test
  void revokeAllCallsTheHookForEverySessionBeforeDeletingIt() {
    device("current", UUID.randomUUID(), "Chrome · Windows", Instant.now());
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());

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
    device("current", UUID.randomUUID(), "Chrome · Windows", Instant.now());
    device("blocked", UUID.randomUUID(), "Safari · iOS", Instant.now());
    device("tablet", UUID.randomUUID(), "Chrome · Windows", Instant.now());
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
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());
    device("tablet", UUID.randomUUID(), "Chrome · Windows", Instant.now());

    assertThat(service.revokeAll(userId)).isEqualTo(2);

    verify(hook).beforeSessionEnds(end("phone", SessionEndReason.ALL_DEVICES_REVOKED, userId));
    verify(hook).beforeSessionEnds(end("tablet", SessionEndReason.ALL_DEVICES_REVOKED, userId));
  }

  @Test
  void revokeAllNeverCallsTheHookForAnotherUsersSessions() {
    device("phone", UUID.randomUUID(), "Safari · iOS", Instant.now());

    service.revokeAll(UUID.randomUUID(), "x");

    verify(hook, never()).beforeSessionEnds(any());
  }
}
