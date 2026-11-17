package com.mairor.backend.users.controller;

import static com.mairor.backend.testsupport.AuthFlowClient.CHROME_WINDOWS;
import static com.mairor.backend.testsupport.AuthFlowClient.SAFARI_IPHONE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.AuthenticatedSessionTestConfig;
import com.mairor.backend.testsupport.MutableClock;
import com.mairor.backend.testsupport.RecordingSessionEndHook;
import com.mairor.backend.testsupport.RecordingSessionEndHook.Call;
import com.mairor.backend.testsupport.RecordingSessionEndHookConfig;
import com.mairor.backend.testsupport.RedisSessionStore;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.session.FindByIndexNameSessionRepository;

/**
 * 로그인이 이전 인증 세션을 대체할 때와 절대 만료로 세션이 끝날 때도 종료 훅이 지우기 전에 호출되는지 실제 HTTP + PostgreSQL 로 확인한다. 절대 만료는 필터가
 * 쓰는 {@link MutableClock} 을 옮겨서 만든다(서버 유휴 만료는 실제 시간 기준이라 영향이 없다).
 */
@Import({
  TestcontainersConfiguration.class,
  AuthenticatedSessionTestConfig.class,
  RecordingSessionEndHookConfig.class
})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionEndHookReplacementAndExpiryTest {

  @LocalServerPort private int port;
  @Autowired private RedisSessionStore sessionStore;
  @Autowired private MutableClock clock;
  @Autowired private RecordingSessionEndHook hook;
  @Autowired private MeterRegistry registry;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;

  private SessionTestClient raw;
  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    raw = new SessionTestClient(port);
    flow = new AuthFlowClient(raw);
    sessionStore.clear();
    clock.set(Instant.now());
    hook.reset();
  }

  private static String sessionIdOf(Login login) {
    return AuthFlowClient.sessionId(login.cookie());
  }

  private boolean alive(Login login) throws Exception {
    return flow.me(login.cookie()).status() == 200;
  }

  private boolean sessionRowExists(Login login) {
    return sessions.findById(sessionIdOf(login)) != null;
  }

  private double failures(String reason) {
    var counter = registry.find("mairor.session.end_hook.failures").tag("reason", reason).counter();
    return counter == null ? 0 : counter.count();
  }

  private void passTheAbsoluteLifetime() {
    clock.set(Instant.now().plus(Duration.ofDays(31)));
  }

  // ---- 로그인이 이전 인증 세션을 대체 ----

  @Test
  void loggingInAgainWithALoggedInCookieCallsTheHookForTheReplacedSession() throws Exception {
    Account account = flow.signUp();
    Login first = flow.login(account, CHROME_WINDOWS);

    Login second = flow.login(account, first.cookie(), CHROME_WINDOWS);

    List<Call> calls = hook.calls;
    assertThat(calls).hasSize(1);
    assertThat(calls.get(0).end().reason()).isEqualTo(SessionEndReason.REPLACED_BY_LOGIN);
    assertThat(calls.get(0).end().sessionId()).isEqualTo(sessionIdOf(first));
    assertThat(calls.get(0).end().userId()).isEqualTo(account.userId().toString());
    assertThat(calls.get(0).sessionExistedWhenCalled()).as("지우기 전에 호출").isTrue();
    assertThat(alive(first)).isFalse();
    assertThat(alive(second)).isTrue();
  }

  @Test
  void switchingToAnotherAccountCallsTheHookWithTheFirstAccount() throws Exception {
    Account first = flow.signUp();
    Account second = flow.signUp();
    Login firstLogin = flow.login(first, CHROME_WINDOWS);

    Login secondLogin = flow.login(second, firstLogin.cookie(), CHROME_WINDOWS);

    assertThat(hook.calls).hasSize(1);
    assertThat(hook.calls.get(0).end().userId()).isEqualTo(first.userId().toString());
    assertThat(hook.calls.get(0).end().sessionId()).isEqualTo(sessionIdOf(firstLogin));
    assertThat(hook.calls.get(0).end().reason()).isEqualTo(SessionEndReason.REPLACED_BY_LOGIN);
    assertThat(alive(secondLogin)).isTrue();
  }

  @Test
  void loggingInWithoutALoggedInSessionDoesNotCallTheHook() throws Exception {
    Account account = flow.signUp();
    // 쿠키 없음
    Login first = flow.login(account, CHROME_WINDOWS);
    hook.reset();
    // 로그인 전 익명 세션 쿠키
    Response anonymous = raw.get("/test-support/anonymous-session", null);

    flow.login(account, anonymous.sessionCookieValue(), SAFARI_IPHONE);

    // 익명 세션은 훅을 부르지 않는다. 같은 계정의 다른 기기 세션만 계정당 1개 규칙으로 대체된다
    assertThat(hook.calls)
        .extracting(call -> call.end().sessionId())
        .containsExactly(sessionIdOf(first));
    assertThat(hook.calls.get(0).end().reason()).isEqualTo(SessionEndReason.REPLACED_BY_LOGIN);
  }

  @Test
  void aFailingHookDoesNotBlockTheLogin() throws Exception {
    Account account = flow.signUp();
    Login first = flow.login(account, CHROME_WINDOWS);
    hook.failingSessionIds.add(sessionIdOf(first));
    double before = failures("replaced_by_login");

    Login second = flow.login(account, first.cookie(), CHROME_WINDOWS);

    // 로그인은 성공하고, 이전 세션은 지워지며, 실패는 지표로 남는다
    assertThat(alive(second)).isTrue();
    assertThat(sessionRowExists(first)).isFalse();
    assertThat(failures("replaced_by_login")).isEqualTo(before + 1);
  }

  // ---- 절대 만료 ----

  @Test
  void aSessionThatReachesTheAbsoluteLifetimeCallsTheHookBeforeItIsRemoved() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);
    hook.reset();
    passTheAbsoluteLifetime();

    Response expired = flow.me(login.cookie());

    assertThat(expired.status()).isEqualTo(401);
    assertThat(hook.calls).hasSize(1);
    Call call = hook.calls.get(0);
    assertThat(call.end().reason()).isEqualTo(SessionEndReason.ABSOLUTE_EXPIRED);
    assertThat(call.end().sessionId()).isEqualTo(sessionIdOf(login));
    assertThat(call.end().userId()).isEqualTo(account.userId().toString());
    assertThat(call.sessionExistedWhenCalled()).as("지우기 전에 호출").isTrue();
    assertThat(sessionRowExists(login)).isFalse();
    // 만료 쿠키만 내려간다
    assertThat(expired.sessionCookieCount()).isEqualTo(1);
    assertThat(expired.sessionCookieMaxAge()).isZero();
  }

  @Test
  void aLiveSessionNeverCallsTheHookOnOrdinaryRequests() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);
    hook.reset();

    flow.me(login.cookie());
    flow.me(login.cookie());

    assertThat(hook.calls).isEmpty();
  }

  @Test
  void whenTheHookFailsAtAbsoluteExpiryTheAnswerIs401AndTheSessionStaysForARetry()
      throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);
    hook.reset();
    hook.failingSessionIds.add(sessionIdOf(login));
    passTheAbsoluteLifetime();

    Response expired = flow.me(login.cookie());

    // 응답은 정상적인 만료(401)다. 세션은 남기고 쿠키도 만료시키지 않는다
    assertThat(expired.status()).isEqualTo(401);
    assertThat(expired.body()).contains("\"code\":\"UNAUTHORIZED\"");
    assertThat(expired.sessionCookieCount()).isZero();
    assertThat(sessionRowExists(login)).isTrue();

    // 다음 요청에서 다시 시도한다
    hook.failingSessionIds.clear();
    Response retry = flow.me(login.cookie());

    assertThat(retry.status()).isEqualTo(401);
    assertThat(hook.calls).hasSize(2);
    assertThat(sessionRowExists(login)).isFalse();
  }

  @Test
  void anExpiredSessionStaysUnusableWhileItsHookKeepsFailing() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);
    hook.failingSessionIds.add(sessionIdOf(login));
    passTheAbsoluteLifetime();

    assertThat(flow.me(login.cookie()).status()).isEqualTo(401);
    // 변경 요청도 403 이 아니라 401 이다
    assertThat(flow.logout(login.cookie(), login.csrfToken()).status()).isEqualTo(401);
  }

  /** 공개 경로(로그인)는 만료된 세션을 이어 쓰면 안 되므로 훅이 실패해도 세션을 지우고 요청을 계속한다. */
  @Test
  void aLoginWithAnExpiredCookieWhoseHookFailsStillSucceedsAndDropsTheOldSession()
      throws Exception {
    Account account = flow.signUp();
    Login old = flow.login(account, CHROME_WINDOWS);
    hook.reset();
    hook.failingSessionIds.add(sessionIdOf(old));
    passTheAbsoluteLifetime();
    double before = failures("absolute_expired");

    Login fresh = flow.login(account, old.cookie(), CHROME_WINDOWS);

    assertThat(alive(fresh)).isTrue();
    assertThat(sessionRowExists(old)).isFalse();
    assertThat(hook.calls)
        .extracting(c -> c.end().reason())
        .contains(SessionEndReason.ABSOLUTE_EXPIRED);
    assertThat(failures("absolute_expired")).isEqualTo(before + 1);
  }

  /**
   * 유휴 만료는 요청 없이 일어나므로, Redis 가 세션의 만료 알림 키를 지울 때 보내는 알림으로 종료 훅이 불린다(운영과 같은 경로). 알림은 비동기라 기다려서
   * 확인한다.
   */
  @Test
  void anIdleSessionThatRedisExpiresCallsTheHookWithIdleExpired() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);
    hook.reset();

    sessionStore.expireNow(sessionIdOf(login));

    await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(
            () ->
                assertThat(hook.calls)
                    .extracting(call -> call.end().sessionId(), call -> call.end().reason())
                    .contains(
                        org.assertj.core.groups.Tuple.tuple(
                            sessionIdOf(login), SessionEndReason.IDLE_EXPIRED)));
    assertThat(hook.calls.get(0).end().userId()).isEqualTo(account.userId().toString());
  }
}
