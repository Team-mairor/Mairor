package com.mairor.backend.users.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import com.mairor.backend.common.security.SessionEndNotifier;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.common.security.SessionMetrics;
import com.mairor.backend.testsupport.MutableClock;
import com.mairor.backend.users.dto.request.LoginRequest;
import com.mairor.backend.users.dto.response.LoginResponse;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.AuthenticatedUser;
import com.mairor.backend.users.support.InMemoryLoginAttemptLimiter;
import com.mairor.backend.users.support.LoginHashGate;
import com.mairor.backend.users.support.LoginMetrics;
import com.mairor.backend.users.support.PasswordNormalizer;
import com.mairor.backend.users.support.UserSessionAttributes;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import jakarta.servlet.http.HttpSession;
import java.text.Normalizer;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * 로그인 서비스 단위 테스트. 비밀번호 인코더는 실제 bcrypt 를 쓰고(스파이로 호출만 센다), 시도 제한기·BCrypt 게이트도 실제 구현이다. 세션 저장소(JDBC)와
 * 쿠키는 실제 HTTP 흐름 테스트에서 확인한다.
 */
class UserLoginServiceTest {

  private static final Instant NOW = Instant.parse("2026-10-29T03:00:00Z");
  private static final String PASSWORD = "Password1!";
  private static final String CHROME_WINDOWS =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          + "Chrome/130.0.0.0 Safari/537.36";

  private final UserRepository userRepository = mock(UserRepository.class);
  private final PasswordEncoder encoder =
      spy(PasswordEncoderFactories.createDelegatingPasswordEncoder());
  private final MutableClock clock = new MutableClock(NOW);
  private final LoginHashGate gate = new LoginHashGate(4);
  private final SessionEndHook endHook = mock(SessionEndHook.class);
  private final SessionEndNotifier endNotifier = notifierWith(endHook);
  private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
  private final LoginMetrics metrics = new LoginMetrics(registry);

  private InMemoryLoginAttemptLimiter limiter;
  private UserLoginService service;
  private MockHttpServletRequest request;
  private MockHttpServletResponse response;
  private User member;

  @BeforeEach
  void setUp() {
    SecurityContextHolder.clearContext();
    limiter =
        new InMemoryLoginAttemptLimiter(
            3, Duration.ofSeconds(30), Duration.ofMinutes(15), 1_000, message -> {});
    service =
        new UserLoginService(userRepository, encoder, limiter, gate, establisher(), metrics, clock);
    request = new MockHttpServletRequest();
    request.addHeader("User-Agent", CHROME_WINDOWS);
    response = new MockHttpServletResponse();
    member = user("member@example.com", PASSWORD);
    when(userRepository.findByEmail("member@example.com")).thenReturn(Optional.of(member));
    // 세션을 발급한 뒤 비밀번호 버전을 다시 읽는다. 기본은 비밀번호가 바뀌지 않은 상태(읽어 둔 값과 같다)
    when(userRepository.findPasswordVersionById(any())).thenReturn(Optional.of(0));
  }

  /** 운영과 같은 구성: CSRF 필터가 쓰는 저장소·핸들러와 같은 종류를 쓴다. */
  private SessionEstablisher establisher() {
    return new SessionEstablisher(
        new HttpSessionSecurityContextRepository(),
        new HttpSessionCsrfTokenRepository(),
        new XorCsrfTokenRequestAttributeHandler(),
        endNotifier,
        clock);
  }

  private static SessionEndNotifier notifierWith(SessionEndHook hook) {
    DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
    factory.registerSingleton("hook", hook);
    return new SessionEndNotifier(
        factory.getBeanProvider(SessionEndHook.class),
        new SessionMetrics(new SimpleMeterRegistry()));
  }

  @AfterEach
  void tearDown() {
    SecurityContextHolder.clearContext();
  }

  private User user(String email, String rawPassword) {
    User user = new User(email, rawPassword == null ? null : encoder.encode(rawPassword));
    ReflectionTestUtils.setField(user, "id", UUID.randomUUID());
    return user;
  }

  private LoginResponse login(String email, String password) {
    return service.login(new LoginRequest(email, password), request, response);
  }

  private BusinessException failedLogin(String email, String password) {
    return catchBusinessException(() -> login(email, password));
  }

  private static BusinessException catchBusinessException(Runnable action) {
    try {
      action.run();
    } catch (BusinessException e) {
      return e;
    }
    throw new AssertionError("BusinessException 이 던져져야 합니다");
  }

  // ---- 성공 ----

  @Test
  void successReturnsTheUserAndACsrfToken() {
    LoginResponse result = login("member@example.com", PASSWORD);

    assertThat(result.user().userId()).isEqualTo(member.getId().toString());
    assertThat(result.user().email()).isEqualTo("member@example.com");
    assertThat(result.csrfToken()).isNotBlank();
    // 응답 본문에 비밀번호나 해시가 없다
    assertThat(result.toString()).doesNotContain(PASSWORD).doesNotContain(member.getPasswordHash());
  }

  @Test
  void successStoresAnAuthenticatedContextInTheSession() {
    login("member@example.com", PASSWORD);

    SecurityContext stored =
        (SecurityContext)
            request
                .getSession()
                .getAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
    assertThat(stored).isNotNull();
    assertThat(stored.getAuthentication().isAuthenticated()).isTrue();
    assertThat(stored.getAuthentication().getPrincipal()).isInstanceOf(AuthenticatedUser.class);
    assertThat(stored.getAuthentication().getName()).isEqualTo(member.getId().toString());
  }

  @Test
  void successRecordsTheLoginTimeTheDeviceAndAPublicSessionReference() {
    login("member@example.com", PASSWORD);

    var session = request.getSession();
    assertThat(session.getAttribute(SessionAttributes.AUTHENTICATED_AT)).isEqualTo(NOW);
    assertThat(session.getAttribute(UserSessionAttributes.DEVICE)).isEqualTo("Chrome · Windows");
    assertThat(session.getAttribute(UserSessionAttributes.SESSION_REF)).isInstanceOf(UUID.class);
  }

  @Test
  void successTellsTheCookieRefreshFilterToStayOut() {
    login("member@example.com", PASSWORD);

    assertThat(request.getAttribute(SessionAttributes.COOKIE_REFRESH_SUPPRESSED)).isEqualTo(true);
  }

  @Test
  void normalizedEmailIsUsedForTheLookup() {
    login("  Member@Example.COM ", PASSWORD);

    verify(userRepository).findByEmail("member@example.com");
  }

  @Test
  void anNfdPasswordMatchesAnAccountCreatedWithTheNfcForm() {
    String nfc = "한글Pass1!";
    User korean = user("korean@example.com", PasswordNormalizer.normalize(nfc));
    when(userRepository.findByEmail("korean@example.com")).thenReturn(Optional.of(korean));
    String nfd = Normalizer.normalize(nfc, Normalizer.Form.NFD);
    assertThat(nfd).isNotEqualTo(nfc);

    LoginResponse result = login("korean@example.com", nfd);

    assertThat(result.user().email()).isEqualTo("korean@example.com");
  }

  // ---- 세션 만들기 ----

  @Test
  void createsASessionWhenThereIsNone() {
    assertThat(request.getSession(false)).isNull();

    login("member@example.com", PASSWORD);

    assertThat(request.getSession(false)).isNotNull();
  }

  @Test
  void changesTheSessionIdOfAnAnonymousSession() {
    MockHttpSession anonymous = (MockHttpSession) request.getSession();
    String before = anonymous.getId();

    login("member@example.com", PASSWORD);

    assertThat(request.getSession().getId()).isNotEqualTo(before);
  }

  @Test
  void anAlreadyLoggedInSessionIsDiscardedWhenLoggingInAsAnotherAccount() {
    User other = user("other@example.com", "Another1!");
    when(userRepository.findByEmail("other@example.com")).thenReturn(Optional.of(other));
    login("member@example.com", PASSWORD);
    MockHttpSession first = (MockHttpSession) request.getSession();
    Object firstRef = first.getAttribute(UserSessionAttributes.SESSION_REF);

    // 같은 브라우저가 다른 계정으로 로그인한다 (서비스가 SecurityContextHolder 에서 기존 인증을 본다)
    login("other@example.com", "Another1!");

    MockHttpSession second = (MockHttpSession) request.getSession();
    assertThat(first.isInvalid()).isTrue();
    assertThat(second.getId()).isNotEqualTo(first.getId());
    assertThat(second.getAttribute(UserSessionAttributes.SESSION_REF))
        .isNotNull()
        .isNotEqualTo(firstRef);
    SecurityContext stored =
        (SecurityContext)
            second.getAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
    assertThat(stored.getAuthentication().getName()).isEqualTo(other.getId().toString());
  }

  @Test
  void replacesTheCsrfTokenKeptInTheAnonymousSession() {
    HttpSessionCsrfTokenRepository csrfRepository = new HttpSessionCsrfTokenRepository();
    CsrfToken oldToken = csrfRepository.generateToken(request);
    csrfRepository.saveToken(oldToken, request, response);

    LoginResponse result = login("member@example.com", PASSWORD);

    CsrfToken stored = csrfRepository.loadToken(request);
    assertThat(stored).isNotNull();
    assertThat(stored.getToken()).isNotEqualTo(oldToken.getToken());
    assertThat(result.csrfToken()).isNotBlank().isNotEqualTo(oldToken.getToken());
  }

  @Test
  void theReturnedTokenIsWhatTheCsrfFilterAcceptsOnTheNextRequest() {
    HttpSessionCsrfTokenRepository csrfRepository = new HttpSessionCsrfTokenRepository();
    CsrfToken oldToken = csrfRepository.generateToken(request);
    csrfRepository.saveToken(oldToken, request, response);
    // 로그인 전에 받아 둔 마스킹된 토큰
    MockHttpServletRequest beforeLogin = new MockHttpServletRequest();
    beforeLogin.setSession(request.getSession());
    new XorCsrfTokenRequestAttributeHandler()
        .handle(beforeLogin, response, () -> csrfRepository.loadToken(beforeLogin));
    String tokenFromBeforeLogin =
        ((CsrfToken) beforeLogin.getAttribute(CsrfToken.class.getName())).getToken();

    LoginResponse result = login("member@example.com", PASSWORD);

    // CsrfFilter 는 저장된 토큰과, 요청 헤더의 마스킹을 푼 값을 비교한다
    assertThat(acceptedByCsrfFilter(result.csrfToken())).isTrue();
    assertThat(acceptedByCsrfFilter(tokenFromBeforeLogin)).isFalse();
  }

  @Test
  void aFailureWhileBuildingTheSessionDiscardsTheAuthenticationAndRethrows() {
    CsrfTokenRepository broken = mock(CsrfTokenRepository.class);
    doThrow(new IllegalStateException("csrf failed")).when(broken).saveToken(any(), any(), any());
    UserLoginService failing =
        new UserLoginService(
            userRepository,
            encoder,
            limiter,
            gate,
            new SessionEstablisher(
                new HttpSessionSecurityContextRepository(),
                broken,
                new XorCsrfTokenRequestAttributeHandler(),
                endNotifier,
                clock),
            metrics,
            clock);

    assertThatThrownBy(
            () ->
                failing.login(new LoginRequest("member@example.com", PASSWORD), request, response))
        .isInstanceOf(IllegalStateException.class)
        .hasMessage("csrf failed");

    assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    HttpSession session = request.getSession(false);
    assertThat(session == null || ((MockHttpSession) session).isInvalid()).isTrue();
  }

  private boolean acceptedByCsrfFilter(String headerValue) {
    MockHttpServletRequest next = new MockHttpServletRequest();
    next.setSession(request.getSession());
    next.addHeader("X-CSRF-TOKEN", headerValue);
    CsrfToken stored = new HttpSessionCsrfTokenRepository().loadToken(next);
    String actual = new XorCsrfTokenRequestAttributeHandler().resolveCsrfTokenValue(next, stored);
    return actual != null && actual.equals(stored.getToken());
  }

  // ---- 실패: 원인을 구분하지 않는다 ----

  @Test
  void aWrongPasswordIsRejectedWithTheGenericMessage() {
    BusinessException e = failedLogin("member@example.com", "Wrong-Password1!");

    assertThat(e.status()).isEqualTo(HttpStatus.UNAUTHORIZED);
    assertThat(e.code()).isEqualTo("USERS_INVALID_CREDENTIALS");
    assertThat(e.getMessage()).isEqualTo("이메일 또는 비밀번호를 확인해 주세요.");
    assertThat(request.getSession(false)).as("실패하면 세션을 만들지 않는다").isNull();
  }

  @Test
  void anUnknownEmailLooksExactlyLikeAWrongPasswordAndStillHashesADummy() {
    when(userRepository.findByEmail("nobody@example.com")).thenReturn(Optional.empty());
    BusinessException wrongPassword = failedLogin("member@example.com", "Wrong-Password1!");

    BusinessException unknown = failedLogin("nobody@example.com", PASSWORD);

    assertThat(unknown.status()).isEqualTo(wrongPassword.status());
    assertThat(unknown.code()).isEqualTo(wrongPassword.code());
    assertThat(unknown.getMessage()).isEqualTo(wrongPassword.getMessage());
    // 사용자가 없어도 같은 비용의 비교를 한다: 틀린 비밀번호 1번 + 더미 비교 1번
    verify(encoder, times(2)).matches(anyString(), anyString());
  }

  @Test
  void aGoogleOnlyAccountWithoutAHashLooksLikeAWrongPassword() {
    User googleOnly = user("google@example.com", null);
    when(userRepository.findByEmail("google@example.com")).thenReturn(Optional.of(googleOnly));
    BusinessException wrongPassword = failedLogin("member@example.com", "Wrong-Password1!");

    BusinessException e = failedLogin("google@example.com", PASSWORD);

    assertThat(e.status()).isEqualTo(wrongPassword.status());
    assertThat(e.code()).isEqualTo(wrongPassword.code());
    assertThat(e.getMessage()).isEqualTo(wrongPassword.getMessage());
    verify(encoder, times(2)).matches(anyString(), anyString());
  }

  @Test
  void aPasswordOver72BytesIsRejectedWithoutHashingAndCountsAsAFailure() {
    // bcrypt 는 72바이트 뒤를 무시하므로, 앞 72바이트가 같은 긴 비밀번호가 통과하면 안 된다
    String longPassword = "a".repeat(73);
    User prefixOwner = user("prefix@example.com", "a".repeat(72));
    when(userRepository.findByEmail("prefix@example.com")).thenReturn(Optional.of(prefixOwner));

    for (int i = 0; i < 3; i++) {
      BusinessException e = failedLogin("prefix@example.com", longPassword);
      assertThat(e.code()).isEqualTo("USERS_INVALID_CREDENTIALS");
    }

    verify(encoder, never()).matches(eq(longPassword), anyString());
    assertThat(gate.availablePermits()).isEqualTo(4);
    // 실패로 셌으므로 세 번 뒤에는 잠긴다
    assertThat(failedLogin("prefix@example.com", "a".repeat(72)).code())
        .isEqualTo("USERS_LOGIN_RATE_LIMITED");
  }

  @Test
  void countsBytesNotCharactersForTheLimit() {
    // 한글 25자 = 75바이트
    String korean = "가".repeat(25);
    User owner = user("kr@example.com", "가".repeat(24));
    when(userRepository.findByEmail("kr@example.com")).thenReturn(Optional.of(owner));

    assertThat(failedLogin("kr@example.com", korean).code()).isEqualTo("USERS_INVALID_CREDENTIALS");
    verify(encoder, never()).matches(eq(korean), anyString());
  }

  // ---- 시도 제한 ----

  @Test
  void locksAfterThreeWrongPasswordsEvenForTheRightPassword() {
    for (int i = 0; i < 3; i++) {
      assertThat(failedLogin("member@example.com", "Wrong-Password1!").code())
          .isEqualTo("USERS_INVALID_CREDENTIALS");
    }

    BusinessException locked = failedLogin("member@example.com", PASSWORD);

    assertThat(locked.status()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
    assertThat(locked.code()).isEqualTo("USERS_LOGIN_RATE_LIMITED");
    assertThat(locked.retryAfterSeconds()).isEqualTo(30);
    // 잠금 중에는 비밀번호 비교도 하지 않는다 (틀린 3번 + 더미 0번)
    verify(encoder, times(3)).matches(anyString(), anyString());
  }

  @Test
  void aSuccessfulLoginClearsTheFailureCount() {
    failedLogin("member@example.com", "Wrong-Password1!");
    failedLogin("member@example.com", "Wrong-Password1!");
    login("member@example.com", PASSWORD);

    failedLogin("member@example.com", "Wrong-Password1!");
    failedLogin("member@example.com", "Wrong-Password1!");

    // 성공으로 초기화됐으므로 실패 2번 뒤에도 잠기지 않았다
    login("member@example.com", PASSWORD);
  }

  @Test
  void theLockEndsAfterTheLockDuration() {
    for (int i = 0; i < 3; i++) {
      failedLogin("member@example.com", "Wrong-Password1!");
    }
    assertThat(failedLogin("member@example.com", PASSWORD).code())
        .isEqualTo("USERS_LOGIN_RATE_LIMITED");

    clock.advance(Duration.ofSeconds(30));

    login("member@example.com", PASSWORD);
  }

  @Test
  void anUnknownEmailIsCountedAndLockedLikeAKnownOne() {
    when(userRepository.findByEmail("nobody@example.com")).thenReturn(Optional.empty());
    for (int i = 0; i < 3; i++) {
      failedLogin("nobody@example.com", PASSWORD);
    }

    BusinessException e = failedLogin("nobody@example.com", PASSWORD);

    assertThat(e.code()).isEqualTo("USERS_LOGIN_RATE_LIMITED");
  }

  // ---- BCrypt 동시 실행 상한과 환불 ----

  @Test
  void whenTheHashGateIsFullItAnswers429WithoutCountingTheAttempt() {
    LoginHashGate full = new LoginHashGate(1);
    var held = full.tryEnter().orElseThrow();
    UserLoginService busy =
        new UserLoginService(userRepository, encoder, limiter, full, establisher(), metrics, clock);

    for (int i = 0; i < 5; i++) {
      BusinessException e =
          catchBusinessException(
              () ->
                  busy.login(new LoginRequest("member@example.com", PASSWORD), request, response));
      assertThat(e.status()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
      assertThat(e.code()).isEqualTo("TOO_MANY_REQUESTS");
      assertThat(e.retryAfterSeconds()).isEqualTo(1);
    }
    held.close();

    // 거절된 5번이 실패로 세어졌다면 이미 잠겨 있을 것이다
    busy.login(new LoginRequest("member@example.com", PASSWORD), request, response);
  }

  @Test
  void anInternalErrorDoesNotCountAsAFailure() {
    when(userRepository.findByEmail(anyString())).thenThrow(new IllegalStateException("DB 장애"));
    for (int i = 0; i < 5; i++) {
      assertThatThrownBy(() -> login("member@example.com", PASSWORD))
          .isInstanceOf(IllegalStateException.class);
    }
    doReturn(Optional.of(member)).when(userRepository).findByEmail("member@example.com");

    // 환불됐으므로 잠기거나 자리가 막히지 않았다
    login("member@example.com", PASSWORD);
    assertThat(gate.availablePermits()).isEqualTo(4);
  }

  @Test
  void theHashGatePermitIsReturnedEvenWhenTheEncoderThrows() {
    org.mockito.Mockito.doThrow(new IllegalStateException("해시 실패"))
        .when(encoder)
        .matches(eq(PASSWORD), eq(member.getPasswordHash()));

    assertThatThrownBy(() -> login("member@example.com", PASSWORD))
        .isInstanceOf(IllegalStateException.class);

    assertThat(gate.availablePermits()).isEqualTo(4);
  }

  @Test
  void aTicketIsNeverLeftOpenSoSlotsAreNotLeaked() {
    // 성공·실패·예외를 섞어도 자리가 새지 않아 이후 시도가 Pending 으로 막히지 않는다
    login("member@example.com", PASSWORD);
    failedLogin("member@example.com", "Wrong-Password1!");
    when(userRepository.findByEmail(anyString())).thenThrow(new IllegalStateException("DB 장애"));
    assertThatThrownBy(() -> login("member@example.com", PASSWORD))
        .isInstanceOf(IllegalStateException.class);
    doReturn(Optional.of(member)).when(userRepository).findByEmail("member@example.com");

    login("member@example.com", PASSWORD);
    verify(userRepository, times(4)).findByEmail(any());
  }

  // ---- 지표 ----

  private double count(String result) {
    var counter = registry.find("mairor.login.attempts").tag("result", result).counter();
    return counter == null ? 0 : counter.count();
  }

  @Test
  void aSuccessfulLoginIsCounted() {
    login("member@example.com", PASSWORD);

    assertThat(count("success")).isEqualTo(1);
    assertThat(count("invalid_credentials")).isZero();
  }

  // ---- 세션 발급 뒤 비밀번호 버전 재확인 ----

  @Test
  void aPasswordChangedWhileLoggingInRejectsTheLoginAndDiscardsTheSession() {
    when(userRepository.findPasswordVersionById(any())).thenReturn(Optional.of(1));

    BusinessException e = failedLogin("member@example.com", PASSWORD);

    assertThat(e.status()).isEqualTo(HttpStatus.UNAUTHORIZED);
    assertThat(e.code()).isEqualTo("USERS_INVALID_CREDENTIALS");
    assertThat(request.getSession(false)).as("만든 세션을 버린다").isNull();
    assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    assertThat(count("password_changed")).isEqualTo(1);
    assertThat(count("success")).isZero();
  }

  @Test
  void aUserWhoVanishedWhileLoggingInIsTreatedTheSameWay() {
    when(userRepository.findPasswordVersionById(any())).thenReturn(Optional.empty());

    BusinessException e = failedLogin("member@example.com", PASSWORD);

    assertThat(e.code()).isEqualTo("USERS_INVALID_CREDENTIALS");
    assertThat(request.getSession(false)).isNull();
    assertThat(count("password_changed")).isEqualTo(1);
  }

  @Test
  void aRejectedRecheckDoesNotCountAsAWrongPassword() {
    when(userRepository.findPasswordVersionById(any())).thenReturn(Optional.of(1));
    for (int i = 0; i < 5; i++) {
      failedLogin("member@example.com", PASSWORD);
    }
    when(userRepository.findPasswordVersionById(any())).thenReturn(Optional.of(0));

    // 올바른 비밀번호를 다섯 번 보냈지만 비밀번호 실패로 세지 않았으므로 잠기지 않았다
    login("member@example.com", PASSWORD);

    assertThat(count("invalid_credentials")).isZero();
    assertThat(gate.availablePermits()).isEqualTo(4);
  }

  /**
   * 재확인은 비밀번호가 맞은 뒤에 일어난다. 그래서 재확인 실패는 비밀번호 실패로 세지 않고, 비밀번호가 맞았으므로 그 전의 실패 횟수는 0 으로 돌아간다. 제한기에는 실패
   * 횟수를 읽는 메서드가 없어서 동작으로 확인한다(한도 3회): 남아 있었다면 다음 실패에서 바로 잠긴다.
   */
  private void assertFailuresStartFromZeroAgain() {
    assertThat(failedLogin("member@example.com", "Wrong-Password1!").code())
        .as("초기화되지 않았다면 여기서 세 번째 실패로 잠긴다")
        .isEqualTo("USERS_INVALID_CREDENTIALS");
    assertThat(failedLogin("member@example.com", "Wrong-Password1!").code())
        .isEqualTo("USERS_INVALID_CREDENTIALS");
    assertThat(failedLogin("member@example.com", "Wrong-Password1!").code())
        .isEqualTo("USERS_INVALID_CREDENTIALS");
    // 제한기는 다시 센다: 세 번 틀렸으니 이제 잠긴다
    assertThat(failedLogin("member@example.com", PASSWORD).code())
        .isEqualTo("USERS_LOGIN_RATE_LIMITED");
  }

  @Test
  void aDatabaseErrorDuringTheRecheckIsAnErrorNotAWrongPasswordAndClearsEarlierFailures() {
    failedLogin("member@example.com", "Wrong-Password1!");
    failedLogin("member@example.com", "Wrong-Password1!");
    when(userRepository.findPasswordVersionById(any()))
        .thenThrow(new IllegalStateException("DB 장애"));

    assertThatThrownBy(() -> login("member@example.com", PASSWORD))
        .isInstanceOf(IllegalStateException.class);

    assertThat(count("error")).isEqualTo(1);
    assertThat(count("invalid_credentials")).as("앞의 틀린 비밀번호 두 번뿐").isEqualTo(2);
    assertThat(count("success")).isZero();
    assertFailuresStartFromZeroAgain();
  }

  @Test
  void aPasswordChangedDuringTheLoginIsCountedSeparatelyAndClearsEarlierFailures() {
    failedLogin("member@example.com", "Wrong-Password1!");
    failedLogin("member@example.com", "Wrong-Password1!");
    when(userRepository.findPasswordVersionById(any())).thenReturn(Optional.of(1));

    assertThat(failedLogin("member@example.com", PASSWORD).code())
        .isEqualTo("USERS_INVALID_CREDENTIALS");

    assertThat(count("password_changed")).isEqualTo(1);
    assertThat(count("invalid_credentials")).as("앞의 틀린 비밀번호 두 번뿐").isEqualTo(2);
    assertThat(count("error")).isZero();
    assertFailuresStartFromZeroAgain();
  }

  @Test
  void aFailingRecheckDiscardsTheSessionAndThrowsTheOriginalException() {
    IllegalStateException original = new IllegalStateException("DB 장애");
    when(userRepository.findPasswordVersionById(any())).thenThrow(original);

    assertThatThrownBy(() -> login("member@example.com", PASSWORD)).isSameAs(original);

    assertThat(request.getSession(false)).isNull();
    assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    assertThat(count("error")).isEqualTo(1);
    assertThat(count("success")).isZero();
  }

  @Test
  void aFailureWhileDiscardingAfterAFailingRecheckIsAttachedToTheOriginalException() {
    IllegalStateException original = new IllegalStateException("DB 장애");
    IllegalStateException cleanup = new IllegalStateException("정리 실패");
    when(userRepository.findPasswordVersionById(any())).thenThrow(original);
    SessionEstablisher failingDiscard = spy(establisher());
    doThrow(cleanup).when(failingDiscard).discard(any());
    service =
        new UserLoginService(
            userRepository, encoder, limiter, gate, failingDiscard, metrics, clock);

    assertThatThrownBy(() -> login("member@example.com", PASSWORD))
        .isSameAs(original)
        .hasSuppressedException(cleanup);
  }

  @Test
  void aFailureWhileDiscardingAfterAChangedPasswordIsNotHiddenBehindA401() {
    IllegalStateException cleanup = new IllegalStateException("정리 실패");
    when(userRepository.findPasswordVersionById(any())).thenReturn(Optional.of(1));
    SessionEstablisher failingDiscard = spy(establisher());
    doThrow(cleanup).when(failingDiscard).discard(any());
    service =
        new UserLoginService(
            userRepository, encoder, limiter, gate, failingDiscard, metrics, clock);

    // 세션을 버리지 못했는데 401 로 끝나면 응답은 실패인데 세션이 살아 있게 된다
    assertThatThrownBy(() -> login("member@example.com", PASSWORD)).isSameAs(cleanup);
  }

  @Test
  void aWrongPasswordIsCountedAsInvalidCredentials() {
    failedLogin("member@example.com", "Wrong-Password1!");
    failedLogin("nobody@example.com", PASSWORD);

    assertThat(count("invalid_credentials")).isEqualTo(2);
    assertThat(count("success")).isZero();
  }

  @Test
  void aLockedEmailIsCountedAsLockedAndNotAsInvalidCredentials() {
    for (int i = 0; i < 3; i++) {
      failedLogin("member@example.com", "Wrong-Password1!");
    }
    failedLogin("member@example.com", PASSWORD);

    assertThat(count("invalid_credentials")).isEqualTo(3);
    assertThat(count("locked")).isEqualTo(1);
  }

  @Test
  void aRejectionByTheHashGateIsCountedSeparately() {
    LoginHashGate full = new LoginHashGate(1);
    var held = full.tryEnter().orElseThrow();
    UserLoginService busy =
        new UserLoginService(userRepository, encoder, limiter, full, establisher(), metrics, clock);

    catchBusinessException(
        () -> busy.login(new LoginRequest("member@example.com", PASSWORD), request, response));
    held.close();

    assertThat(count("gate_rejected")).isEqualTo(1);
    assertThat(count("invalid_credentials")).isZero();
  }

  @Test
  void anInternalErrorIsCountedAsError() {
    when(userRepository.findByEmail("member@example.com"))
        .thenThrow(new IllegalStateException("db down"));

    assertThatThrownBy(() -> login("member@example.com", PASSWORD))
        .isInstanceOf(IllegalStateException.class);

    assertThat(count("error")).isEqualTo(1);
    assertThat(count("invalid_credentials")).isZero();
  }

  @Test
  void theMetricLabelsNeverContainTheEmailOrAnyOtherIdentifier() {
    login("member@example.com", PASSWORD);
    failedLogin("nobody@example.com", PASSWORD);

    assertThat(registry.getMeters())
        .allSatisfy(
            meter ->
                assertThat(meter.getId().getTags())
                    .allSatisfy(
                        tag -> {
                          assertThat(tag.getKey()).isEqualTo("result");
                          assertThat(tag.getValue()).doesNotContain("@").doesNotContain("member");
                        }));
  }

  // ---- 해시 게이트는 DB 조회보다 앞에서 ----

  @Test
  void whenTheHashGateIsFullTheDatabaseIsNotQueriedAtAll() {
    LoginHashGate full = new LoginHashGate(1);
    var held = full.tryEnter().orElseThrow();
    UserLoginService busy =
        new UserLoginService(userRepository, encoder, limiter, full, establisher(), metrics, clock);
    org.mockito.Mockito.clearInvocations(userRepository);

    catchBusinessException(
        () -> busy.login(new LoginRequest("member@example.com", PASSWORD), request, response));
    held.close();

    org.mockito.Mockito.verifyNoInteractions(userRepository);
  }

  @Test
  void aPasswordOver72BytesDoesNotQueryTheDatabaseOrUseTheGate() {
    org.mockito.Mockito.clearInvocations(userRepository);
    String tooLong = "a".repeat(73);

    BusinessException e = failedLogin("member@example.com", tooLong);

    assertThat(e.code()).isEqualTo("USERS_INVALID_CREDENTIALS");
    org.mockito.Mockito.verifyNoInteractions(userRepository);
    assertThat(gate.availablePermits()).isEqualTo(4);
  }

  @Test
  void theHashGatePermitIsHeldWhileTheUserIsLookedUp() {
    when(userRepository.findByEmail("member@example.com"))
        .thenAnswer(
            call -> {
              // 조회하는 동안 게이트 자리 하나가 사용 중이다
              assertThat(gate.availablePermits()).isEqualTo(3);
              return Optional.of(member);
            });

    login("member@example.com", PASSWORD);

    assertThat(gate.availablePermits()).isEqualTo(4);
  }

  // ---- 이전 인증 세션 대체 → 종료 훅 ----

  @Test
  void replacingALoggedInSessionCallsTheHookBeforeItIsDiscarded() {
    login("member@example.com", PASSWORD);
    MockHttpSession first = (MockHttpSession) request.getSession();
    String firstId = first.getId();
    boolean[] discardedWhenCalled = new boolean[1];
    doAnswer(
            call -> {
              discardedWhenCalled[0] = first.isInvalid();
              return null;
            })
        .when(endHook)
        .beforeSessionEnds(any());

    login("member@example.com", PASSWORD);

    verify(endHook)
        .beforeSessionEnds(
            new SessionEnd(member.getId().toString(), firstId, SessionEndReason.REPLACED_BY_LOGIN));
    assertThat(discardedWhenCalled[0]).as("훅은 이전 세션을 폐기하기 전에 호출된다").isFalse();
    assertThat(first.isInvalid()).isTrue();
  }

  @Test
  void aFirstLoginOrAnAnonymousSessionDoesNotCallTheHook() {
    login("member@example.com", PASSWORD);

    verify(endHook, never()).beforeSessionEnds(any());
  }

  @Test
  void aFailingHookDoesNotBlockReplacingTheSession() {
    login("member@example.com", PASSWORD);
    MockHttpSession first = (MockHttpSession) request.getSession();
    doThrow(new IllegalStateException("cleanup failed")).when(endHook).beforeSessionEnds(any());

    LoginResponse result = login("member@example.com", PASSWORD);

    assertThat(result.csrfToken()).isNotBlank();
    assertThat(first.isInvalid()).isTrue();
    assertThat(request.getSession()).isNotSameAs(first);
  }
}
