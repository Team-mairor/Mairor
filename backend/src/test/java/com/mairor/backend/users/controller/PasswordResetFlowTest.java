package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.RecordingSessionEndHook;
import com.mairor.backend.testsupport.RecordingSessionEndHookConfig;
import com.mairor.backend.testsupport.RedisSessionStore;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import com.mairor.backend.users.VerificationTestSupport.CapturingMailSender;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.PasswordResetLocks;
import com.mairor.backend.users.support.VerificationCodeGenerator;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.invocation.InvocationOnMock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

/**
 * 새 비밀번호 저장(API-USERS-010)이 세션·로그인·동시 요청과 어떻게 맞물리는지 실제 HTTP + PostgreSQL 로 확인한다.
 *
 * <p>세션 쿠키가 응답을 커밋할 때 다시 저장되는지 같은 문제는 실제 HTTP 에서만 드러나서 MockMvc 로 보지 않는다. 같은 이메일로 인증번호를 여러 번 받아야 해서
 * 재발송 간격은 0 으로 둔다. 스레드 사이 순서는 래치로 고정해서 시간에 기대지 않는다.
 */
@Import({
  TestcontainersConfiguration.class,
  RecordingSessionEndHookConfig.class,
  PasswordResetFlowTest.CapturingMail.class
})
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
      "app.rate-limit.password-reset.limit=1000",
      "app.password-reset.resend-cooldown=0s",
      "app.password-reset.hourly-limit=1000"
    })
@ExtendWith(OutputCaptureExtension.class)
class PasswordResetFlowTest {

  private static final String NEW_PASSWORD = "NewPassw0rd!2026";
  private static final String NEWER_PASSWORD = "Newer-Passw0rd!26";
  private static final Pattern TOKEN = Pattern.compile("\"resetToken\"\\s*:\\s*\"([^\"]+)\"");

  @TestConfiguration(proxyBeanMethods = false)
  static class CapturingMail {

    @Bean
    @Primary
    CapturingMailSender capturingMailSender() {
      return new CapturingMailSender();
    }
  }

  /** 멈춰 세운 쪽이 닿았다고 알리고({@code reached}), 풀어 줄 때까지 기다린다({@code release}). */
  private static final class Gate {
    final CountDownLatch reached = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);
  }

  @LocalServerPort private int port;
  @Autowired private RedisSessionStore sessionStore;
  @Autowired private CapturingMailSender mail;
  @Autowired private RecordingSessionEndHook hook;
  @Autowired private MeterRegistry registry;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;
  @Autowired private UserRepository userRepository;

  /** 멈춤 지점: 새 비밀번호 해시 계산(잠금 안). */
  @MockitoSpyBean private PasswordEncoder passwordEncoder;

  /** 멈춤 지점: 잠금을 잡기 직전(토큰 조회는 끝남). */
  @MockitoSpyBean private PasswordResetLocks locks;

  /** 멈춤 지점: 인증번호 발송의 인증번호 생성(잠금 안). */
  @MockitoSpyBean private VerificationCodeGenerator codeGenerator;

  private SessionTestClient client;
  private AuthFlowClient flow;
  private ExecutorService pool;
  private final AtomicReference<Gate> gate = new AtomicReference<>();

  @BeforeEach
  void setUp() {
    client = new SessionTestClient(port);
    flow = new AuthFlowClient(client);
    pool = Executors.newCachedThreadPool();
    hook.reset();
    sessionStore.clear();
  }

  @AfterEach
  void tearDown() {
    Gate leftover = gate.getAndSet(null);
    if (leftover != null) {
      leftover.release.countDown();
    }
    hook.reset();
    pool.shutdownNow();
  }

  // ---- 도구 ----

  private Gate armGate() {
    Gate armed = new Gate();
    gate.set(armed);
    return armed;
  }

  /** 문이 열려 있으면 한 번만 멈춘 뒤 진짜 메서드를 부른다. */
  private Object pauseOnce(InvocationOnMock invocation) throws Throwable {
    Gate current = gate.getAndSet(null);
    if (current != null) {
      current.reached.countDown();
      assertThat(current.release.await(30, TimeUnit.SECONDS)).as("테스트가 풀어 주어야 한다").isTrue();
    }
    return invocation.callRealMethod();
  }

  private Map<String, String> origin() {
    return Map.of("Origin", AuthFlowClient.ORIGIN);
  }

  private String requestCode(String email) throws Exception {
    Response sent =
        client.postJson(
            "/v1/users/password-reset", "{\"email\": \"" + email + "\"}", null, origin());
    assertThat(sent.status()).as("인증번호 발송: %s", sent.body()).isEqualTo(202);
    List<CapturingMailSender.Mail> mine =
        mail.resetCodes.stream().filter(m -> m.to().equals(email)).toList();
    return mine.get(mine.size() - 1).code();
  }

  private Response verify(String email, String code) throws Exception {
    return client.postJson(
        "/v1/users/password-reset/verification",
        "{\"email\": \"" + email + "\", \"code\": \"" + code + "\"}",
        null,
        origin());
  }

  private String tokenFor(String email) throws Exception {
    Response verified = verify(email, requestCode(email));
    assertThat(verified.status()).as("인증번호 확인: %s", verified.body()).isEqualTo(200);
    Matcher matcher = TOKEN.matcher(verified.body());
    assertThat(matcher.find()).isTrue();
    return matcher.group(1);
  }

  private Response save(String token, String password, String cookie) throws Exception {
    return client.call(
        "PUT",
        "/v1/users/password-reset/password",
        "{\"resetToken\": \"%s\", \"newPassword\": \"%s\", \"newPasswordConfirm\": \"%s\"}"
            .formatted(token, password, password),
        cookie,
        origin());
  }

  private int loginStatus(Account account, String password) throws Exception {
    return flow.loginRaw(account.email(), password, AuthFlowClient.CHROME_WINDOWS).status();
  }

  private double count(String result) {
    Counter counter = registry.find("mairor.password_reset").tag("result", result).counter();
    return counter == null ? 0 : counter.count();
  }

  private int passwordVersion(Account account) {
    return userRepository.findPasswordVersionById(account.userId()).orElseThrow();
  }

  // ---- 정상 흐름 ----

  @Test
  void aResetChangesThePasswordAndLogsOutEveryDeviceWithoutLoggingIn() throws Exception {
    Account account = flow.signUp();
    Login chrome = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    // 계정당 로그인 세션은 하나라 safari 로그인이 chrome 세션을 이미 대체했다
    Login safari = flow.login(account, AuthFlowClient.SAFARI_IPHONE);
    hook.reset();
    double successes = count("success");
    String token = tokenFor(account.email());

    Response saved = save(token, NEW_PASSWORD, null);

    assertThat(saved.status()).isEqualTo(204);
    assertThat(saved.sessionCookieValue()).as("자동 로그인하지 않는다").isNull();
    assertThat(flow.me(chrome.cookie()).status()).isEqualTo(401);
    assertThat(flow.me(safari.cookie()).status()).isEqualTo(401);
    assertThat(sessions.findByPrincipalName(account.userId().toString())).isEmpty();
    assertThat(hook.calls)
        .extracting(call -> call.end().reason())
        .containsOnly(SessionEndReason.ALL_DEVICES_REVOKED);
    assertThat(hook.calls).hasSize(1);
    assertThat(loginStatus(account, AuthFlowClient.PASSWORD)).isEqualTo(401);
    assertThat(loginStatus(account, NEW_PASSWORD)).isEqualTo(200);
    assertThat(passwordVersion(account)).isEqualTo(1);
    assertThat(count("success")).isEqualTo(successes + 1);
  }

  @Test
  void aCodeSentAfterTheTokenIsVoidOnceThePasswordIsChanged() throws Exception {
    Account account = flow.signUp();
    String token = tokenFor(account.email());
    String laterCode = requestCode(account.email());

    assertThat(save(token, NEW_PASSWORD, null).status()).isEqualTo(204);

    Response late = verify(account.email(), laterCode);
    assertThat(late.status()).isEqualTo(410);
    assertThat(late.body()).contains("USERS_RESET_CODE_EXPIRED");
  }

  @Test
  void aResetUnlocksALoginThatWasLockedByWrongPasswords() throws Exception {
    Account account = flow.signUp();
    for (int i = 0; i < 3; i++) {
      assertThat(loginStatus(account, "Wrong-Passw0rd!")).isEqualTo(401);
    }
    assertThat(loginStatus(account, AuthFlowClient.PASSWORD)).isEqualTo(429);

    assertThat(save(tokenFor(account.email()), NEW_PASSWORD, null).status()).isEqualTo(204);

    assertThat(loginStatus(account, NEW_PASSWORD)).isEqualTo(200);
  }

  @Test
  void theNormalizedEmailIsUsedSoTheLockOfAnyCaseVariantIsCleared() throws Exception {
    Account account = flow.signUp();
    String shouting = "  " + account.email().toUpperCase() + " ";
    for (int i = 0; i < 3; i++) {
      flow.loginRaw(shouting, "Wrong-Passw0rd!", AuthFlowClient.CHROME_WINDOWS);
    }
    assertThat(loginStatus(account, AuthFlowClient.PASSWORD)).isEqualTo(429);

    // 인증번호도 대소문자가 섞인 주소로 받는다. 저장·확인·잠금 해제가 모두 같은 정규화 값을 본다
    Response sent =
        client.postJson(
            "/v1/users/password-reset", "{\"email\": \"" + shouting + "\"}", null, origin());
    assertThat(sent.status()).isEqualTo(202);
    String code = mail.resetCodes.get(mail.resetCodes.size() - 1).code();
    Response verified = verify(shouting, code);
    Matcher matcher = TOKEN.matcher(verified.body());
    assertThat(matcher.find()).isTrue();
    assertThat(save(matcher.group(1), NEW_PASSWORD, null).status()).isEqualTo(204);

    assertThat(loginStatus(account, NEW_PASSWORD)).isEqualTo(200);
  }

  // ---- 로그인한 상태에서 재설정 ----

  @Test
  void resettingFromALoggedInSessionOfTheSameAccountEndsThatSessionForGood() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    String sessionId = AuthFlowClient.sessionId(login.cookie());
    String token = tokenFor(account.email());

    Response saved = save(token, NEW_PASSWORD, login.cookie());

    assertThat(saved.status()).isEqualTo(204);
    // 로그아웃처럼 이 기기의 쿠키도 만료시킨다
    assertThat(saved.sessionCookieMaxAge()).isZero();
    // 응답을 커밋할 때 다시 저장되지 않았다
    assertThat(flow.me(login.cookie()).status()).isEqualTo(401);
    assertThat(sessions.findById(sessionId)).isNull();
    assertThat(hook.calls).filteredOn(call -> call.end().sessionId().equals(sessionId)).hasSize(1);
  }

  @Test
  void aLoggedInSessionOfAnotherAccountIsLeftAlone() throws Exception {
    Account target = flow.signUp();
    Account other = flow.signUp();
    Login otherLogin = flow.login(other, AuthFlowClient.CHROME_WINDOWS);
    String token = tokenFor(target.email());

    assertThat(save(token, NEW_PASSWORD, otherLogin.cookie()).status()).isEqualTo(204);

    assertThat(flow.me(otherLogin.cookie()).status()).isEqualTo(200);
  }

  // ---- 세션 정리가 실패할 때 ----

  @Test
  void whenEndingTheSessionsFailsThePasswordIsAlreadyChangedAndTheSameTokenFinishesIt()
      throws Exception {
    Account account = flow.signUp();
    Login chrome = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    Login safari = flow.login(account, AuthFlowClient.SAFARI_IPHONE);
    hook.failingSessionIds.add(AuthFlowClient.sessionId(safari.cookie()));
    double failures = count("session_revoke_failed");
    String token = tokenFor(account.email());

    Response failed = save(token, NEW_PASSWORD, null);

    assertThat(failed.status()).isEqualTo(500);
    assertThat(failed.body()).contains("INTERNAL_ERROR");
    assertThat(count("session_revoke_failed")).isEqualTo(failures + 1);
    assertThat(passwordVersion(account)).isEqualTo(1);
    assertThat(flow.me(chrome.cookie()).status()).as("끊을 수 있던 세션은 끊겼다").isEqualTo(401);
    assertThat(flow.me(safari.cookie()).status()).as("정리에 실패한 세션은 남았다").isEqualTo(200);
    // 그 사이에 새 비밀번호로 로그인한 세션도 생긴다
    Response fresh = flow.loginRaw(account.email(), NEW_PASSWORD, AuthFlowClient.CHROME_WINDOWS);
    assertThat(fresh.status()).isEqualTo(200);

    hook.failingSessionIds.clear();
    // 같은 토큰으로 다시 보내면 이번 요청의 비밀번호로 한 번 더 바꾸고 남은 세션을 모두 끝낸다
    assertThat(save(token, NEWER_PASSWORD, null).status()).isEqualTo(204);

    assertThat(flow.me(safari.cookie()).status()).isEqualTo(401);
    assertThat(flow.me(fresh.sessionCookieValue()).status()).isEqualTo(401);
    assertThat(passwordVersion(account)).isEqualTo(2);
    assertThat(loginStatus(account, NEW_PASSWORD)).isEqualTo(401);
    assertThat(loginStatus(account, NEWER_PASSWORD)).isEqualTo(200);
    // 마무리했으니 토큰은 더 못 쓴다
    assertThat(save(token, NEWER_PASSWORD, null).status()).isEqualTo(410);
  }

  @Test
  void theCurrentPasswordIsRejectedButTheSameRequestStillFinishesAfterAFailure() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    String token = tokenFor(account.email());

    // 처음에는 현재 비밀번호와 같은 값은 거절한다
    Response same = save(token, AuthFlowClient.PASSWORD, null);
    assertThat(same.status()).isEqualTo(400);
    assertThat(same.body()).contains("newPassword");

    // 새 비밀번호로 바꿨는데 세션 정리가 실패했다
    hook.failingSessionIds.add(AuthFlowClient.sessionId(login.cookie()));
    assertThat(save(token, NEW_PASSWORD, null).status()).isEqualTo(500);
    hook.failingSessionIds.clear();

    // 이제 NEW_PASSWORD 가 현재 비밀번호지만, 같은 토큰의 재시도라서 같은 요청으로 마무리된다
    assertThat(save(token, NEW_PASSWORD, null).status()).isEqualTo(204);
    assertThat(flow.me(login.cookie()).status()).isEqualTo(401);
    assertThat(loginStatus(account, NEW_PASSWORD)).isEqualTo(200);
  }

  @Test
  void aTemporaryStoreFailureWhileEndingTheSessionsIsServiceUnavailable() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    hook.failingSessionIds.add(AuthFlowClient.sessionId(login.cookie()));
    hook.failure = () -> new DataAccessResourceFailureException("db down");

    Response failed = save(tokenFor(account.email()), NEW_PASSWORD, null);

    assertThat(failed.status()).isEqualTo(503);
    assertThat(failed.body()).contains("SERVICE_UNAVAILABLE");
  }

  @Test
  void ifTheTokenIsGoneAfterAFailureANewCodeIsNeeded() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    hook.failingSessionIds.add(AuthFlowClient.sessionId(login.cookie()));
    String first = tokenFor(account.email());
    assertThat(save(first, NEW_PASSWORD, null).status()).isEqualTo(500);
    hook.failingSessionIds.clear();

    // 그사이 다시 인증해서 토큰이 바뀌었다
    String second = tokenFor(account.email());

    assertThat(save(first, NEW_PASSWORD, null).status()).isEqualTo(410);
    assertThat(save(second, NEWER_PASSWORD, null).status()).isEqualTo(204);
    assertThat(flow.me(login.cookie()).status()).isEqualTo(401);
  }

  // ---- 같은 이메일의 동시 요청 ----

  @Test
  void theSameTokenSentTwiceAtOnceChangesThePasswordOnlyOnce() throws Exception {
    Account account = flow.signUp();
    String token = tokenFor(account.email());
    Gate paused = armGate();
    doAnswer(this::pauseOnce).when(passwordEncoder).encode(any());
    double busy = count("busy");

    // 첫 요청은 잠금을 잡고 해시를 계산하는 중에 멈춰 있다
    Future<Response> first = pool.submit(() -> save(token, NEW_PASSWORD, null));
    assertThat(paused.reached.await(30, TimeUnit.SECONDS)).isTrue();

    Response second = save(token, NEWER_PASSWORD, null);
    Response verifyMeanwhile = verify(account.email(), "123456");
    paused.release.countDown();

    assertThat(second.status()).isEqualTo(429);
    assertThat(second.body()).contains("TOO_MANY_REQUESTS");
    assertThat(second.header("Retry-After")).isEqualTo("1");
    assertThat(verifyMeanwhile.status()).isEqualTo(429);
    assertThat(count("busy")).isEqualTo(busy + 2);
    assertThat(first.get(30, TimeUnit.SECONDS).status()).isEqualTo(204);
    // 다시 보내면 토큰은 이미 쓰였다
    assertThat(save(token, NEWER_PASSWORD, null).status()).isEqualTo(410);
    assertThat(loginStatus(account, NEW_PASSWORD)).isEqualTo(200);
    assertThat(passwordVersion(account)).isEqualTo(1);
  }

  @Test
  void aTokenReplacedWhileTheRequestWaitedForTheLockChangesNothing() throws Exception {
    Account account = flow.signUp();
    String oldToken = tokenFor(account.email());
    Gate paused = armGate();
    doAnswer(this::pauseOnce).when(locks).tryLock(anyString());

    // 토큰 조회는 끝났고 잠금을 잡기 직전에 멈춰 있다
    Future<Response> waiting = pool.submit(() -> save(oldToken, NEW_PASSWORD, null));
    assertThat(paused.reached.await(30, TimeUnit.SECONDS)).isTrue();
    // 그 사이 같은 이메일로 다시 인증해 새 토큰이 나온다
    String newToken = tokenFor(account.email());
    paused.release.countDown();

    Response response = waiting.get(30, TimeUnit.SECONDS);
    assertThat(response.status()).isEqualTo(410);
    assertThat(response.body()).contains("USERS_RESET_TOKEN_EXPIRED");
    assertThat(passwordVersion(account)).isZero();
    assertThat(loginStatus(account, AuthFlowClient.PASSWORD)).isEqualTo(200);
    assertThat(save(newToken, NEW_PASSWORD, null).status()).isEqualTo(204);
  }

  @Test
  void aCodeRequestRunningDuringTheResetCannotLeaveAUsableCodeBehind() throws Exception {
    Account account = flow.signUp();
    String token = tokenFor(account.email());
    Gate paused = armGate();
    doAnswer(this::pauseOnce).when(codeGenerator).generate();

    // 인증번호 발송이 잠금을 잡은 채 인증번호를 만드는 중에 멈춰 있다
    Future<String> lateCode = pool.submit(() -> requestCode(account.email()));
    assertThat(paused.reached.await(30, TimeUnit.SECONDS)).isTrue();

    assertThat(save(token, NEW_PASSWORD, null).status()).as("발송이 끝날 때까지 거절").isEqualTo(429);
    paused.release.countDown();
    String code = lateCode.get(30, TimeUnit.SECONDS);
    assertThat(save(token, NEW_PASSWORD, null).status()).isEqualTo(204);

    // 비밀번호를 바꾸면서 그 인증번호도 폐기했다
    assertThat(verify(account.email(), code).status()).isEqualTo(410);
  }

  // ---- 로그 ----

  @Test
  void neitherTokensNorPasswordsAppearInTheLogs(CapturedOutput output) throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    hook.failingSessionIds.add(AuthFlowClient.sessionId(login.cookie()));
    String token = tokenFor(account.email());

    assertThat(save(token, NEW_PASSWORD, null).status()).isEqualTo(500);

    assertThat(output.getAll())
        .contains("비밀번호를 바꿨지만 기존 세션을 모두 끝내지 못했습니다")
        .doesNotContain(token)
        .doesNotContain(NEW_PASSWORD)
        .doesNotContain(account.email());
  }
}
