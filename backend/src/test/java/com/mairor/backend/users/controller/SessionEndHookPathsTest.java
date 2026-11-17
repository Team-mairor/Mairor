package com.mairor.backend.users.controller;

import static com.mairor.backend.testsupport.AuthFlowClient.CHROME_WINDOWS;
import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.RecordingSessionEndHook;
import com.mairor.backend.testsupport.RecordingSessionEndHook.Call;
import com.mairor.backend.testsupport.RecordingSessionEndHookConfig;
import com.mairor.backend.testsupport.RedisSessionStore;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;

/**
 * 로그아웃이 세션을 지우기 <b>전에</b> 종료 훅을 호출하는지, 훅이 실패하면 세션이 남고 같은 요청으로 다시 시도할 수 있는지 실제 HTTP + Redis 세션 저장소로
 * 확인한다. 테스트용 훅은 호출을 기록하고(호출 시점에 세션이 저장소에 있었는지 포함) 지정한 세션에서는 실패한다.
 */
@Import({TestcontainersConfiguration.class, RecordingSessionEndHookConfig.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionEndHookPathsTest {

  @LocalServerPort private int port;
  @Autowired private RedisSessionStore sessionStore;
  @Autowired private RecordingSessionEndHook hook;
  @Autowired private MeterRegistry registry;

  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    flow = new AuthFlowClient(new SessionTestClient(port));
    sessionStore.clear();
    hook.reset();
  }

  private static String sessionIdOf(Login login) {
    return AuthFlowClient.sessionId(login.cookie());
  }

  private List<Call> callsFor(String userId) {
    return hook.calls.stream().filter(c -> c.end().userId().equals(userId)).toList();
  }

  private boolean alive(Login login) throws Exception {
    return flow.me(login.cookie()).status() == 200;
  }

  // ---- 로그아웃 ----

  @Test
  void logoutCallsTheHookOnceBeforeTheSessionIsDeleted() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);

    Response response = flow.logout(login.cookie(), login.csrfToken());

    assertThat(response.status()).isEqualTo(204);
    assertThat(hook.calls).hasSize(1);
    Call call = hook.calls.get(0);
    assertThat(call.end().reason()).isEqualTo(SessionEndReason.LOGOUT);
    assertThat(call.end().userId()).isEqualTo(account.userId().toString());
    assertThat(call.end().sessionId()).isEqualTo(sessionIdOf(login));
    assertThat(call.sessionExistedWhenCalled()).as("훅이 호출될 때 세션은 아직 있어야 한다").isTrue();
    assertThat(alive(login)).isFalse();
  }

  @Test
  void aLogoutWhoseHookFailsKeepsTheSessionAndCanBeRetried() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);
    hook.failingSessionIds.add(sessionIdOf(login));

    Response failed = flow.logout(login.cookie(), login.csrfToken());

    assertThat(failed.status()).isEqualTo(500);
    assertThat(failed.body()).contains("\"code\":\"INTERNAL_ERROR\"").doesNotContain("<html");
    // 로그아웃이 끝나지 않았다: 만료 쿠키가 내려가지 않고 세션이 살아 있다
    assertThat(failed.sessionCookieCount()).isZero();
    assertThat(alive(login)).isTrue();

    hook.failingSessionIds.clear();
    Response retry = flow.logout(login.cookie(), login.csrfToken());

    assertThat(retry.status()).isEqualTo(204);
    assertThat(alive(login)).isFalse();
    assertThat(hook.calls).hasSize(2);
  }

  @Test
  void aRejectedLogoutDoesNotCallTheHook() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);

    Response noToken = flow.logout(login.cookie(), null);
    Response noSession = flow.logout(null, null);

    assertThat(noToken.status()).isEqualTo(403);
    assertThat(noSession.status()).isEqualTo(403);
    assertThat(hook.calls).isEmpty();
    assertThat(alive(login)).isTrue();
  }

  // ---- 지표 ----

  @Test
  void aFailingHookIsCountedByReason() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);
    var counter = registry.find("mairor.session.end_hook.failures").tag("reason", "logout");
    double before = counter.counter() == null ? 0 : counter.counter().count();
    hook.failingSessionIds.add(sessionIdOf(login));

    flow.logout(login.cookie(), login.csrfToken());

    double after =
        registry.find("mairor.session.end_hook.failures").tag("reason", "logout").counter().count();
    assertThat(after).isEqualTo(before + 1);
  }
}
