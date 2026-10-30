package com.mairor.backend.users.controller;

import static com.mairor.backend.testsupport.AuthFlowClient.CHROME_WINDOWS;
import static com.mairor.backend.testsupport.AuthFlowClient.SAFARI_IPHONE;
import static com.mairor.backend.testsupport.AuthFlowClient.sessionId;
import static org.assertj.core.api.Assertions.assertThat;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.AuthenticatedSessionTestConfig;
import com.mairor.backend.testsupport.MutableClock;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.session.FindByIndexNameSessionRepository;

/**
 * 로그인 기기 관리(목록·기기 하나 로그아웃·전체 로그아웃)를 실제 HTTP + PostgreSQL 로 확인한다. 쿠키·CSRF 토큰·세션 저장소가 실제로 맞물려야 확인되는
 * 동작이 많아 MockMvc 를 쓰지 않는다. 기기는 User-Agent 로 구분한다.
 */
@Import({TestcontainersConfiguration.class, AuthenticatedSessionTestConfig.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UserSessionControllerTest {

  private static final String SESSIONS = "/v1/users/me/sessions";
  private static final String PHONE = "Safari · iOS";
  private static final String TABLET = "Chrome · Windows";
  private static final long THREE_DAYS_SECONDS = Duration.ofDays(3).toSeconds();

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private MutableClock clock;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;

  private SessionTestClient raw;
  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    raw = new SessionTestClient(port);
    flow = new AuthFlowClient(raw);
    jdbc.update("delete from spring_session");
    clock.set(Instant.now());
  }

  private Response list(Login login) throws Exception {
    return flow.get(SESSIONS, login.cookie());
  }

  private static String refOf(String listBody, String device) {
    List<String> refs =
        JsonPath.read(listBody, "$.items[?(@.device == '" + device + "')].sessionRef");
    assertThat(refs).as("%s 기기의 sessionRef", device).hasSize(1);
    return refs.get(0);
  }

  private static int count(String listBody) {
    return JsonPath.read(listBody, "$.items.length()");
  }

  // ---- 목록 ----

  @Test
  void listShowsEachDeviceNewestFirstAndMarksOnlyTheRequestingOneAsCurrent() throws Exception {
    Account account = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login tablet = flow.login(account, CHROME_WINDOWS);

    Response response = list(tablet);

    assertThat(response.status()).isEqualTo(200);
    String body = response.body();
    assertThat(count(body)).isEqualTo(2);
    // 나중에 로그인한 태블릿이 앞에 온다
    assertThat((String) JsonPath.read(body, "$.items[0].device")).isEqualTo(TABLET);
    assertThat((String) JsonPath.read(body, "$.items[1].device")).isEqualTo(PHONE);
    assertThat((Boolean) JsonPath.read(body, "$.items[0].current")).isTrue();
    assertThat((Boolean) JsonPath.read(body, "$.items[1].current")).isFalse();
    assertThat((String) JsonPath.read(body, "$.items[0].createdAt")).isNotBlank();
    assertThat((String) JsonPath.read(body, "$.items[0].lastAccessedAt")).isNotBlank();
    assertThat(UUID.fromString(JsonPath.read(body, "$.items[0].sessionRef"))).isNotNull();
    // 실제 세션 ID 와 쿠키 값은 어디에도 나오지 않는다
    assertThat(body)
        .doesNotContain(phone.cookie())
        .doesNotContain(tablet.cookie())
        .doesNotContain(sessionId(phone.cookie()))
        .doesNotContain(sessionId(tablet.cookie()));
    assertThat(body).doesNotContain("ip").doesNotContain("userAgent");
  }

  @Test
  void listOnlyContainsMyOwnDevices() throws Exception {
    Account mine = flow.signUp();
    Account other = flow.signUp();
    Login myLogin = flow.login(mine, CHROME_WINDOWS);
    flow.login(other, SAFARI_IPHONE);

    String body = list(myLogin).body();

    assertThat(count(body)).isEqualTo(1);
    assertThat((String) JsonPath.read(body, "$.items[0].device")).isEqualTo(TABLET);
  }

  @Test
  void listLeavesOutSessionsThatAreNotUsableDevices() throws Exception {
    Account account = flow.signUp();
    Login tablet = flow.login(account, CHROME_WINDOWS);
    Login idleExpired = flow.login(account, SAFARI_IPHONE);
    jdbc.update(
        "update spring_session set last_access_time = last_access_time - ? where session_id = ?",
        Duration.ofDays(4).toMillis(),
        sessionId(idleExpired.cookie()));
    // 기기 정보 없이 만들어진 세션(로그인 API 를 거치지 않은 세션)
    raw.post("/test-support/login?userId=" + account.userId(), null);

    String body = list(tablet).body();

    assertThat(count(body)).isEqualTo(1);
    assertThat((String) JsonPath.read(body, "$.items[0].device")).isEqualTo(TABLET);
  }

  @Test
  void listLeavesOutADeviceWhoseLoginIsOlderThanThirtyDays() throws Exception {
    Account account = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    clock.set(clock.instant().plus(Duration.ofDays(29)));
    Login tablet = flow.login(account, CHROME_WINDOWS);
    clock.set(clock.instant().plus(Duration.ofDays(1)));
    assertThat(phone.cookie()).isNotBlank();

    String body = list(tablet).body();

    // 폰은 30일이 지나 절대 만료됐고 태블릿만 남는다
    assertThat(count(body)).isEqualTo(1);
    assertThat((String) JsonPath.read(body, "$.items[0].device")).isEqualTo(TABLET);
  }

  @Test
  void listNeedsALogin() throws Exception {
    Response response = flow.get(SESSIONS, null);

    assertThat(response.status()).isEqualTo(401);
    assertThat(response.body()).contains("UNAUTHORIZED");
  }

  // ---- 기기 하나 로그아웃 ----

  @Test
  void anotherDeviceCanBeLoggedOutWhileTheCurrentOneStaysLoggedIn() throws Exception {
    Account account = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login tablet = flow.login(account, CHROME_WINDOWS);
    String phoneRef = refOf(list(tablet).body(), PHONE);

    Response revoke = flow.delete(SESSIONS + "/" + phoneRef, tablet.cookie(), tablet.csrfToken());

    assertThat(revoke.status()).isEqualTo(204);
    // 현재 기기는 그대로 유지되고 쿠키도 평소처럼 정확히 한 번 갱신된다
    assertThat(revoke.sessionCookieCount()).isEqualTo(1);
    assertThat(revoke.sessionCookieValue()).isEqualTo(tablet.cookie());
    assertThat(revoke.sessionCookieMaxAge()).isEqualTo(THREE_DAYS_SECONDS);
    assertThat(flow.get("/v1/users/me", phone.cookie()).status()).isEqualTo(401);
    assertThat(flow.get("/v1/users/me", tablet.cookie()).status()).isEqualTo(200);
    assertThat(count(list(tablet).body())).isEqualTo(1);
  }

  @Test
  void aDeviceCanLogItselfOutByItsOwnReference() throws Exception {
    Account account = flow.signUp();
    Login tablet = flow.login(account, CHROME_WINDOWS);
    String ownRef = refOf(list(tablet).body(), TABLET);

    Response revoke = flow.delete(SESSIONS + "/" + ownRef, tablet.cookie(), tablet.csrfToken());

    // 로그아웃과 같다: 만료 쿠키 하나뿐이고 이후 쿠키는 쓸 수 없다
    assertThat(revoke.status()).isEqualTo(204);
    assertThat(revoke.sessionCookieCount()).isEqualTo(1);
    assertThat(revoke.sessionCookieMaxAge()).isZero();
    assertThat(flow.get("/v1/users/me", tablet.cookie()).status()).isEqualTo(401);
  }

  @Test
  void unknownMalformedOrAlreadyEndedReferencesAreAll404() throws Exception {
    Account account = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login tablet = flow.login(account, CHROME_WINDOWS);
    String phoneRef = refOf(list(tablet).body(), PHONE);
    assertThat(flow.delete(SESSIONS + "/" + phoneRef, tablet.cookie(), tablet.csrfToken()).status())
        .isEqualTo(204);

    for (String ref : new String[] {UUID.randomUUID().toString(), "not-a-uuid", phoneRef}) {
      Response response = flow.delete(SESSIONS + "/" + ref, tablet.cookie(), tablet.csrfToken());
      assertThat(response.status()).as("sessionRef=%s", ref).isEqualTo(404);
      assertThat(response.body()).contains("NOT_FOUND");
    }
    assertThat(phone.cookie()).isNotBlank();
  }

  @Test
  void anotherUsersDeviceCannotBeLoggedOut() throws Exception {
    Account mine = flow.signUp();
    Account other = flow.signUp();
    Login myLogin = flow.login(mine, CHROME_WINDOWS);
    Login otherLogin = flow.login(other, SAFARI_IPHONE);
    String otherRef = refOf(list(otherLogin).body(), PHONE);

    Response response =
        flow.delete(SESSIONS + "/" + otherRef, myLogin.cookie(), myLogin.csrfToken());

    // 없는 값과 구분되지 않는 404 이고 상대방의 세션은 그대로다
    assertThat(response.status()).isEqualTo(404);
    assertThat(flow.get("/v1/users/me", otherLogin.cookie()).status()).isEqualTo(200);
    assertThat(sessions.findByPrincipalName(other.userId().toString())).hasSize(1);
  }

  @Test
  void loggingOutADeviceNeedsTheCsrfToken() throws Exception {
    Account account = flow.signUp();
    flow.login(account, SAFARI_IPHONE);
    Login tablet = flow.login(account, CHROME_WINDOWS);
    String phoneRef = refOf(list(tablet).body(), PHONE);

    Response noToken = flow.delete(SESSIONS + "/" + phoneRef, tablet.cookie(), null);
    Response wrongToken = flow.delete(SESSIONS + "/" + phoneRef, tablet.cookie(), "wrong-token");
    Response noSession = flow.delete(SESSIONS + "/" + phoneRef, null, null);

    assertThat(noToken.status()).isEqualTo(403);
    assertThat(noToken.body()).contains("CSRF_INVALID");
    assertThat(wrongToken.status()).isEqualTo(403);
    assertThat(noSession.status()).isEqualTo(403);
    // 거절됐으므로 폰의 세션은 그대로 있다
    assertThat(count(list(tablet).body())).isEqualTo(2);
  }

  // ---- 전체 로그아웃 ----

  @Test
  void loggingOutEverywhereEndsEveryDeviceIncludingTheCurrentOne() throws Exception {
    Account account = flow.signUp();
    Account other = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login tablet = flow.login(account, CHROME_WINDOWS);
    Login second = flow.login(account, CHROME_WINDOWS);
    Login otherLogin = flow.login(other, SAFARI_IPHONE);
    // 기기 정보가 없는 세션도 함께 지워진다
    raw.post("/test-support/login?userId=" + account.userId(), null);
    assertThat(sessions.findByPrincipalName(account.userId().toString())).hasSize(4);

    Response response = flow.delete(SESSIONS, tablet.cookie(), tablet.csrfToken());

    assertThat(response.status()).isEqualTo(204);
    // 현재 기기를 포함해 모두 끝나고, 만료 쿠키 하나만 내려가 갱신 쿠키가 되살리지 않는다
    assertThat(response.sessionCookieCount()).isEqualTo(1);
    assertThat(response.sessionCookieMaxAge()).isZero();
    for (Login login : List.of(phone, tablet, second)) {
      assertThat(flow.get("/v1/users/me", login.cookie()).status()).isEqualTo(401);
    }
    assertThat(sessions.findByPrincipalName(account.userId().toString())).isEmpty();
    // 다른 회원은 영향이 없다
    assertThat(flow.get("/v1/users/me", otherLogin.cookie()).status()).isEqualTo(200);
  }

  /**
   * 한 기기를 지우는 데 실패해도 현재 기기는 먼저 지워지지 않아서, 같은 기기에서 같은 요청을 다시 보내 마무리할 수 있다. 실패한 기기 하나만 남고 나머지는 이미
   * 끊긴다(전체 삭제는 원자적이지 않다).
   */
  @Test
  void loggingOutEverywhereThatFailsHalfwayKeepsTheCurrentDeviceSoItCanBeRetried()
      throws Exception {
    Account account = flow.signUp();
    Login blocked = flow.login(account, SAFARI_IPHONE);
    Login current = flow.login(account, CHROME_WINDOWS);
    Login third = flow.login(account, CHROME_WINDOWS);
    blockDeletingSession(sessionId(blocked.cookie()));
    Response failed;
    try {
      failed = flow.delete(SESSIONS, current.cookie(), current.csrfToken());
    } finally {
      unblockDeletingSessions();
    }

    assertThat(failed.status()).isEqualTo(500);
    assertThat(failed.sessionCookieCount()).isZero();
    // 현재 기기는 그대로이고, 지울 수 있던 기기는 끊겼고, 실패한 기기만 남았다
    assertThat(flow.get("/v1/users/me", current.cookie()).status()).isEqualTo(200);
    assertThat(flow.get("/v1/users/me", third.cookie()).status()).isEqualTo(401);
    assertThat(flow.get("/v1/users/me", blocked.cookie()).status()).isEqualTo(200);

    // 현재 기기에서 같은 요청을 다시 보내면 나머지가 끊기고 현재 기기도 로그아웃된다
    Login again = new Login(failed, current.cookie(), current.csrfToken());
    Response retry = flow.delete(SESSIONS, again.cookie(), again.csrfToken());

    assertThat(retry.status()).isEqualTo(204);
    for (Login login : List.of(blocked, current, third)) {
      assertThat(flow.get("/v1/users/me", login.cookie()).status()).isEqualTo(401);
    }
    assertThat(sessions.findByPrincipalName(account.userId().toString())).isEmpty();
  }

  /** 이 세션 ID 의 행을 지우려 하면 DB 가 오류를 내게 한다(삭제 실패 주입). */
  private void blockDeletingSession(String sessionId) {
    jdbc.execute(
        """
        create or replace function mairor_block_session_delete() returns trigger as $$
        begin
          if OLD.session_id = TG_ARGV[0] then
            raise exception 'blocked by test';
          end if;
          return OLD;
        end $$ language plpgsql""");
    jdbc.execute(
        "create trigger mairor_block_session_delete before delete on spring_session "
            + "for each row execute function mairor_block_session_delete('"
            + sessionId.replace("'", "''")
            + "')");
  }

  private void unblockDeletingSessions() {
    jdbc.execute("drop trigger if exists mairor_block_session_delete on spring_session");
  }

  @Test
  void loggingOutEverywhereNeedsTheCsrfToken() throws Exception {
    Account account = flow.signUp();
    Login tablet = flow.login(account, CHROME_WINDOWS);

    Response noToken = flow.delete(SESSIONS, tablet.cookie(), null);
    Response noSession = flow.delete(SESSIONS, null, null);

    assertThat(noToken.status()).isEqualTo(403);
    assertThat(noToken.body()).contains("CSRF_INVALID");
    assertThat(noSession.status()).isEqualTo(403);
    assertThat(flow.get("/v1/users/me", tablet.cookie()).status()).isEqualTo(200);
  }

  @Test
  void loggingOutEverywhereWhileAnotherDeviceKeepsRequestingEndsCleanly() throws Exception {
    Account account = flow.signUp();
    Login phone = flow.login(account, SAFARI_IPHONE);
    Login tablet = flow.login(account, CHROME_WINDOWS);
    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch go = new CountDownLatch(1);
    try {
      Future<List<Integer>> phoneRequests =
          pool.submit(
              () -> {
                go.await();
                List<Integer> statuses = new ArrayList<>();
                for (int i = 0; i < 25; i++) {
                  statuses.add(flow.get("/v1/users/me", phone.cookie()).status());
                }
                return statuses;
              });
      Future<Integer> logoutEverywhere =
          pool.submit(
              () -> {
                go.await();
                return flow.delete(SESSIONS, tablet.cookie(), tablet.csrfToken()).status();
              });
      go.countDown();

      // 진행 중이던 요청은 200 이거나 401 이고, 서버 오류는 없다
      assertThat(logoutEverywhere.get(60, TimeUnit.SECONDS)).isEqualTo(204);
      assertThat(phoneRequests.get(60, TimeUnit.SECONDS)).isSubsetOf(200, 401);
    } finally {
      pool.shutdownNow();
    }

    // 경합이 끝난 뒤에는 어느 쿠키도 쓸 수 없고 되살아난 세션도 없다
    assertThat(flow.get("/v1/users/me", phone.cookie()).status()).isEqualTo(401);
    assertThat(flow.get("/v1/users/me", tablet.cookie()).status()).isEqualTo(401);
    assertThat(sessions.findByPrincipalName(account.userId().toString())).isEmpty();
  }

  @Test
  void afterLoggingOutEverywhereTheSameAccountCanLogInAgain() throws Exception {
    Account account = flow.signUp();
    Login tablet = flow.login(account, CHROME_WINDOWS);
    flow.delete(SESSIONS, tablet.cookie(), tablet.csrfToken());

    Login again = flow.login(account, CHROME_WINDOWS);

    assertThat(flow.get("/v1/users/me", again.cookie()).status()).isEqualTo(200);
    assertThat(count(list(again).body())).isEqualTo(1);
  }
}
