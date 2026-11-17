package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.AuthenticatedSessionTestConfig;
import com.mairor.backend.testsupport.RedisSessionStore;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Base64;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.RedisSystemException;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.session.data.redis.RedisIndexedSessionRepository;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

/**
 * 세션 저장소(Redis)가 실패할 때 실제 HTTP 응답이 공통 오류 형식으로 나가는지 확인한다. 장애의 종류를 구분해서 만든다.
 *
 * <ul>
 *   <li><b>일시적 장애</b>(Redis 연결 실패): {@code 503 SERVICE_UNAVAILABLE}. 인증 실패(401)가 아니다.
 *   <li><b>서버 문제</b>(그 밖의 Redis 오류): {@code 500 INTERNAL_ERROR}. 503 이 아니다.
 *   <li><b>손상된 세션</b>(저장된 값을 읽지 못함): {@code 401} 과 쿠키 만료.
 *   <li><b>저장할 수 없는 값</b>(직렬화 실패, 서버 버그): {@code 500}. "로그인 만료"(401)로 보이면 안 된다.
 * </ul>
 *
 * 어느 쪽이든 세션을 저장하지 못했는데 로그인 성공이 나가거나, 지우지 못했는데 로그아웃 성공(204)이 나가지 않아야 한다. 장애는 세션 저장소 빈을 감싸서 조회·저장·삭제
 * 중 하나가 예외를 던지게 만든다.
 */
@Import({TestcontainersConfiguration.class, AuthenticatedSessionTestConfig.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionStoreFailureTest {

  @LocalServerPort private int port;
  @Autowired private RedisSessionStore sessionStore;
  @MockitoSpyBean private RedisIndexedSessionRepository sessions;
  @Autowired private MeterRegistry registry;

  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    flow = new AuthFlowClient(new SessionTestClient(port));
    sessionStore.clear();
  }

  // ---- 장애 만들기 ----

  private static RedisConnectionFailureException down() {
    return new RedisConnectionFailureException("Redis 연결 실패(테스트가 주입)");
  }

  private static RedisSystemException broken() {
    return new RedisSystemException("Redis 오류(테스트가 주입)", new IllegalStateException());
  }

  private void failReads(RuntimeException e) {
    doThrow(e).when(sessions).findById(anyString());
  }

  private void failSaves(RuntimeException e) {
    doThrow(e).when(sessions).save(any());
  }

  private void failDeletes(RuntimeException e) {
    doThrow(e).when(sessions).deleteById(anyString());
  }

  private void corruptSecurityContext(Login login) {
    String sessionId = new String(Base64.getDecoder().decode(login.cookie()));
    sessionStore.corruptAttribute(
        sessionId, HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
  }

  // ---- 응답 확인 ----

  private static void assertServiceUnavailable(Response response) {
    assertThat(response.status()).isEqualTo(503);
    assertThat(response.body())
        .contains("\"code\":\"SERVICE_UNAVAILABLE\"")
        .doesNotContain("<html");
  }

  private static void assertServerError(Response response) {
    assertThat(response.status()).isEqualTo(500);
    assertThat(response.body()).contains("\"code\":\"INTERNAL_ERROR\"").doesNotContain("<html");
  }

  private double failures(String cause) {
    var counter = registry.find("mairor.session.failures").tag("cause", cause).counter();
    return counter == null ? 0 : counter.count();
  }

  /**
   * 세션은 속성을 바꿀 때 바로 저장되므로, 마지막 저장만 실패한 로그인은 저장소에 세션을 남길 수 있다. 쿠키를 받지 못했으니 그 세션은 쓸 수 없고, 장애가 끝난 뒤의
   * 로그인이 계정당 세션 1개 규칙으로 함께 지운다.
   */
  private void assertTheNextLoginLeavesOnlyItsOwnSession(Account account) throws Exception {
    Login again = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    assertThat(flow.me(again.cookie()).status()).isEqualTo(200);
    assertThat(sessions.findByPrincipalName(account.userId().toString()))
        .containsOnlyKeys(new String(Base64.getDecoder().decode(again.cookie())));
  }

  // ---- 조회 실패 ----

  @Test
  void whenTheStoreIsUnreachableTheAnswerIs503NotAnUnauthenticated401() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    failReads(down());
    Response whileDown = flow.me(login.cookie());
    reset(sessions);

    assertServiceUnavailable(whileDown);
    assertThat(whileDown.sessionCookieCount()).isZero();
    // 장애가 끝나면 같은 쿠키로 그대로 이용할 수 있다(세션을 잃지 않았다)
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  @Test
  void aStoreErrorThatIsNotAnOutageIsAServerError() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    failReads(broken());
    Response broken = flow.me(login.cookie());
    reset(sessions);

    assertServerError(broken);
    assertThat(broken.sessionCookieCount()).isZero();
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  // ---- 저장 실패 ----

  @Test
  void aLoginWhoseSessionCannotBeSavedBecauseTheStoreIsDownDoesNotAnswerSuccess() throws Exception {
    Account account = flow.signUp();
    failSaves(down());
    Response failed =
        flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);
    reset(sessions);

    assertServiceUnavailable(failed);
    assertThat(failed.body()).doesNotContain("csrfToken");
    assertThat(failed.sessionCookieValue()).isNull();
    assertTheNextLoginLeavesOnlyItsOwnSession(account);
  }

  @Test
  void aLoginWhoseSessionCannotBeSavedBecauseOfAGeneralErrorIsAServerError() throws Exception {
    Account account = flow.signUp();
    failSaves(broken());
    Response failed =
        flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);
    reset(sessions);

    assertServerError(failed);
    assertThat(failed.body()).doesNotContain("csrfToken");
    assertThat(failed.sessionCookieValue()).isNull();
    assertTheNextLoginLeavesOnlyItsOwnSession(account);
  }

  @Test
  void aRequestWhoseSessionUpdateCannotBeSavedBecauseTheStoreIsDownAnswers503() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    failSaves(down());
    Response failed = flow.me(login.cookie());
    reset(sessions);

    assertServiceUnavailable(failed);
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  // ---- 삭제 실패 ----

  /** 컨트롤러 안에서 세션을 지우다 실패한다(MVC 예외 처리). 일시 장애면 503 이다. */
  @Test
  void aLogoutWhoseSessionCannotBeDeletedBecauseTheStoreIsDownIs503() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    failDeletes(down());
    Response failed = flow.logout(login.cookie(), login.csrfToken());
    reset(sessions);

    assertServiceUnavailable(failed);
    // 로그아웃이 끝나지 않았으므로 세션은 살아 있고, 다시 로그아웃할 수 있다
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
    assertThat(flow.logout(login.cookie(), login.csrfToken()).status()).isEqualTo(204);
    assertThat(flow.me(login.cookie()).status()).isEqualTo(401);
  }

  @Test
  void aLogoutWhoseSessionCannotBeDeletedBecauseOfAGeneralErrorIsAServerError() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    failDeletes(broken());
    Response failed = flow.logout(login.cookie(), login.csrfToken());
    reset(sessions);

    assertServerError(failed);
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  // ---- 읽을 수 없는 세션과 저장할 수 없는 값 ----

  @Test
  void aSessionThatCannotBeReadBackIsAnsweredWith401AndItsCookieIsExpired() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    corruptSecurityContext(login);

    Response broken = flow.me(login.cookie());

    assertThat(broken.status()).isEqualTo(401);
    assertThat(broken.body()).contains("\"code\":\"UNAUTHORIZED\"");
    // 같은 쿠키로 계속 실패하지 않게 브라우저가 쿠키를 버린다
    assertThat(broken.sessionCookieCount()).isEqualTo(1);
    assertThat(broken.sessionCookieMaxAge()).isZero();
    // 쿠키 없이 다시 로그인하면 된다
    Login again = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    assertThat(flow.me(again.cookie()).status()).isEqualTo(200);
  }

  /**
   * 저장된 세션을 읽지 못하는 것(역직렬화)과 새 속성을 저장하지 못하는 것(직렬화)은 같은 예외 종류로 나오지만 뜻이 다르다. 앞은 사용자의 세션이 못 쓰게 된 것이라 다시
   * 로그인하게 하고, 뒤는 서버 버그라서 "로그인 만료"로 보이면 안 된다.
   */
  @Test
  void aSessionAttributeThatCannotBeSerializedIsAServerErrorNotAnExpiredLogin() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);

    Response failed = flow.get("/test-support/unserializable", login.cookie());

    assertServerError(failed);
    // 쿠키를 만료시키지 않고, 기존 세션은 그대로 쓸 수 있다
    assertThat(failed.sessionCookieCount()).isZero();
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  // ---- 지표 ----

  @Test
  void failuresAreCountedByTheirCause() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    double storeBefore = failures("store_unavailable");
    double unexpectedBefore = failures("unexpected");
    double corruptedBefore = failures("corrupted_session");

    failReads(down());
    flow.me(login.cookie());
    reset(sessions);
    flow.get("/test-support/unserializable", login.cookie());
    corruptSecurityContext(login);
    flow.me(login.cookie());

    assertThat(failures("store_unavailable")).isEqualTo(storeBefore + 1);
    assertThat(failures("unexpected")).isEqualTo(unexpectedBefore + 1);
    assertThat(failures("corrupted_session")).isEqualTo(corruptedBefore + 1);
  }

  // ---- 장애 중에도 세션과 무관한 요청은 정상 ----

  @Test
  void requestsThatDoNotTouchTheSessionStoreAreUnaffected() throws Exception {
    failReads(down());
    failSaves(down());
    failDeletes(down());

    assertThat(flow.get("/health", null).status()).isEqualTo(200);
  }
}
