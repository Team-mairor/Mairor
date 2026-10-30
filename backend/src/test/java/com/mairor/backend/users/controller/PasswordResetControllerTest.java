package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.VerificationTestSupport;
import com.mairor.backend.users.VerificationTestSupport.CapturingMailSender;
import com.mairor.backend.users.VerificationTestSupport.MutableClock;
import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.service.UserSessionService;
import com.mairor.backend.users.support.EmailVerificationStore;
import com.mairor.backend.users.support.EmailVerificationStoreConfig;
import com.mairor.backend.users.support.PasswordResetLocks;
import com.mairor.backend.users.support.VerificationHasher;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;

/**
 * 비밀번호 재설정 인증번호 발송·확인 API 계약 (API-USERS-008·009). 가입과 마찬가지로 인증·CSRF 토큰 없이 허용 Origin 헤더만 보낸다.
 *
 * <p>실제 메일 대신 보낸 메일을 모아 두는 발송기를 쓰고, 시간은 테스트가 움직일 수 있는 시계로 바꿔 쿨다운·만료를 기다리지 않고 확인한다. 인증 상태는 메모리에 있어
 * 테스트끼리 섞이지 않도록 테스트마다 새 이메일과 새 클라이언트 IP 를 쓴다.
 *
 * <p>가입한 이메일, 가입하지 않은 이메일, 비밀번호가 없는 Google 로그인 전용 이메일이 응답과 제한 동작으로 구별되지 않는지를 중점으로 본다.
 */
@Import({TestcontainersConfiguration.class, VerificationTestSupport.TestBeans.class})
@SpringBootTest(
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.rate-limit.password-reset.limit=1000",
      "app.rate-limit.email-verification.limit=1000"
    })
@AutoConfigureMockMvc
@Transactional
@ExtendWith(OutputCaptureExtension.class)
class PasswordResetControllerTest {

  private static final Instant T0 = VerificationTestSupport.T0;
  private static final String ORIGIN = "http://localhost:3000";
  private static final String SEND = "/v1/users/password-reset";
  private static final String VERIFY = "/v1/users/password-reset/verification";
  private static final String SAVE = "/v1/users/password-reset/password";
  private static final String NEW_PASSWORD = "NewPassw0rd!2026";
  private static final AtomicInteger IPS = new AtomicInteger();

  @Autowired private MockMvc mockMvc;
  @Autowired private CapturingMailSender mail;
  @Autowired private MutableClock clock;
  @Autowired private VerificationHasher hasher;
  @Autowired private PasswordResetLocks locks;
  @Autowired private PasswordEncoder passwordEncoder;

  @Autowired
  @Qualifier(EmailVerificationStoreConfig.PASSWORD_RESET)
  private EmailVerificationStore resetStore;

  /** 조회 실패를 흉내 낼 때만 스텁한다(던지기). 그 밖의 호출은 실제 저장소로 간다. */
  @MockitoSpyBean private UserRepository userRepository;

  /** 갱신이 반영되지 않았을 때 세션 정리를 부르지 않는지 확인한다. */
  @MockitoSpyBean private UserSessionService userSessionService;

  @Autowired private MeterRegistry registry;

  private final String id = UUID.randomUUID().toString();
  private final String registered = "reset-" + id + "@example.com";
  private final String googleOnly = "google-" + id + "@example.com";
  private final String unknown = "nobody-" + id + "@example.com";
  private final String ip = "10.8." + IPS.incrementAndGet() / 250 + "." + IPS.get() % 250;
  private ExecutorService pool;

  @BeforeEach
  void setUp() {
    clock.set(T0);
    mail.failing = false;
    mail.sent.clear();
    mail.resetCodes.clear();
    mail.googleNotices.clear();
    userRepository.saveAndFlush(new User(registered, "{bcrypt}hash"));
    userRepository.saveAndFlush(
        new User(googleOnly, null, AuthProvider.GOOGLE, null, null, null, null, null, null));
    pool = Executors.newSingleThreadExecutor();
  }

  @AfterEach
  void tearDown() {
    pool.shutdownNow();
  }

  private MockHttpServletRequestBuilder request(String url, String json) {
    return post(url)
        .header("Origin", ORIGIN)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json)
        .with(
            r -> {
              r.setRemoteAddr(ip);
              return r;
            });
  }

  private ResultActions send(String address) throws Exception {
    return mockMvc.perform(request(SEND, "{\"email\": \"" + address + "\"}"));
  }

  private ResultActions verify(String address, String code) throws Exception {
    return mockMvc.perform(
        request(VERIFY, "{\"email\": \"" + address + "\", \"code\": \"" + code + "\"}"));
  }

  private String sendAndGetCode(String address) throws Exception {
    send(address).andExpect(status().isAccepted());
    return mail.lastResetCode().code();
  }

  private ResultActions save(String token, String password, String confirm) throws Exception {
    return mockMvc.perform(
        put(SAVE)
            .header("Origin", ORIGIN)
            .contentType(MediaType.APPLICATION_JSON)
            .content(
                "{\"resetToken\": \""
                    + token
                    + "\", \"newPassword\": \""
                    + password
                    + "\", \"newPasswordConfirm\": \""
                    + confirm
                    + "\"}"));
  }

  private String tokenFor(String address) throws Exception {
    return tokenOf(verify(address, sendAndGetCode(address)).andExpect(status().isOk()).andReturn());
  }

  private String tokenOf(MvcResult result) throws Exception {
    return JsonPath.read(result.getResponse().getContentAsString(), "$.resetToken");
  }

  private static String wrongCodeFor(String code) {
    return code.equals("000000") ? "000001" : "000000";
  }

  // ---- 발송 ----

  @Test
  void send_toARegisteredEmail_returns202AndMailsASixDigitCode() throws Exception {
    send(registered)
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.expiresInSeconds").value(600))
        .andExpect(jsonPath("$.resendAvailableInSeconds").value(60));

    assertThat(mail.resetCodes).hasSize(1);
    assertThat(mail.lastResetCode().to()).isEqualTo(registered);
    assertThat(mail.lastResetCode().code()).matches("\\d{6}");
    assertThat(mail.lastResetCode().validFor()).isEqualTo(Duration.ofMinutes(10));
    assertThat(mail.googleNotices).isEmpty();
    assertThat(mail.sent).as("가입 인증 메일은 보내지 않는다").isEmpty();
  }

  @Test
  void send_normalizesTheEmail() throws Exception {
    send("  " + registered.toUpperCase() + " ").andExpect(status().isAccepted());

    assertThat(mail.lastResetCode().to()).isEqualTo(registered);
  }

  @Test
  void send_toAGoogleOnlyAccount_sendsANoticeInsteadOfACode() throws Exception {
    send(googleOnly).andExpect(status().isAccepted());

    assertThat(mail.googleNotices).containsExactly(googleOnly);
    assertThat(mail.resetCodes).isEmpty();
  }

  @Test
  void send_toAnUnknownEmail_sendsNothing() throws Exception {
    send(unknown).andExpect(status().isAccepted());

    assertThat(mail.resetCodes).isEmpty();
    assertThat(mail.googleNotices).isEmpty();
  }

  @Test
  void send_answersTheSameWhetherOrNotTheEmailIsRegistered() throws Exception {
    List<MvcResult> first = List.of(sendRaw(registered), sendRaw(googleOnly), sendRaw(unknown));
    clock.advance(Duration.ofSeconds(20));
    List<MvcResult> second = List.of(sendRaw(registered), sendRaw(googleOnly), sendRaw(unknown));

    for (MvcResult result : first) {
      assertThat(result.getResponse().getStatus()).isEqualTo(202);
      assertThat(result.getResponse().getContentAsString())
          .isEqualTo(first.get(0).getResponse().getContentAsString());
      assertThat(result.getResponse().getHeader("Retry-After")).isNull();
    }
    // 쿨다운도 가입 여부와 상관없이 똑같이 걸린다
    for (MvcResult result : second) {
      assertThat(result.getResponse().getStatus()).isEqualTo(429);
      assertThat(result.getResponse().getContentAsString())
          .isEqualTo(second.get(0).getResponse().getContentAsString())
          .contains("USERS_RESET_RATE_LIMITED");
      assertThat(result.getResponse().getHeader("Retry-After")).isEqualTo("40");
    }
  }

  private MvcResult sendRaw(String address) throws Exception {
    return send(address).andReturn();
  }

  @Test
  void send_overTheHourlyLimit_returns429WithALongRetryAfter() throws Exception {
    for (int i = 0; i < 5; i++) {
      send(unknown).andExpect(status().isAccepted());
      clock.advance(Duration.ofSeconds(61));
    }

    send(unknown)
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_RESET_RATE_LIMITED"))
        .andExpect(header().string("Retry-After", String.valueOf(3600 - 5 * 61)));
  }

  @Test
  void resend_invalidatesThePreviousCode() throws Exception {
    String first = sendAndGetCode(registered);
    clock.advance(Duration.ofSeconds(61));
    String second = sendAndGetCode(registered);

    if (!first.equals(second)) {
      verify(registered, first)
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_INVALID"));
    }
    verify(registered, second).andExpect(status().isOk());
  }

  @Test
  void aFailedCodeMail_returns503AndCanBeRetriedRightAway() throws Exception {
    mail.failing = true;

    send(registered)
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("USERS_RESET_SEND_FAILED"));

    mail.failing = false;
    // 예약이 되돌려져 쿨다운에 걸리지 않는다
    send(registered).andExpect(status().isAccepted());
    assertThat(mail.resetCodes).hasSize(1);
  }

  @Test
  void aFailedGoogleNotice_returns503AndCanBeRetriedRightAway() throws Exception {
    mail.failing = true;

    send(googleOnly)
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("USERS_RESET_SEND_FAILED"));

    mail.failing = false;
    send(googleOnly).andExpect(status().isAccepted());
    assertThat(mail.googleNotices).containsExactly(googleOnly);
  }

  @Test
  void aFailureAfterTheReservation_givesTheReservationBack() throws Exception {
    doThrow(new DataAccessResourceFailureException("db down"))
        .when(userRepository)
        .findByEmail(registered);

    send(registered)
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"));

    org.mockito.Mockito.reset(userRepository);
    // 쿨다운·시간당 횟수가 줄지 않았다
    send(registered).andExpect(status().isAccepted());
    assertThat(mail.resetCodes).hasSize(1);
  }

  @Test
  void send_rejectsAnInvalidEmail() throws Exception {
    send("not-an-email")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void send_rejectsARequestWithoutAnAllowedOrigin() throws Exception {
    mockMvc
        .perform(
            post(SEND)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\": \"" + registered + "\"}"))
        .andExpect(status().isForbidden());
    assertThat(mail.resetCodes).isEmpty();
  }

  // ---- 확인 ----

  @Test
  void verify_withTheRightCode_returnsAResetTokenForThatEmail() throws Exception {
    String code = sendAndGetCode(registered);

    MvcResult result =
        verify(registered, code)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.expiresAt").value("2026-10-27T00:10:00Z"))
            .andReturn();

    String token = tokenOf(result);
    assertThat(token).isNotBlank();
    assertThat(resetStore.findTokenEmail(hasher.hashToken(token), T0)).contains(registered);
  }

  @Test
  void verify_aCodeCanBeUsedOnlyOnce() throws Exception {
    String code = sendAndGetCode(registered);
    verify(registered, code).andExpect(status().isOk());

    verify(registered, code)
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_EXPIRED"));
  }

  @Test
  void verify_afterTheCodeExpired_returns410() throws Exception {
    String code = sendAndGetCode(registered);
    clock.advance(Duration.ofMinutes(10));

    verify(registered, code)
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_EXPIRED"));
  }

  @Test
  void verify_tooManyWrongCodes_blocksEvenTheRightOne() throws Exception {
    String code = sendAndGetCode(registered);
    for (int i = 0; i < 5; i++) {
      verify(registered, wrongCodeFor(code))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_INVALID"));
    }

    verify(registered, code)
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_ATTEMPTS_EXCEEDED"));
  }

  @Test
  void verify_withoutARequest_looksTheSameForRegisteredAndUnknownEmails() throws Exception {
    String registeredBody =
        verify(registered, "123456")
            .andExpect(status().isGone())
            .andReturn()
            .getResponse()
            .getContentAsString();
    String unknownBody =
        verify(unknown, "123456")
            .andExpect(status().isGone())
            .andReturn()
            .getResponse()
            .getContentAsString();

    assertThat(unknownBody).isEqualTo(registeredBody);
  }

  @Test
  void verify_behavesTheSameForUnknownAndGoogleOnlyEmailsAsForARegisteredOne() throws Exception {
    for (String address : List.of(registered, googleOnly, unknown)) {
      send(address).andExpect(status().isAccepted());
      // 가입하지 않았거나 비밀번호가 없는 이메일은 맞힐 수 있는 인증번호가 없다. 틀림·시도 초과가 똑같이 나온다
      for (int i = 0; i < 5; i++) {
        verify(address, "%06d".formatted(i))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_INVALID"));
      }
      verify(address, "999999")
          .andExpect(status().isTooManyRequests())
          .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_ATTEMPTS_EXCEEDED"));
    }
  }

  @Test
  void verify_codesOfUnknownAndGoogleOnlyEmailsExpireLikeRealOnes() throws Exception {
    for (String address : List.of(registered, googleOnly, unknown)) {
      send(address).andExpect(status().isAccepted());
    }
    clock.advance(Duration.ofMinutes(10));

    for (String address : List.of(registered, googleOnly, unknown)) {
      verify(address, "123456")
          .andExpect(status().isGone())
          .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_EXPIRED"));
    }
  }

  @Test
  void verifyingAgainReplacesThePreviousToken() throws Exception {
    String firstToken = tokenOf(verify(registered, sendAndGetCode(registered)).andReturn());
    clock.advance(Duration.ofSeconds(61));

    String secondToken = tokenOf(verify(registered, sendAndGetCode(registered)).andReturn());

    assertThat(resetStore.findTokenEmail(hasher.hashToken(firstToken), clock.instant())).isEmpty();
    assertThat(resetStore.findTokenEmail(hasher.hashToken(secondToken), clock.instant()))
        .contains(registered);
  }

  @Test
  void aSignupVerificationCodeCannotBeUsedToResetThePassword() throws Exception {
    mockMvc
        .perform(request("/v1/users/email-verification", "{\"email\": \"" + unknown + "\"}"))
        .andExpect(status().isAccepted());
    String signupCode = mail.last().code();

    verify(unknown, signupCode)
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_RESET_CODE_EXPIRED"));
  }

  @Test
  void verify_rejectsAMalformedCode() throws Exception {
    verify(registered, "12ab56")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  // ---- 같은 이메일의 동시 요청 ----

  @Test
  void whileAnotherRequestForTheSameEmailIsRunning_bothApisAnswer429AtOnce() throws Exception {
    String code = sendAndGetCode(registered);
    CountDownLatch held = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    // 잠금은 같은 스레드에서 다시 잡을 수 있어서, 다른 스레드가 잡고 있게 한다
    pool.submit(
        () -> {
          try (var lock = locks.tryLock(registered).orElseThrow()) {
            held.countDown();
            release.await(30, TimeUnit.SECONDS);
          }
          return null;
        });
    assertThat(held.await(10, TimeUnit.SECONDS)).isTrue();
    clock.advance(Duration.ofSeconds(61));

    try {
      send(registered)
          .andExpect(status().isTooManyRequests())
          .andExpect(jsonPath("$.code").value("TOO_MANY_REQUESTS"))
          .andExpect(header().string("Retry-After", "1"));
      verify(registered, code)
          .andExpect(status().isTooManyRequests())
          .andExpect(jsonPath("$.code").value("TOO_MANY_REQUESTS"))
          .andExpect(header().string("Retry-After", "1"));
    } finally {
      release.countDown();
    }
    pool.shutdown();
    assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();

    // 거절된 확인은 시도로 세지 않았고 인증번호도 그대로다
    verify(registered, code).andExpect(status().isOk());
  }

  // ---- 로그 ----

  @Test
  void neitherTheCodeNorTheTokenIsLogged(CapturedOutput output) throws Exception {
    int before = output.getAll().length();
    String code = sendAndGetCode(registered);
    String token = tokenOf(verify(registered, code).andExpect(status().isOk()).andReturn());

    assertThat(outputSince(output, before)).doesNotContain(code).doesNotContain(token);
  }

  /**
   * 이 테스트가 시작된 뒤에 나온 출력. 캡처는 클래스가 시작될 때부터 쌓이는데, 같은 클래스의 다른 테스트가 실패하면 MockMvc 가 그 요청 본문(테스트용 비밀번호
   * 포함)을 출력해서 앱 로그가 아닌 것까지 섞이기 때문이다.
   */
  private static String outputSince(CapturedOutput output, int before) {
    return output.getAll().substring(before);
  }

  // ---- 새 비밀번호 저장 (입력·토큰 규칙) ----

  @Test
  void save_withAValidToken_changesThePasswordAndRaisesTheVersion() throws Exception {
    String token = tokenFor(registered);

    save(token, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());

    User user = userRepository.findByEmail(registered).orElseThrow();
    assertThat(passwordEncoder.matches(NEW_PASSWORD, user.getPasswordHash())).isTrue();
    assertThat(user.getPasswordVersion()).isEqualTo(1);
  }

  @Test
  void save_aMismatchedConfirmation_isRejectedAndKeepsTheToken() throws Exception {
    String token = tokenFor(registered);

    save(token, NEW_PASSWORD, NEW_PASSWORD + "x")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("newPasswordConfirm"));

    // 토큰은 그대로라 고쳐서 다시 보낼 수 있다
    save(token, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());
  }

  @Test
  void save_aWeakPassword_isRejectedAndKeepsTheToken() throws Exception {
    String token = tokenFor(registered);

    save(token, "onlyletters", "onlyletters")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("newPassword"));

    save(token, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());
  }

  @Test
  void save_aPasswordOver72Bytes_isRejected() throws Exception {
    // 28자라 길이 규칙은 통과하지만 한글 24자가 72바이트라 모두 합치면 넘는다
    String tooLong = "가".repeat(24) + "Aa1!";
    String token = tokenFor(registered);

    save(token, tooLong, tooLong)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("newPassword"));
  }

  @Test
  void save_withAnUnknownToken_returns410() throws Exception {
    save("not-a-real-token", NEW_PASSWORD, NEW_PASSWORD)
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_RESET_TOKEN_EXPIRED"));
  }

  @Test
  void save_afterTheTokenExpired_returns410AndChangesNothing() throws Exception {
    String token = tokenFor(registered);
    clock.advance(Duration.ofMinutes(10));

    save(token, NEW_PASSWORD, NEW_PASSWORD)
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_RESET_TOKEN_EXPIRED"));

    assertThat(userRepository.findByEmail(registered).orElseThrow().getPasswordVersion()).isZero();
  }

  @Test
  void save_aTokenCanBeUsedOnlyOnce() throws Exception {
    String token = tokenFor(registered);
    save(token, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());

    save(token, "Another1!pass", "Another1!pass")
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_RESET_TOKEN_EXPIRED"));
  }

  @Test
  void save_withAReplacedToken_returns410() throws Exception {
    String first = tokenFor(registered);
    clock.advance(Duration.ofSeconds(61));
    String second = tokenFor(registered);

    save(first, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isGone());
    save(second, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());
  }

  @Test
  void save_rejectsARequestWithoutAnAllowedOrigin() throws Exception {
    String token = tokenFor(registered);

    mockMvc
        .perform(
            put(SAVE)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"resetToken\": \"%s\", \"newPassword\": \"%s\", \"newPasswordConfirm\": \"%s\"}"
                        .formatted(token, NEW_PASSWORD, NEW_PASSWORD)))
        .andExpect(status().isForbidden());
    assertThat(userRepository.findByEmail(registered).orElseThrow().getPasswordVersion()).isZero();
  }

  @Test
  void save_whileAnotherRequestForTheSameEmailIsRunning_answers429() throws Exception {
    String token = tokenFor(registered);
    CountDownLatch held = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    pool.submit(
        () -> {
          try (var lock = locks.tryLock(registered).orElseThrow()) {
            held.countDown();
            release.await(30, TimeUnit.SECONDS);
          }
          return null;
        });
    assertThat(held.await(10, TimeUnit.SECONDS)).isTrue();

    try {
      save(token, NEW_PASSWORD, NEW_PASSWORD)
          .andExpect(status().isTooManyRequests())
          .andExpect(jsonPath("$.code").value("TOO_MANY_REQUESTS"))
          .andExpect(header().string("Retry-After", "1"));
    } finally {
      release.countDown();
    }
    pool.shutdown();
    assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();

    save(token, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());
  }

  @Test
  void save_neitherTheTokenNorThePasswordIsLogged(CapturedOutput output) throws Exception {
    int before = output.getAll().length();
    String token = tokenFor(registered);

    save(token, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());

    assertThat(outputSince(output, before)).doesNotContain(token).doesNotContain(NEW_PASSWORD);
  }

  @Test
  void save_whenTheUpdateChangesNoRow_returns410AndSkipsEverythingAfterIt() throws Exception {
    String token = tokenFor(registered);
    double successes = successCount();
    // 조회한 뒤 갱신하기 전에 회원이 사라진 상황: 갱신된 행이 없다
    doReturn(0).when(userRepository).updatePassword(any(), anyString(), any());

    save(token, NEW_PASSWORD, NEW_PASSWORD)
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_RESET_TOKEN_EXPIRED"));

    org.mockito.Mockito.verify(userSessionService, never()).revokeAll(any(), any());
    assertThat(successCount()).isEqualTo(successes);
    // 토큰을 폐기하지 않았다: 갱신이 실제로 되면 같은 토큰으로 마무리된다
    org.mockito.Mockito.reset(userRepository);
    save(token, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());
  }

  private double successCount() {
    Counter counter = registry.find("mairor.password_reset").tag("result", "success").counter();
    return counter == null ? 0 : counter.count();
  }

  @Test
  void save_theCurrentPassword_isRejectedAndKeepsTheToken() throws Exception {
    String current = "Current1!pass";
    String address = "current-" + id + "@example.com";
    userRepository.saveAndFlush(new User(address, passwordEncoder.encode(current)));
    String token = tokenFor(address);

    save(token, current, current)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("newPassword"))
        .andExpect(jsonPath("$.details[0].reason").value("현재 비밀번호와 다른 비밀번호를 입력해 주세요."));

    User unchanged = userRepository.findByEmail(address).orElseThrow();
    assertThat(unchanged.getPasswordVersion()).isZero();
    // 토큰은 그대로라 다른 비밀번호로 다시 보낼 수 있다
    save(token, NEW_PASSWORD, NEW_PASSWORD).andExpect(status().isNoContent());
  }

  @Test
  void save_theCurrentPasswordTypedInAnotherUnicodeForm_isAlsoRejected() throws Exception {
    String nfc = "한글Pass1!";
    String nfd = java.text.Normalizer.normalize(nfc, java.text.Normalizer.Form.NFD);
    String address = "unicode-" + id + "@example.com";
    userRepository.saveAndFlush(new User(address, passwordEncoder.encode(nfc)));
    String token = tokenFor(address);

    save(token, nfd, nfd)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("newPassword"));
  }
}
