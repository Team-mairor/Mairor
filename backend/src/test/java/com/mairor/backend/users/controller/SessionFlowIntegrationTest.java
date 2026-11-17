package com.mairor.backend.users.controller;

import static com.mairor.backend.testsupport.AuthFlowClient.CHROME_WINDOWS;
import static org.assertj.core.api.Assertions.assertThat;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.AuthenticatedSessionTestConfig;
import com.mairor.backend.testsupport.MutableClock;
import com.mairor.backend.testsupport.RedisSessionStore;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import com.mairor.backend.users.support.LoginHashGate;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

/**
 * 로그인 → 내 계정 조회 → 로그아웃 → 재사용 차단을 실제 HTTP + PostgreSQL 로 확인한다. MockMvc 는 세션 직렬화·재조회, 실제 {@code
 * Set-Cookie}, CSRF 필터가 새 토큰을 받아들이는지를 거치지 않아 이 검증에 쓸 수 없다.
 *
 * <p>쿠키는 {@link SessionTestClient} 가 응답에서 꺼내 다음 요청에 직접 실어 보낸다. 절대 만료는 필터와 서비스가 쓰는 {@link
 * MutableClock} 으로 옮긴다.
 */
@Import({TestcontainersConfiguration.class, AuthenticatedSessionTestConfig.class})
@ExtendWith(OutputCaptureExtension.class)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionFlowIntegrationTest {

  private static final long THREE_DAYS_SECONDS = Duration.ofDays(3).toSeconds();

  @LocalServerPort private int port;
  @Autowired private RedisSessionStore sessionStore;
  @Autowired private MutableClock clock;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;
  @Autowired private LoginHashGate hashGate;
  @Autowired private MeterRegistry registry;

  private SessionTestClient client;

  @BeforeEach
  void setUp() {
    client = new SessionTestClient(port);
    flow = new AuthFlowClient(client);
    sessionStore.clear();
    clock.set(Instant.now());
  }

  private AuthFlowClient flow;

  private Account signUp() throws Exception {
    return flow.signUp();
  }

  private Login login(Account account, String sessionCookie) throws Exception {
    return flow.login(account, sessionCookie, CHROME_WINDOWS);
  }

  private Login login(Account account) throws Exception {
    return flow.login(account, CHROME_WINDOWS);
  }

  private Response me(String cookie) throws Exception {
    return flow.me(cookie);
  }

  private Response logout(String cookie, String csrfToken) throws Exception {
    return flow.logout(cookie, csrfToken);
  }

  private Response change(String cookie, String csrfToken) throws Exception {
    return flow.post("/test-support/change", cookie, csrfToken);
  }

  private long sessionRows() {
    return sessionStore.count();
  }

  // ---- 로그인 → 내 계정 → 로그아웃 → 재사용 차단 ----

  @Test
  void loginThenMeThenLogoutThenTheCookieIsUseless() throws Exception {
    Account account = signUp();

    Login login = login(account);
    Response me = me(login.cookie());
    Response logout = logout(login.cookie(), login.csrfToken());
    Response reused = me(login.cookie());

    assertThat(me.status()).isEqualTo(200);
    assertThat(JsonPath.<String>read(me.body(), "$.user.userId"))
        .isEqualTo(account.userId().toString());
    assertThat(JsonPath.<String>read(me.body(), "$.csrfToken")).isNotBlank();
    assertThat(logout.status()).isEqualTo(204);
    assertThat(reused.status()).isEqualTo(401);
    assertThat(reused.body()).contains("UNAUTHORIZED");
    assertThat(sessionRows()).isZero();
  }

  @Test
  void theLoginCookieHasTheDocumentedAttributes() throws Exception {
    Login login = login(signUp());

    assertThat(login.response().sessionCookieCount()).isEqualTo(1);
    assertThat(login.response().sessionSetCookie())
        .startsWith("__Host-sessionId=")
        .contains("Max-Age=" + THREE_DAYS_SECONDS)
        .contains("Path=/")
        .contains("Secure")
        .contains("HttpOnly")
        .contains("SameSite=Strict")
        .doesNotContain("Domain");
  }

  @Test
  void meRefreshesTheCookieExactlyOnceWithTheSameSessionId() throws Exception {
    Login login = login(signUp());

    Response me = me(login.cookie());

    assertThat(me.sessionCookieCount()).isEqualTo(1);
    assertThat(me.sessionCookieValue()).isEqualTo(login.cookie());
    assertThat(me.sessionCookieMaxAge()).isEqualTo(THREE_DAYS_SECONDS);
  }

  @Test
  void logoutAnswersWithOnlyTheExpiryCookie() throws Exception {
    Login login = login(signUp());

    Response logout = logout(login.cookie(), login.csrfToken());

    assertThat(logout.status()).isEqualTo(204);
    assertThat(logout.sessionCookieCount()).isEqualTo(1);
    assertThat(logout.sessionCookieMaxAge()).isZero();
  }

  @Test
  void logoutNeedsTheCsrfTokenAndKeepsTheSessionWhenItIsWrong() throws Exception {
    Login login = login(signUp());

    assertThat(logout(login.cookie(), null).status()).isEqualTo(403);
    Response wrong = logout(login.cookie(), "not-a-valid-token");
    assertThat(wrong.status()).isEqualTo(403);
    assertThat(wrong.body()).contains("CSRF_INVALID");

    // 토큰이 틀렸다고 로그아웃되지는 않는다
    assertThat(me(login.cookie()).status()).isEqualTo(200);
  }

  @Test
  void logoutWithoutASessionIs403() throws Exception {
    Response logout = logout(null, null);

    assertThat(logout.status()).isEqualTo(403);
    assertThat(logout.body()).contains("CSRF_INVALID");
  }

  @Test
  void loginWithoutAllowedOriginIsRejected() throws Exception {
    Account account = signUp();
    String body =
        "{\"email\": \"%s\", \"password\": \"%s\"}"
            .formatted(account.email(), AuthFlowClient.PASSWORD);

    Response response = client.postJson("/v1/users/login", body, null, null);

    assertThat(response.status()).isEqualTo(403);
    assertThat(response.setCookies()).isEmpty();
  }

  /** 서로 다른 이메일을 쏟아부어도 BCrypt 동시 실행은 상한까지만 허용되고, 거절된 시도는 실패 횟수에 들어가지 않는다. */
  @Test
  void whenTheHashGateIsFullLoginAnswers429WithRetryAfterAndDoesNotCountTheAttempt()
      throws Exception {
    Account account = signUp();
    List<LoginHashGate.Permit> held = new ArrayList<>();
    try {
      for (var permit = hashGate.tryEnter(); permit.isPresent(); permit = hashGate.tryEnter()) {
        held.add(permit.get());
      }
      for (int i = 0; i < 5; i++) {
        Response busy = flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, CHROME_WINDOWS);
        assertThat(busy.status()).isEqualTo(429);
        assertThat(busy.body()).contains("TOO_MANY_REQUESTS");
        assertThat(busy.header("Retry-After")).isEqualTo("1");
        assertThat(busy.setCookies()).isEmpty();
      }
    } finally {
      held.forEach(LoginHashGate.Permit::close);
    }

    // 5번 거절됐지만 시도로 세지 않았으므로 바로 로그인된다(잠금 임계치 3회)
    assertThat(login(account).response().status()).isEqualTo(200);
  }

  private double loginCount(String result) {
    var counter = registry.find("mairor.login.attempts").tag("result", result).counter();
    return counter == null ? 0 : counter.count();
  }

  @Test
  void loginResultsAreCountedWithoutAnyIdentifierInTheLabels() throws Exception {
    Account account = flow.signUp();
    double successBefore = loginCount("success");
    double invalidBefore = loginCount("invalid_credentials");

    flow.loginRaw(account.email(), "WrongPassword!2026", CHROME_WINDOWS);
    login(account);

    assertThat(loginCount("success")).isEqualTo(successBefore + 1);
    assertThat(loginCount("invalid_credentials")).isEqualTo(invalidBefore + 1);
    assertThat(registry.getMeters())
        .filteredOn(meter -> meter.getId().getName().startsWith("mairor."))
        .allSatisfy(
            meter ->
                assertThat(meter.getId().getTags())
                    .allSatisfy(tag -> assertThat(tag.getValue()).doesNotContain("@")));
  }

  @Test
  void loginNeverPutsThePasswordTheHashOrTheSessionIdInTheLogOrTheBody(CapturedOutput output)
      throws Exception {
    Account account = signUp();
    Response wrong = flow.loginRaw(account.email(), "WrongPassword!2026", CHROME_WINDOWS);
    Login login = login(account);
    String rawSessionId = AuthFlowClient.sessionId(login.cookie());

    assertThat(wrong.status()).isEqualTo(401);
    assertThat(output.getAll())
        .doesNotContain(AuthFlowClient.PASSWORD)
        .doesNotContain("WrongPassword!2026")
        .doesNotContain("$2a$")
        .doesNotContain(rawSessionId)
        .doesNotContain(login.cookie())
        .doesNotContain(login.csrfToken());
    assertThat(login.response().body())
        .doesNotContain(AuthFlowClient.PASSWORD)
        .doesNotContain("$2a$")
        .doesNotContain(rawSessionId)
        .doesNotContain("password");
  }

  // ---- 세션 고정·계정 전환·다중 기기 ----

  @Test
  void loggingInWithAnAnonymousSessionIssuesANewSessionId() throws Exception {
    Account account = signUp();
    Response anonymous = client.get("/test-support/anonymous-session", null);
    String anonymousCookie = anonymous.sessionCookieValue();
    assertThat(anonymousCookie).isNotBlank();

    Login login = login(account, anonymousCookie);

    assertThat(login.response().sessionCookieCount()).isEqualTo(1);
    assertThat(login.cookie()).isNotEqualTo(anonymousCookie);
    // 로그인 전에 받은 세션 ID 로는 인증되지 않는다 (세션 고정 방지)
    assertThat(me(anonymousCookie).status()).isEqualTo(401);
    assertThat(me(login.cookie()).status()).isEqualTo(200);
  }

  @Test
  void theCsrfTokenKeptInTheAnonymousSessionIsReplacedByLogin() throws Exception {
    Account account = signUp();
    Response anonymous = client.get("/test-support/anonymous-session", null);
    String tokenBeforeLogin = anonymous.body().trim();

    Login login = login(account, anonymous.sessionCookieValue());

    // 로그인 전에 받아 둔 토큰은 이제 거절되고, 로그인 응답의 새 토큰은 통과한다
    assertThat(change(login.cookie(), tokenBeforeLogin).status()).isEqualTo(403);
    Response accepted = change(login.cookie(), login.csrfToken());
    assertThat(accepted.status()).isEqualTo(200);
    assertThat(accepted.body()).isEqualTo("changed");
    // 내 계정 조회로 다시 받은 토큰도 통과하고, 토큰이 없거나 틀리면 거절된다
    String tokenFromMe = JsonPath.read(me(login.cookie()).body(), "$.csrfToken");
    assertThat(change(login.cookie(), tokenFromMe).status()).isEqualTo(200);
    assertThat(change(login.cookie(), null).status()).isEqualTo(403);
    assertThat(change(login.cookie(), "not-a-valid-token").status()).isEqualTo(403);
  }

  @Test
  void theCsrfTokenIsUsableWhenLoggingInFromABrandNewBrowser() throws Exception {
    // 세션이 전혀 없던 브라우저(CSRF 토큰도 아직 없음)가 로그인해도 응답 토큰이 통과한다
    Login login = login(signUp());

    assertThat(change(login.cookie(), login.csrfToken()).status()).isEqualTo(200);
  }

  @Test
  void loggingInAsAnotherAccountDiscardsTheFirstSession() throws Exception {
    Account first = signUp();
    Account second = signUp();
    Login firstLogin = login(first);

    Login secondLogin = login(second, firstLogin.cookie());

    assertThat(secondLogin.response().sessionCookieCount()).isEqualTo(1);
    assertThat(secondLogin.cookie()).isNotEqualTo(firstLogin.cookie());
    assertThat(me(firstLogin.cookie()).status()).isEqualTo(401);
    Response me = me(secondLogin.cookie());
    assertThat(JsonPath.<String>read(me.body(), "$.user.userId"))
        .isEqualTo(second.userId().toString());
    assertThat(sessions.findByPrincipalName(first.userId().toString())).isEmpty();
    assertThat(sessions.findByPrincipalName(second.userId().toString())).hasSize(1);
  }

  /** 계정당 로그인 세션은 하나다. 다른 기기에서 같은 계정으로 로그인하면 먼저 로그인한 기기는 로그아웃된다. */
  @Test
  void loggingInOnAnotherDeviceLogsOutTheFirstOne() throws Exception {
    Account account = signUp();
    Login phone = login(account);
    Login tablet = login(account);

    assertThat(phone.cookie()).isNotEqualTo(tablet.cookie());
    assertThat(me(phone.cookie()).status()).isEqualTo(401);
    assertThat(me(tablet.cookie()).status()).isEqualTo(200);
    assertThat(sessions.findByPrincipalName(account.userId().toString()))
        .containsOnlyKeys(AuthFlowClient.sessionId(tablet.cookie()));
  }

  @Test
  void theSessionRecordsTheLoginTime() throws Exception {
    Account account = signUp();
    Instant loginTime = clock.instant();

    Login login = login(account);

    Session session =
        sessions
            .findByPrincipalName(account.userId().toString())
            .get(AuthFlowClient.sessionId(login.cookie()));
    assertThat(session).isNotNull();
    assertThat((Instant) session.getAttribute(SessionAttributes.AUTHENTICATED_AT))
        .isEqualTo(loginTime);
  }

  // ---- 절대 만료 ----

  @Test
  void aLoginExpiresThirtyDaysAfterItWasMade() throws Exception {
    Login login = login(signUp());

    clock.set(clock.instant().plus(Duration.ofDays(29)).plus(Duration.ofHours(23)));
    Response almost = me(login.cookie());
    assertThat(almost.status()).isEqualTo(200);
    // 절대 만료까지 1시간 남았으므로 쿠키도 1시간만 늘어난다
    assertThat(almost.sessionCookieMaxAge()).isEqualTo(Duration.ofHours(1).toSeconds());

    clock.advance(Duration.ofHours(1));
    Response expired = me(login.cookie());

    assertThat(expired.status()).isEqualTo(401);
    assertThat(sessionRows()).isZero();
  }

  @Test
  void anExpiredCookieDoesNotBlockLoggingInAgain() throws Exception {
    Account account = signUp();
    Login first = login(account);
    clock.set(clock.instant().plus(Duration.ofDays(30)));
    Instant secondLoginTime = clock.instant();

    // 로그인 경로는 공개 경로라 만료된 쿠키를 가지고 있어도 막지 않는다
    Login second = login(account, first.cookie());

    assertThat(second.response().sessionCookieCount()).isEqualTo(1);
    assertThat(second.cookie()).isNotEqualTo(first.cookie());
    assertThat(me(first.cookie()).status()).isEqualTo(401);
    assertThat(me(second.cookie()).status()).isEqualTo(200);
    Session session =
        sessions
            .findByPrincipalName(account.userId().toString())
            .get(AuthFlowClient.sessionId(second.cookie()));
    assertThat((Instant) session.getAttribute(SessionAttributes.AUTHENTICATED_AT))
        .isEqualTo(secondLoginTime);
  }
}
