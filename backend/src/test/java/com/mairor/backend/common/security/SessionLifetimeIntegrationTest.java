package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthenticatedSessionTestConfig;
import com.mairor.backend.testsupport.MutableClock;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

/**
 * 세션 수명 정책(서버 유휴 3일 / 쿠키 3일 갱신 / 절대 30일)을 실제 HTTP + PostgreSQL 로 확인한다.
 *
 * <p>시간 조작은 두 가지로 나뉜다. 절대 만료와 쿠키 {@code Max-Age} 계산은 필터가 쓰는 {@link MutableClock} 을 옮기고, 서버 유휴 만료는
 * Spring Session 이 따로 시각을 관리하므로 {@code spring_session} 컬럼을 직접 되돌린다. 만료 판정은 {@code last_access_time
 * + max_inactive_interval} 기준이라 {@code expiry_time} 만 바꿔서는 만료되지 않는다.
 */
@Import({TestcontainersConfiguration.class, AuthenticatedSessionTestConfig.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionLifetimeIntegrationTest {

  private static final long THREE_DAYS_SECONDS = Duration.ofDays(3).toSeconds();

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private MutableClock clock;
  @Autowired private SessionLifetimePolicy policy;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;

  private SessionTestClient client;

  @BeforeEach
  void setUp() {
    client = new SessionTestClient(port);
    jdbc.update("delete from spring_session");
    clock.set(Instant.now());
  }

  private record Login(UUID userId, String cookie, Instant authenticatedAt) {}

  private Login login() throws Exception {
    return login("");
  }

  private Login login(String extraQuery) throws Exception {
    UUID userId = UUID.randomUUID();
    Instant authenticatedAt = clock.instant();
    Response response = client.post("/test-support/login?userId=" + userId + extraQuery, null);
    assertThat(response.status()).isEqualTo(200);
    assertThat(response.sessionCookieValue()).isNotBlank();
    return new Login(userId, response.sessionCookieValue(), authenticatedAt);
  }

  /** 세션 쿠키 값(Base64)에서 실제 세션 ID 를 꺼낸다. */
  private static String sessionId(String cookie) {
    return new String(Base64.getDecoder().decode(cookie));
  }

  /** 마지막 접근 시각을 {@code elapsed} 만큼 과거로 되돌려, 그만큼 요청이 없었던 상태를 만든다. */
  private void idleFor(String cookie, Duration elapsed) {
    long millis = elapsed.toMillis();
    jdbc.update(
        "update spring_session set last_access_time = last_access_time - ?, "
            + "expiry_time = expiry_time - ? where session_id = ?",
        millis,
        millis,
        sessionId(cookie));
  }

  private long sessionRows() {
    return jdbc.queryForObject("select count(*) from spring_session", Long.class);
  }

  // ---- 정책 값 ----

  @Test
  void usesTheDocumentedLifetimes() {
    assertThat(policy.idleTimeout()).isEqualTo(Duration.ofDays(3));
    assertThat(policy.cookieMaxAge()).isEqualTo(Duration.ofDays(3));
    assertThat(policy.absoluteTimeout()).isEqualTo(Duration.ofDays(30));
  }

  // ---- 서버 유휴 만료와 쿠키 갱신 ----

  @Test
  void reconnectingExtendsTheServerIdleExpiryAndTheCookieTogether() throws Exception {
    Login login = login();
    idleFor(login.cookie(), Duration.ofDays(2));
    long expiryBefore =
        jdbc.queryForObject(
            "select expiry_time from spring_session where session_id = ?",
            Long.class,
            sessionId(login.cookie()));
    // 2일 전에 마지막으로 접근한 상태라 만료까지 1일 남았다
    assertThat(expiryBefore - System.currentTimeMillis())
        .isBetween(Duration.ofHours(23).toMillis(), Duration.ofHours(25).toMillis());

    Response response = client.get("/test-support/whoami", login.cookie());

    assertThat(response.status()).isEqualTo(200);
    assertThat(response.sessionCookieCount()).isEqualTo(1);
    assertThat(response.sessionCookieValue()).isEqualTo(login.cookie());
    assertThat(response.sessionCookieMaxAge()).isEqualTo(THREE_DAYS_SECONDS);
    long expiryAfter =
        jdbc.queryForObject(
            "select expiry_time from spring_session where session_id = ?",
            Long.class,
            sessionId(login.cookie()));
    // 서버 유휴 만료도 지금부터 3일 뒤로 연장됐다
    assertThat(expiryAfter - System.currentTimeMillis())
        .isBetween(Duration.ofDays(3).toMillis() - 60_000, Duration.ofDays(3).toMillis() + 60_000);
  }

  @Test
  void ordinaryRequestsKeepTheSessionIdAndTheLoginTime() throws Exception {
    Login login = login();
    String sessionId = sessionId(login.cookie());

    for (int i = 0; i < 5; i++) {
      Response response = client.get("/test-support/whoami", login.cookie());
      assertThat(response.status()).isEqualTo(200);
      assertThat(response.sessionCookieValue()).isEqualTo(login.cookie());
      clock.advance(Duration.ofHours(6));
    }

    Map<String, ? extends Session> found = sessions.findByPrincipalName(login.userId().toString());
    assertThat(found).containsOnlyKeys(sessionId);
    assertThat((Instant) found.get(sessionId).getAttribute(SessionAttributes.AUTHENTICATED_AT))
        .isEqualTo(login.authenticatedAt());
  }

  @Test
  void noRequestsForThreeDaysMakeTheCookieUseless() throws Exception {
    Login login = login();
    idleFor(login.cookie(), Duration.ofDays(3).plusHours(1));

    Response response = client.get("/test-support/whoami", login.cookie());

    assertThat(response.status()).isEqualTo(401);
    // 요청 캐시를 꺼서 만료로 인한 401 에도 익명 세션 쿠키가 생기지 않는다
    assertThat(response.sessionCookieCount()).isZero();
  }

  // ---- 절대 만료 ----

  @Test
  void keepingActiveStillExpiresThirtyDaysAfterLogin() throws Exception {
    Login login = login();

    // 2일마다 접속해도 29일째까지는 계속 인증된다 (서버 유휴 만료는 실시간 기준이라 영향이 없다)
    for (int day = 2; day <= 28; day += 2) {
      clock.set(login.authenticatedAt().plus(Duration.ofDays(day)));
      assertThat(client.get("/test-support/whoami", login.cookie()).status())
          .as("로그인 %d일째", day)
          .isEqualTo(200);
    }
    clock.set(login.authenticatedAt().plus(Duration.ofDays(30)).minusSeconds(1));
    assertThat(client.get("/test-support/whoami", login.cookie()).status()).isEqualTo(200);

    // 정확히 30일이 되면 만료된다
    clock.set(login.authenticatedAt().plus(Duration.ofDays(30)));
    Response expired = client.get("/test-support/whoami", login.cookie());

    assertThat(expired.status()).isEqualTo(401);
    assertThat(expired.body()).contains("UNAUTHORIZED");
    assertThat(sessionRows()).isZero();
    assertThat(client.get("/test-support/whoami", login.cookie()).status()).isEqualTo(401);
  }

  @Test
  void anExpiredSessionGetsOnlyTheExpiryCookie() throws Exception {
    Login login = login();
    clock.set(login.authenticatedAt().plus(Duration.ofDays(30)));

    Response expired = client.get("/test-support/whoami", login.cookie());

    assertThat(expired.status()).isEqualTo(401);
    assertThat(expired.sessionCookieCount()).isEqualTo(1);
    assertThat(expired.sessionCookieMaxAge()).isZero();
  }

  @Test
  void cookieLifetimeIsLimitedByTheTimeLeftUntilAbsoluteExpiry() throws Exception {
    Login login = login();

    clock.set(login.authenticatedAt().plus(Duration.ofDays(1)));
    assertThat(client.get("/test-support/whoami", login.cookie()).sessionCookieMaxAge())
        .isEqualTo(THREE_DAYS_SECONDS);

    // 28일째: 남은 시간 2일이 쿠키 상한 3일보다 짧다
    clock.set(login.authenticatedAt().plus(Duration.ofDays(28)));
    assertThat(client.get("/test-support/whoami", login.cookie()).sessionCookieMaxAge())
        .isEqualTo(Duration.ofDays(2).toSeconds());

    // 절대 만료 1시간 전
    clock.set(login.authenticatedAt().plus(Duration.ofDays(30)).minus(Duration.ofHours(1)));
    assertThat(client.get("/test-support/whoami", login.cookie()).sessionCookieMaxAge())
        .isEqualTo(Duration.ofHours(1).toSeconds());
  }

  @Test
  void aSessionWithoutALoginTimeIsTreatedAsExpired() throws Exception {
    Login login = login("&omitAuthenticatedAt=true");

    Response response = client.get("/test-support/whoami", login.cookie());

    assertThat(response.status()).isEqualTo(401);
    assertThat(sessionRows()).isZero();
  }

  // ---- 필터 순서 ----

  @Test
  void anExpiredSessionGets401EvenForAChangeRequestWithoutACsrfToken() throws Exception {
    Login login = login();
    clock.set(login.authenticatedAt().plus(Duration.ofDays(30)));

    Response response = client.post("/test-support/change", login.cookie());

    // 절대 만료 필터가 CSRF 필터보다 앞이라 403 이 아니라 401 이다
    assertThat(response.status()).isEqualTo(401);
    assertThat(response.body()).contains("UNAUTHORIZED");
  }

  @Test
  void aValidSessionChangeRequestWithoutACsrfTokenStillGets403() throws Exception {
    Login login = login();

    Response response = client.post("/test-support/change", login.cookie());

    assertThat(response.status()).isEqualTo(403);
    assertThat(response.body()).contains("CSRF_INVALID");
  }

  @Test
  void aPublicPathIsServedWithAnExpiredSessionAndTheSessionIsRemoved() throws Exception {
    Login login = login();
    clock.set(login.authenticatedAt().plus(Duration.ofDays(30)));

    Response response = client.get("/health", login.cookie());

    // 만료된 쿠키를 가진 브라우저도 공개 경로(예: 로그인)를 쓸 수 있어야 한다
    assertThat(response.status()).isEqualTo(200);
    assertThat(sessionRows()).isZero();
    assertThat(response.sessionCookieCount()).isEqualTo(1);
    assertThat(response.sessionCookieMaxAge()).isZero();
  }

  // ---- 응답별 쿠키 갱신 ----

  @Test
  void aResponseWithABodyRefreshesTheCookieExactlyOnce() throws Exception {
    Login login = login();

    Response response = client.get("/test-support/whoami", login.cookie());

    assertThat(response.sessionCookieCount()).isEqualTo(1);
    assertThat(response.sessionCookieValue()).isEqualTo(login.cookie());
    assertThat(response.sessionCookieMaxAge()).isEqualTo(THREE_DAYS_SECONDS);
  }

  @Test
  void a204ResponseWithoutABodyRefreshesTheCookieExactlyOnce() throws Exception {
    Login login = login();

    Response response = client.get("/test-support/no-content", login.cookie());

    // 응답이 커밋되지 않은 채 체인이 반환되는 경로
    assertThat(response.status()).isEqualTo(204);
    assertThat(response.sessionCookieCount()).isEqualTo(1);
    assertThat(response.sessionCookieValue()).isEqualTo(login.cookie());
    assertThat(response.sessionCookieMaxAge()).isEqualTo(THREE_DAYS_SECONDS);
  }

  @Test
  void failedResponsesDoNotRefreshTheCookie() throws Exception {
    Login login = login();

    Response serverError = client.get("/test-support/error", login.cookie());
    Response csrfRejected = client.post("/test-support/change", login.cookie());

    assertThat(serverError.status()).isEqualTo(500);
    assertThat(serverError.sessionCookieCount()).isZero();
    assertThat(csrfRejected.status()).isEqualTo(403);
    assertThat(csrfRejected.sessionCookieCount()).isZero();
  }

  @Test
  void anonymousRequestsNeverGetASessionCookie() throws Exception {
    Response health = client.get("/health", null);
    Response unauthenticated = client.get("/test-support/whoami", null);

    assertThat(health.status()).isEqualTo(200);
    assertThat(health.setCookies()).isEmpty();
    assertThat(unauthenticated.status()).isEqualTo(401);
    assertThat(unauthenticated.setCookies()).isEmpty();
    assertThat(sessionRows()).isZero();
  }

  @Test
  void invalidatingTheSessionInsideTheRequestLeavesOnlyTheExpiryCookie() throws Exception {
    Login login = login();

    Response response = client.get("/test-support/invalidate", login.cookie());

    // 로그아웃 응답: 만료 쿠키 하나뿐이고 갱신 쿠키가 다시 살려 놓지 않는다
    assertThat(response.status()).isEqualTo(204);
    assertThat(response.sessionCookieCount()).isEqualTo(1);
    assertThat(response.sessionCookieMaxAge()).isZero();
    assertThat(client.get("/test-support/whoami", login.cookie()).status()).isEqualTo(401);
  }

  @Test
  void rotatingTheSessionIdLeavesOnlyTheCookieIssuedByTheSessionRepository() throws Exception {
    Login login = login();

    Response response = client.get("/test-support/rotate", login.cookie());

    assertThat(response.status()).isEqualTo(200);
    assertThat(response.sessionCookieCount()).isEqualTo(1);
    String newCookie = response.sessionCookieValue();
    assertThat(newCookie).isNotEqualTo(login.cookie());
    assertThat(response.sessionCookieMaxAge()).isEqualTo(THREE_DAYS_SECONDS);
    assertThat(client.get("/test-support/whoami", newCookie).status()).isEqualTo(200);
    assertThat(client.get("/test-support/whoami", login.cookie()).status()).isEqualTo(401);
  }
}
