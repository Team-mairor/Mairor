package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.VerificationTestSupport;
import com.mairor.backend.users.VerificationTestSupport.CapturingMailSender;
import com.mairor.backend.users.VerificationTestSupport.MutableClock;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.EmailVerificationStore;
import com.mairor.backend.users.support.VerificationHasher;
import java.time.Duration;
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
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.transaction.annotation.Transactional;

/**
 * 가입에 이메일 인증을 요구할 때({@code app.signup.require-email-verification=true})의 흐름: 인증번호 발송 → 확인(토큰) → 가입.
 * 설정을 끈 기본 동작은 다른 가입 테스트가 이미 확인한다(토큰 없이 가입 성공).
 */
@Import({TestcontainersConfiguration.class, VerificationTestSupport.TestBeans.class})
@SpringBootTest(
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.signup.require-email-verification=true",
      "app.rate-limit.email-verification.limit=1000"
    })
@AutoConfigureMockMvc
@Transactional
@ExtendWith(OutputCaptureExtension.class)
class UserSignUpEmailVerificationTest {

  private static final String ORIGIN = "http://localhost:3000";
  private static final String PASSWORD = "ExampleOnly!2026";
  private static final AtomicInteger IPS = new AtomicInteger();

  @Autowired private MockMvc mockMvc;
  @Autowired private CapturingMailSender mail;
  @Autowired private MutableClock clock;
  @Autowired private VerificationHasher hasher;
  @Autowired private UserRepository userRepository;

  @MockitoSpyBean private EmailVerificationStore store;

  private final String email = "verified-" + UUID.randomUUID() + "@example.com";
  private final String ip = "10.8." + IPS.incrementAndGet() / 250 + "." + IPS.get() % 250;

  @BeforeEach
  void setUp() {
    clock.set(VerificationTestSupport.T0);
    mail.failing = false;
    mail.sent.clear();
  }

  private ResultActions call(String url, String json) throws Exception {
    return mockMvc.perform(
        post(url)
            .header("Origin", ORIGIN)
            .contentType(MediaType.APPLICATION_JSON)
            .content(json)
            .with(
                r -> {
                  r.setRemoteAddr(ip);
                  return r;
                }));
  }

  /** 인증번호를 받고 확인해서 토큰을 얻는다. */
  private String verify(String address) throws Exception {
    call("/v1/users/email-verification", "{\"email\": \"" + address + "\"}")
        .andExpect(status().isAccepted());
    String code = mail.last().code();
    String json =
        call(
                "/v1/users/email-verification/verification",
                "{\"email\": \"" + address + "\", \"code\": \"" + code + "\"}")
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    return JsonPath.read(json, "$.verificationToken");
  }

  private ResultActions signUp(String address, String token) throws Exception {
    return call("/v1/users/signup", signUpJson(address, PASSWORD, PASSWORD, token));
  }

  private static String signUpJson(String address, String password, String confirm, String token) {
    String tokenField = token == null ? "" : ", \"emailVerificationToken\": \"" + token + "\"";
    return """
        {"email": "%s", "password": "%s", "passwordConfirm": "%s", "agreements": %s%s}"""
        .formatted(address, password, confirm, SignUpRequests.AGREEMENTS_JSON, tokenField);
  }

  private boolean tokenStillValid(String token, String address) {
    return store.hasValidToken(hasher.hashToken(token), address, clock.instant());
  }

  // ---- 성공 ----

  @Test
  void signUp_withAVerifiedToken_succeeds_recordsTheTimeAndDiscardsTheToken() throws Exception {
    String token = verify(email);

    signUp(email, token)
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.email").value(email))
        .andExpect(jsonPath("$.emailVerificationToken").doesNotExist());

    var saved = userRepository.findByEmail(email).orElseThrow();
    assertThat(saved.getEmailVerifiedAt()).isEqualTo(VerificationTestSupport.T0);
    assertThat(tokenStillValid(token, email)).isFalse();
  }

  @Test
  void signUp_afterTheTokenWasUsed_cannotReuseIt() throws Exception {
    String token = verify(email);
    signUp(email, token).andExpect(status().isCreated());

    String other = "other-" + email;
    signUp(other, token)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_NOT_VERIFIED"));
    assertThat(userRepository.existsByEmail(other)).isFalse();
  }

  // ---- 거절 ----

  @Test
  void signUp_withoutAToken_returns400NotVerified_andSavesNothing() throws Exception {
    signUp(email, null)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_NOT_VERIFIED"));

    assertThat(userRepository.existsByEmail(email)).isFalse();
  }

  @Test
  void signUp_withABlankOrUnknownToken_returns400NotVerified() throws Exception {
    for (String token : new String[] {"", "   ", "not-a-real-token"}) {
      signUp(email, token)
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("USERS_EMAIL_NOT_VERIFIED"));
    }
    assertThat(userRepository.existsByEmail(email)).isFalse();
  }

  @Test
  void signUp_withAnotherEmailsToken_returns400NotVerified() throws Exception {
    String token = verify("someone-" + email);

    signUp(email, token)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_NOT_VERIFIED"));

    // 그 토큰은 원래 이메일을 위해 여전히 유효하다
    assertThat(tokenStillValid(token, "someone-" + email)).isTrue();
  }

  @Test
  void signUp_withAnExpiredToken_returns400NotVerified() throws Exception {
    String token = verify(email);
    clock.advance(Duration.ofMinutes(30));

    signUp(email, token)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_NOT_VERIFIED"));
  }

  @Test
  void signUp_justBeforeTheTokenExpires_stillWorks() throws Exception {
    String token = verify(email);
    clock.advance(Duration.ofMinutes(30).minusSeconds(1));

    signUp(email, token).andExpect(status().isCreated());
  }

  @Test
  void cheapValidationFailuresComeBeforeTheTokenCheck() throws Exception {
    // 인증을 안 한 채로 비밀번호 확인값이 틀리면 토큰 오류가 아니라 입력 오류를 먼저 알려 준다
    call("/v1/users/signup", signUpJson(email, PASSWORD, "different-Pass1!", null))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("passwordConfirm"));
  }

  // ---- 실패해도 토큰은 남는다 ----

  @Test
  void aFailedSignUp_keepsTheToken_soTheSameTokenCanRetry() throws Exception {
    String token = verify(email);

    call("/v1/users/signup", signUpJson(email, PASSWORD, "different-Pass1!", token))
        .andExpect(status().isBadRequest());
    call(
            "/v1/users/signup",
            """
            {"email": "%s", "password": "%s", "passwordConfirm": "%s", "agreements": [],
             "emailVerificationToken": "%s"}"""
                .formatted(email, PASSWORD, PASSWORD, token))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_REQUIRED_AGREEMENT_MISSING"));

    assertThat(tokenStillValid(token, email)).isTrue();
    signUp(email, token).andExpect(status().isCreated());
  }

  @Test
  void signUp_whenTheEmailWasTakenInTheMeantime_returns409_andKeepsTheToken() throws Exception {
    String token = verify(email);
    userRepository.saveAndFlush(new User(email, "{bcrypt}taken"));

    signUp(email, token)
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_DUPLICATE"));

    assertThat(tokenStillValid(token, email)).isTrue();
  }

  @Test
  void aFailureToDiscardTheToken_doesNotFailTheSignUp() throws Exception {
    String token = verify(email);
    doThrow(new IllegalStateException("store down")).when(store).deleteToken(anyString());

    signUp(email, token).andExpect(status().isCreated());

    assertThat(userRepository.existsByEmail(email)).isTrue();
  }

  // ---- 노출 방지 ----

  @Test
  void theTokenIsNeitherEchoedNorLogged(CapturedOutput output) throws Exception {
    String token = verify(email);

    String body =
        signUp(email, token)
            .andExpect(status().isCreated())
            .andExpect(
                content()
                    .string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString(token))))
            .andReturn()
            .getResponse()
            .getContentAsString();

    assertThat(body).doesNotContain(token);
    assertThat(output.getAll()).doesNotContain(token);
  }
}
