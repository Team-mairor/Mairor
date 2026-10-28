package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.VerificationTestSupport;
import com.mairor.backend.users.VerificationTestSupport.CapturingMailSender;
import com.mairor.backend.users.VerificationTestSupport.MutableClock;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.service.UserSignUpService;
import com.mairor.backend.users.support.EmailVerificationStore;
import com.mairor.backend.users.support.VerificationHasher;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;

/**
 * 가입 이메일 인증번호 발송·확인 API 계약 (API-USERS-012·013). 가입과 마찬가지로 인증·CSRF 토큰 없이 허용 Origin 헤더만 보낸다.
 *
 * <p>실제 메일 대신 보낸 메일을 모아 두는 발송기를 쓰고, 시간은 테스트가 움직일 수 있는 시계로 바꿔 쿨다운·만료를 기다리지 않고 확인한다. 인증 상태는 메모리에 있어
 * 테스트끼리 섞이지 않도록 테스트마다 새 이메일과 새 클라이언트 IP 를 쓴다.
 */
@Import({TestcontainersConfiguration.class, VerificationTestSupport.TestBeans.class})
@SpringBootTest(
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.rate-limit.email-verification.limit=1000"
    })
@AutoConfigureMockMvc
@Transactional
@ExtendWith(OutputCaptureExtension.class)
class EmailVerificationControllerTest {

  private static final Instant T0 = VerificationTestSupport.T0;
  private static final String ORIGIN = "http://localhost:3000";
  private static final String SEND = "/v1/users/email-verification";
  private static final String CONFIRM = "/v1/users/email-verification/verification";
  private static final AtomicInteger IPS = new AtomicInteger();

  @Autowired private MockMvc mockMvc;
  @Autowired private CapturingMailSender mail;
  @Autowired private MutableClock clock;
  @Autowired private EmailVerificationStore store;
  @Autowired private VerificationHasher hasher;
  @Autowired private UserRepository userRepository;
  @Autowired private UserSignUpService signUpService;

  private final String email = "verify-" + UUID.randomUUID() + "@example.com";
  private final String ip = "10.9." + IPS.incrementAndGet() / 250 + "." + IPS.get() % 250;

  @BeforeEach
  void setUp() {
    clock.set(T0);
    mail.failing = false;
    mail.sent.clear();
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

  private ResultActions confirm(String address, String code) throws Exception {
    return mockMvc.perform(
        request(CONFIRM, "{\"email\": \"" + address + "\", \"code\": \"" + code + "\"}"));
  }

  private String sendAndGetCode(String address) throws Exception {
    send(address).andExpect(status().isAccepted());
    return mail.last().code();
  }

  private static String wrongCodeFor(String code) {
    return code.equals("000000") ? "000001" : "000000";
  }

  // ---- 발송 ----

  @Test
  void send_returns202WithTimes_andMailsASixDigitCode() throws Exception {
    send(email)
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.expiresInSeconds").value(600))
        .andExpect(jsonPath("$.resendAvailableInSeconds").value(60));

    assertThat(mail.sent).hasSize(1);
    assertThat(mail.last().to()).isEqualTo(email);
    assertThat(mail.last().code()).matches("\\d{6}");
    assertThat(mail.last().validFor()).isEqualTo(Duration.ofMinutes(10));
  }

  @Test
  void send_normalizesTheEmail() throws Exception {
    send("  " + email.toUpperCase() + " ").andExpect(status().isAccepted());

    assertThat(mail.last().to()).isEqualTo(email);
  }

  @Test
  void send_toARegisteredEmail_returns409AndSendsNothing() throws Exception {
    signUpService.signUp(
        SignUpRequests.basic("taken@example.com", "ExampleOnly!2026", "ExampleOnly!2026"));

    send("taken@example.com")
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_DUPLICATE"));

    assertThat(mail.sent).isEmpty();
  }

  @Test
  void send_withinTheCooldown_returns429WithRetryAfter_andSendsNoSecondMail() throws Exception {
    send(email).andExpect(status().isAccepted());
    clock.advance(Duration.ofSeconds(20));

    send(email)
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_SEND_RATE_LIMITED"))
        .andExpect(header().string("Retry-After", "40"));

    assertThat(mail.sent).hasSize(1);
  }

  @Test
  void send_afterTheCooldown_isAllowedAgain() throws Exception {
    send(email).andExpect(status().isAccepted());
    clock.advance(Duration.ofSeconds(60));

    send(email).andExpect(status().isAccepted());

    assertThat(mail.sent).hasSize(2);
  }

  @Test
  void send_overTheHourlyLimit_returns429WithALongRetryAfter() throws Exception {
    for (int i = 0; i < 5; i++) {
      send(email).andExpect(status().isAccepted());
      clock.advance(Duration.ofSeconds(61));
    }

    // 5번 보냈고 마지막 발송 후 61초가 지나 쿨다운은 아니지만, 시간당 한도에 걸린다
    send(email)
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_SEND_RATE_LIMITED"))
        .andExpect(header().string("Retry-After", String.valueOf(3600 - 5 * 61)));
    assertThat(mail.sent).hasSize(5);
  }

  @Test
  void send_limitsAreTrackedPerEmail() throws Exception {
    send(email).andExpect(status().isAccepted());

    send("other-" + email).andExpect(status().isAccepted());
  }

  @Test
  void resend_invalidatesThePreviousCode() throws Exception {
    String first = sendAndGetCode(email);
    clock.advance(Duration.ofSeconds(61));
    String second = sendAndGetCode(email);
    // 우연히 같은 번호가 나오면 이전 코드 무효를 확인할 수 없으니 건너뛴다
    org.junit.jupiter.api.Assumptions.assumeFalse(first.equals(second));

    confirm(email, first)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_INVALID"));
    confirm(email, second).andExpect(status().isOk());
  }

  @Test
  void send_whenTheMailFails_returns503_andAllowsAnImmediateRetry() throws Exception {
    mail.failing = true;

    send(email)
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_SEND_FAILED"));

    mail.failing = false;
    // 실패한 발송은 쿨다운과 시간당 횟수에서 빠지므로 기다리지 않고 다시 보낼 수 있다
    send(email).andExpect(status().isAccepted());
    assertThat(mail.sent).hasSize(1);
  }

  @Test
  void send_whenTheMailFails_discardsTheSavedCode() throws Exception {
    mail.failing = true;
    send(email).andExpect(status().isServiceUnavailable());

    confirm(email, "123456")
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_EXPIRED"));
  }

  @Test
  void send_withInvalidEmail_returns400() throws Exception {
    for (String invalid : new String[] {"plain", "a@b", "", "   "}) {
      send(invalid)
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
          .andExpect(jsonPath("$.details[0].field").value("email"));
    }
    assertThat(mail.sent).isEmpty();
  }

  // ---- 확인 ----

  @Test
  void confirm_withTheRightCode_returnsAToken() throws Exception {
    String code = sendAndGetCode(email);

    String json =
        confirm(email, code)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.verificationToken").isString())
            .andExpect(jsonPath("$.expiresAt").value("2026-10-27T00:30:00Z"))
            .andReturn()
            .getResponse()
            .getContentAsString();

    String token = com.jayway.jsonpath.JsonPath.read(json, "$.verificationToken");
    assertThat(token).matches("[A-Za-z0-9_-]{43}");
    // 토큰은 저장소에 해시로 들어 있고 그 이메일에서만 유효하다
    assertThat(store.hasValidToken(hasher.hashToken(token), email, clock.instant())).isTrue();
    assertThat(store.hasValidToken(hasher.hashToken(token), "other@example.com", clock.instant()))
        .isFalse();
  }

  @Test
  void confirm_issuesADifferentTokenEachTime() throws Exception {
    String first = tokenFor(email);
    clock.advance(Duration.ofSeconds(61));
    String second = tokenFor(email);

    assertThat(first).isNotEqualTo(second);
  }

  private String tokenFor(String address) throws Exception {
    String code = sendAndGetCode(address);
    String json =
        confirm(address, code)
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    return com.jayway.jsonpath.JsonPath.read(json, "$.verificationToken");
  }

  @Test
  void confirm_withAWrongCode_returns400_andTheRightCodeStillWorks() throws Exception {
    String code = sendAndGetCode(email);

    confirm(email, wrongCodeFor(code))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_INVALID"));
    confirm(email, code).andExpect(status().isOk());
  }

  @Test
  void confirm_aCodeWorksOnlyOnce() throws Exception {
    String code = sendAndGetCode(email);
    confirm(email, code).andExpect(status().isOk());

    confirm(email, code)
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_EXPIRED"));
  }

  @Test
  void confirm_afterTooManyWrongAttempts_returns429_evenWithTheRightCode() throws Exception {
    String code = sendAndGetCode(email);
    for (int i = 0; i < 5; i++) {
      confirm(email, wrongCodeFor(code))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_INVALID"));
    }

    confirm(email, code)
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_ATTEMPTS_EXCEEDED"));
  }

  @Test
  void confirm_afterResending_theAttemptCountStartsOver() throws Exception {
    String code = sendAndGetCode(email);
    for (int i = 0; i < 5; i++) {
      confirm(email, wrongCodeFor(code));
    }
    clock.advance(Duration.ofSeconds(61));

    String fresh = sendAndGetCode(email);

    confirm(email, fresh).andExpect(status().isOk());
  }

  @Test
  void confirm_afterTheCodeExpired_returns410() throws Exception {
    String code = sendAndGetCode(email);
    clock.advance(Duration.ofMinutes(10));

    confirm(email, code)
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_EXPIRED"));
  }

  @Test
  void confirm_justBeforeExpiry_stillWorks() throws Exception {
    String code = sendAndGetCode(email);
    clock.advance(Duration.ofMinutes(10).minusSeconds(1));

    confirm(email, code).andExpect(status().isOk());
  }

  @Test
  void confirm_withoutEverSending_returns410LikeAnExpiredCode() throws Exception {
    confirm(email, "123456")
        .andExpect(status().isGone())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_EXPIRED"));
  }

  @Test
  void confirm_aCodeSentToAnotherEmailDoesNotWork() throws Exception {
    String code = sendAndGetCode(email);
    String other = "other-" + email;
    String otherCode = sendAndGetCode(other);
    // 우연히 같은 번호가 나오면 확인할 수 없으니 건너뛴다
    org.junit.jupiter.api.Assumptions.assumeFalse(code.equals(otherCode));

    confirm(other, code)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CODE_INVALID"));
  }

  @Test
  void confirm_withMalformedCode_returns400WithCodeField() throws Exception {
    for (String bad : new String[] {"12345", "1234567", "abcdef", "12 456", ""}) {
      confirm(email, bad)
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
          .andExpect(jsonPath("$.details[0].field").value("code"));
    }
  }

  @Test
  void confirm_withMissingFields_returns400() throws Exception {
    mockMvc
        .perform(request(CONFIRM, "{\"email\": \"" + email + "\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("code"));
    mockMvc
        .perform(request(CONFIRM, "{\"code\": \"123456\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("email"));
  }

  // ---- 공통: Origin·CSRF·미디어 타입 ----

  @Test
  void withoutOrigin_returns403() throws Exception {
    mockMvc
        .perform(
            post(SEND)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\": \"" + email + "\"}"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    mockMvc
        .perform(
            post(CONFIRM)
                .header("Origin", "https://evil.com")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\": \"" + email + "\", \"code\": \"123456\"}"))
        .andExpect(status().isForbidden());
    assertThat(mail.sent).isEmpty();
  }

  @Test
  void nonJsonContentType_returns415() throws Exception {
    mockMvc
        .perform(post(SEND).header("Origin", ORIGIN).contentType(MediaType.TEXT_PLAIN).content("x"))
        .andExpect(status().isUnsupportedMediaType());
    mockMvc
        .perform(
            post(CONFIRM).header("Origin", ORIGIN).contentType(MediaType.TEXT_PLAIN).content("x"))
        .andExpect(status().isUnsupportedMediaType());
  }

  @Test
  void otherMethodsAndSubPaths_stillRequireLoginOrCsrf() throws Exception {
    mockMvc.perform(get(SEND)).andExpect(status().isUnauthorized());
    mockMvc.perform(get(CONFIRM)).andExpect(status().isUnauthorized());
    for (MockHttpServletRequestBuilder builder :
        List.of(put(SEND), put(CONFIRM), post(SEND + "/anything"), post(CONFIRM + "/anything"))) {
      mockMvc
          .perform(
              builder
                  .header("Origin", ORIGIN)
                  .contentType(MediaType.APPLICATION_JSON)
                  .content("{}"))
          .andExpect(status().isForbidden())
          .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
    }
  }

  // ---- 로그 ----

  @Test
  void neitherTheEmailNorTheTokenIsLogged(CapturedOutput output) throws Exception {
    String code = sendAndGetCode(email);
    confirm(email, wrongCodeFor(code));
    String json = confirm(email, code).andReturn().getResponse().getContentAsString();
    String token = com.jayway.jsonpath.JsonPath.read(json, "$.verificationToken");

    // 6자리 숫자는 로그의 다른 숫자와 우연히 겹칠 수 있어 인증번호 자체는 확인하지 않는다 (요청 toString 이 가린다)
    assertThat(output.getAll()).doesNotContain(email).doesNotContain(token);
    assertThat(userRepository.existsByEmail(email)).isFalse();
  }
}
