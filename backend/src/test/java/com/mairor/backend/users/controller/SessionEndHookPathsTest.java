package com.mairor.backend.users.controller;

import static com.mairor.backend.testsupport.AuthFlowClient.CHROME_WINDOWS;
import static com.mairor.backend.testsupport.AuthFlowClient.SAFARI_IPHONE;
import static org.assertj.core.api.Assertions.assertThat;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.RecordingSessionEndHook;
import com.mairor.backend.testsupport.RecordingSessionEndHook.Call;
import com.mairor.backend.testsupport.RecordingSessionEndHookConfig;
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
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 로그아웃·기기 로그아웃·전체 로그아웃이 세션을 지우기 <b>전에</b> 종료 훅을 호출하는지, 훅이 실패하면 세션이 남고 같은 요청으로 다시 시도할 수 있는지 실제 HTTP
 * + PostgreSQL 로 확인한다. 테스트용 훅은 호출을 기록하고(호출 시점에 세션이 저장소에 있었는지 포함) 지정한 세션에서는 실패한다.
 */
@Import({TestcontainersConfiguration.class, RecordingSessionEndHookConfig.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionEndHookPathsTest {

  private static final String SESSIONS = "/v1/users/me/sessions";

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private RecordingSessionEndHook hook;
  @Autowired private MeterRegistry registry;

  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    flow = new AuthFlowClient(new SessionTestClient(port));
    jdbc.update("delete from spring_session");
    hook.reset();
  }

  private static String sessionIdOf(Login login) {
    return AuthFlowClient.sessionId(login.cookie());
  }

  private List<Call> callsFor(String userId) {
    return hook.calls.stream().filter(c -> c.end().userId().equals(userId)).toList();
  }

  private String refOf(Login viewer, String device) throws Exception {
    String body = flow.get(SESSIONS, viewer.cookie()).body();
    List<String> refs = JsonPath.read(body, "$.items[?(@.device == '" + device + "')].sessionRef");
    assertThat(refs).as("%s 기기의 sessionRef", device).hasSize(1);
    return refs.get(0);
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

  // ---- 기기 하나 로그아웃 ----

  @Test
  void revokingAnotherDeviceCallsTheHookOnlyForThatDevice() throws Exception {
    Account account = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login tablet = flow.login(account, CHROME_WINDOWS);
    String phoneRef = refOf(tablet, "Safari · iOS");

    Response response = flow.delete(SESSIONS + "/" + phoneRef, tablet.cookie(), tablet.csrfToken());

    assertThat(response.status()).isEqualTo(204);
    assertThat(hook.calls).hasSize(1);
    Call call = hook.calls.get(0);
    assertThat(call.end().reason()).isEqualTo(SessionEndReason.DEVICE_REVOKED);
    assertThat(call.end().sessionId()).isEqualTo(sessionIdOf(phone));
    assertThat(call.end().userId()).isEqualTo(account.userId().toString());
    assertThat(call.sessionExistedWhenCalled()).isTrue();
    assertThat(alive(phone)).isFalse();
    assertThat(alive(tablet)).isTrue();
  }

  @Test
  void revokingTheCurrentDeviceIsALogout() throws Exception {
    Account account = flow.signUp();
    Login tablet = flow.login(account, CHROME_WINDOWS);
    String ownRef = refOf(tablet, "Chrome · Windows");

    Response response = flow.delete(SESSIONS + "/" + ownRef, tablet.cookie(), tablet.csrfToken());

    assertThat(response.status()).isEqualTo(204);
    assertThat(hook.calls).hasSize(1);
    assertThat(hook.calls.get(0).end().reason()).isEqualTo(SessionEndReason.LOGOUT);
    assertThat(alive(tablet)).isFalse();
  }

  @Test
  void aDeviceWhoseHookFailsStaysLoggedInAndCanBeRevokedAgain() throws Exception {
    Account account = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login tablet = flow.login(account, CHROME_WINDOWS);
    String phoneRef = refOf(tablet, "Safari · iOS");
    hook.failingSessionIds.add(sessionIdOf(phone));

    Response failed = flow.delete(SESSIONS + "/" + phoneRef, tablet.cookie(), tablet.csrfToken());

    assertThat(failed.status()).isEqualTo(500);
    assertThat(alive(phone)).isTrue();
    assertThat(alive(tablet)).isTrue();

    hook.failingSessionIds.clear();
    Response retry = flow.delete(SESSIONS + "/" + phoneRef, tablet.cookie(), tablet.csrfToken());

    assertThat(retry.status()).isEqualTo(204);
    assertThat(alive(phone)).isFalse();
  }

  @Test
  void unknownAndOtherUsersReferencesDoNotCallTheHook() throws Exception {
    Account mine = flow.signUp();
    Account other = flow.signUp();
    Login myLogin = flow.login(mine, CHROME_WINDOWS);
    Login otherLogin = flow.login(other, SAFARI_IPHONE);
    String othersRef = refOf(otherLogin, "Safari · iOS");

    Response unknown =
        flow.delete(
            SESSIONS + "/5a7b9c1d-3e5f-4071-9283-a4b5c6d7e8f9",
            myLogin.cookie(),
            myLogin.csrfToken());
    Response foreign =
        flow.delete(SESSIONS + "/" + othersRef, myLogin.cookie(), myLogin.csrfToken());

    assertThat(unknown.status()).isEqualTo(404);
    assertThat(foreign.status()).isEqualTo(404);
    assertThat(hook.calls).isEmpty();
    assertThat(alive(otherLogin)).isTrue();
  }

  // ---- 전체 로그아웃 ----

  @Test
  void logoutEverywhereCallsTheHookOncePerSessionAndTheCurrentOneLast() throws Exception {
    Account account = flow.signUp();
    Account other = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login second = flow.login(account, CHROME_WINDOWS);
    Login tablet = flow.login(account, CHROME_WINDOWS);
    Login othersLogin = flow.login(other, SAFARI_IPHONE);

    Response response = flow.delete(SESSIONS, tablet.cookie(), tablet.csrfToken());

    assertThat(response.status()).isEqualTo(204);
    List<Call> mine = callsFor(account.userId().toString());
    assertThat(mine).hasSize(3);
    assertThat(mine)
        .extracting(c -> c.end().reason())
        .containsOnly(SessionEndReason.ALL_DEVICES_REVOKED);
    assertThat(mine)
        .extracting(c -> c.end().sessionId())
        .containsExactlyInAnyOrder(sessionIdOf(phone), sessionIdOf(second), sessionIdOf(tablet));
    // 현재 기기는 마지막
    assertThat(mine.get(2).end().sessionId()).isEqualTo(sessionIdOf(tablet));
    assertThat(mine).allMatch(Call::sessionExistedWhenCalled);
    // 다른 회원의 세션에는 호출되지 않는다
    assertThat(callsFor(other.userId().toString())).isEmpty();
    assertThat(alive(othersLogin)).isTrue();
  }

  @Test
  void logoutEverywhereWithAFailingDeviceKeepsThatDeviceAndTheCurrentOneThenRetriesCleanly()
      throws Exception {
    Account account = flow.signUp();
    Login blocked = flow.login(account, SAFARI_IPHONE);
    Login third = flow.login(account, CHROME_WINDOWS);
    Login current = flow.login(account, CHROME_WINDOWS);
    hook.failingSessionIds.add(sessionIdOf(blocked));

    Response failed = flow.delete(SESSIONS, current.cookie(), current.csrfToken());

    assertThat(failed.status()).isEqualTo(500);
    assertThat(failed.sessionCookieCount()).isZero();
    // 실패한 기기와 현재 기기는 남고, 훅이 성공한 기기는 끊겼다
    assertThat(alive(blocked)).isTrue();
    assertThat(alive(current)).isTrue();
    assertThat(alive(third)).isFalse();
    // 현재 기기는 다른 기기가 모두 정리되기 전에는 훅을 호출하지 않는다
    assertThat(hook.calls)
        .extracting(c -> c.end().sessionId())
        .doesNotContain(sessionIdOf(current));

    hook.failingSessionIds.clear();
    hook.calls.clear();
    Response retry = flow.delete(SESSIONS, current.cookie(), current.csrfToken());

    assertThat(retry.status()).isEqualTo(204);
    assertThat(alive(blocked)).isFalse();
    assertThat(alive(current)).isFalse();
    // 이미 끊긴 기기에는 다시 호출되지 않는다
    assertThat(hook.calls)
        .extracting(c -> c.end().sessionId())
        .containsExactlyInAnyOrder(sessionIdOf(blocked), sessionIdOf(current));
  }

  @Test
  void logoutEverywhereWhoseCurrentDeviceHookFailsKeepsOnlyTheCurrentDevice() throws Exception {
    Account account = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login current = flow.login(account, CHROME_WINDOWS);
    hook.failingSessionIds.add(sessionIdOf(current));

    Response failed = flow.delete(SESSIONS, current.cookie(), current.csrfToken());

    assertThat(failed.status()).isEqualTo(500);
    assertThat(alive(phone)).isFalse();
    assertThat(alive(current)).isTrue();
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
