package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.RedisSessionStore;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.service.SessionEstablisher;
import com.mairor.backend.users.service.UserSessionService;
import com.mairor.backend.users.support.LoginMetrics;
import java.time.Clock;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.invocation.InvocationOnMock;
import org.mockito.stubbing.Answer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

/**
 * 비밀번호 재설정과 로그인이 겹칠 때 재설정 이후에 살아 있는 세션이 생기지 않는지 실제 HTTP + PostgreSQL 로 확인한다.
 *
 * <p>재설정 API(010)가 하는 일을 같은 순서로 직접 한다: 새 해시와 버전을 먼저 커밋하고({@code updatePassword}), 그다음 이 회원의 모든 세션을
 * 끊는다({@code revokeAll}). 로그인 요청을 세션 발급 직전(A)이나 재확인 직후(B)에 멈추게 해서 겹침을 만든다. 스레드 사이 순서를 래치로 고정해서 시간에
 * 기대지 않는다.
 *
 * <ul>
 *   <li>A: 옛 비밀번호로 검증을 마친 로그인이 재설정이 끝난 뒤 세션을 발급하려 한다 → 세션을 버리고 401
 *   <li>B: 로그인이 버전을 다시 읽은 뒤 응답을 커밋하기 전에 재설정이 끝난다 → 그 로그인의 세션도 {@code revokeAll} 이 끊어야 한다. 세션이 아직
 *       저장돼 있지 않으면 목록에 없어서 살아남는다.
 *   <li>C: 버전을 다시 읽는 데 실패하면 만들어 둔 세션과 인증 상태를 버리고 실패 처리한다
 * </ul>
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PasswordChangeLoginRaceTest {

  private static final String NEW_PASSWORD = "NewPassw0rd!2026";

  /** 멈춰 세운 쪽이 닿았다고 알리고({@code reached}), 풀어 줄 때까지 기다린다({@code release}). */
  private static final class Gate {
    final CountDownLatch reached = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);
  }

  @LocalServerPort private int port;
  @Autowired private RedisSessionStore sessionStore;
  @Autowired private PasswordEncoder passwordEncoder;
  @Autowired private UserSessionService userSessionService;
  @Autowired private Clock clock;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;

  /**
   * 저장소는 스텁(던지기·돌려주기)에만 쓴다. 스프링 데이터 저장소는 인터페이스 프록시라서 스텁한 메서드 안에서 {@code callRealMethod()} 를 부를 수
   * 없고, 멈춤 지점은 구체 클래스(아래 두 스파이)에 둔다.
   */
  @MockitoSpyBean private UserRepository userRepository;

  /** A 의 멈춤 지점: 비밀번호 확인을 마치고 세션을 발급하기 직전. */
  @MockitoSpyBean private SessionEstablisher sessionEstablisher;

  /** B 의 멈춤 지점: 세션 발급과 버전 재확인을 마치고 성공을 세는 순간. 응답은 아직 커밋되지 않았다. */
  @MockitoSpyBean private LoginMetrics loginMetrics;

  private AuthFlowClient flow;
  private ExecutorService pool;
  private final AtomicReference<Gate> gate = new AtomicReference<>();

  /** 문이 열려 있으면 한 번만 멈춘 뒤 진짜 메서드를 부른다. */
  private Object pauseOnce(InvocationOnMock invocation) throws Throwable {
    Gate current = gate.getAndSet(null);
    if (current != null) {
      current.reached.countDown();
      assertThat(current.release.await(30, TimeUnit.SECONDS)).as("테스트가 풀어 주어야 한다").isTrue();
    }
    return invocation.callRealMethod();
  }

  private final Answer<Object> pauseBeforeEstablishing = this::pauseOnce;

  /** 성공을 세는 순간에만 멈춘다. 다른 결과를 세는 호출은 그대로 지나간다. */
  private final Answer<Object> pauseWhenCountingSuccess =
      invocation ->
          invocation.getArgument(0) == LoginMetrics.Result.SUCCESS
              ? pauseOnce(invocation)
              : invocation.callRealMethod();

  @BeforeEach
  void setUp() {
    flow = new AuthFlowClient(new SessionTestClient(port));
    pool = Executors.newCachedThreadPool();
    sessionStore.clear();
  }

  @AfterEach
  void tearDown() {
    Gate leftover = gate.getAndSet(null);
    if (leftover != null) {
      leftover.release.countDown();
    }
    pool.shutdownNow();
  }

  private Gate armGate() {
    Gate armed = new Gate();
    gate.set(armed);
    return armed;
  }

  /** 재설정 API(010)가 할 일: 새 해시와 버전을 커밋한 뒤 모든 세션을 끊는다. */
  private void resetPassword(Account account) {
    userRepository.updatePassword(
        account.userId(), passwordEncoder.encode(NEW_PASSWORD), clock.instant());
    userSessionService.revokeAll(account.userId());
  }

  private Future<Response> loginInBackground(Account account) {
    return pool.submit(
        () ->
            flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS));
  }

  private void assertNoLiveSession(Account account, Response response) throws Exception {
    assertThat(sessions.findByPrincipalName(account.userId().toString())).isEmpty();
    if (response.sessionCookieValue() != null) {
      assertThat(flow.me(response.sessionCookieValue()).status()).isEqualTo(401);
    }
  }

  // ---- A: 옛 비밀번호로 검증한 로그인이 재설정 뒤에 세션을 발급하려 한다 ----

  @Test
  void aLoginThatVerifiedTheOldPasswordCannotStartASessionAfterTheReset() throws Exception {
    Account account = flow.signUp();
    Gate paused = armGate();
    doAnswer(pauseBeforeEstablishing).when(sessionEstablisher).establish(any(), any(), any());

    Future<Response> login = loginInBackground(account);
    assertThat(paused.reached.await(30, TimeUnit.SECONDS)).isTrue();
    // 로그인은 옛 해시를 읽었다. 그 사이에 재설정이 끝난다
    resetPassword(account);
    paused.release.countDown();

    Response response = login.get(30, TimeUnit.SECONDS);
    assertThat(response.status()).isEqualTo(401);
    assertThat(response.body()).contains("USERS_INVALID_CREDENTIALS");
    assertNoLiveSession(account, response);
  }

  // ---- B: 재확인을 마친 로그인이 응답을 커밋하기 전에 재설정이 끝난다 ----

  @Test
  void aSessionIssuedByALoginThatOverlapsTheResetIsEndedByTheResetsRevokeAll() throws Exception {
    Account account = flow.signUp();
    Gate paused = armGate();
    doAnswer(pauseWhenCountingSuccess).when(loginMetrics).record(any());

    Future<Response> login = loginInBackground(account);
    assertThat(paused.reached.await(30, TimeUnit.SECONDS)).isTrue();
    // 로그인은 옛 버전을 읽어 통과했고 아직 응답을 커밋하지 않았다. 그 사이에 재설정이 끝난다
    resetPassword(account);
    paused.release.countDown();

    Response response = login.get(30, TimeUnit.SECONDS);
    // 로그인 응답은 이미 정해졌더라도, 그 세션은 살아 있으면 안 된다
    assertNoLiveSession(account, response);
  }

  // ---- C: 버전을 다시 읽는 데 실패한다 ----

  @Test
  void aUserWhoDisappearedBeforeTheRecheckFailsTheLoginWithoutASession() throws Exception {
    Account account = flow.signUp();
    doReturn(Optional.empty()).when(userRepository).findPasswordVersionById(any());

    Response response =
        flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);

    assertThat(response.status()).isEqualTo(401);
    assertThat(response.body()).contains("USERS_INVALID_CREDENTIALS");
    assertNoLiveSession(account, response);
  }

  @Test
  void aTemporaryDatabaseFailureDuringTheRecheckIsServiceUnavailableWithoutASession()
      throws Exception {
    Account account = flow.signUp();
    doThrow(new DataAccessResourceFailureException("db down"))
        .when(userRepository)
        .findPasswordVersionById(any());

    Response response =
        flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);

    assertThat(response.status()).isEqualTo(503);
    assertThat(response.body()).contains("SERVICE_UNAVAILABLE");
    assertNoLiveSession(account, response);
  }

  @Test
  void anInternalErrorDuringTheRecheckIsInternalErrorWithoutASession() throws Exception {
    Account account = flow.signUp();
    doThrow(new IllegalStateException("boom")).when(userRepository).findPasswordVersionById(any());

    Response response =
        flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);

    assertThat(response.status()).isEqualTo(500);
    assertThat(response.body()).contains("INTERNAL_ERROR");
    assertNoLiveSession(account, response);
  }

  @Test
  void failedRechecksAreNotCountedAsWrongPasswordsAndTheNextLoginWorks() throws Exception {
    Account account = flow.signUp();
    doThrow(new IllegalStateException("boom")).when(userRepository).findPasswordVersionById(any());
    // 로그인 실패 한도(테스트 설정 3회)보다 많이 겪어도 잠기지 않는다
    for (int i = 0; i < 5; i++) {
      Response failed =
          flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);
      assertThat(failed.status()).isEqualTo(500);
    }
    reset(userRepository);

    AuthFlowClient.Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);

    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
    assertThat(sessions.findByPrincipalName(account.userId().toString())).hasSize(1);
  }

  @Test
  void aLoginWithoutAnyOverlapKeepsItsSession() throws Exception {
    Account account = flow.signUp();

    AuthFlowClient.Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);

    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
    assertThat(sessions.findByPrincipalName(account.userId().toString())).hasSize(1);
  }
}
