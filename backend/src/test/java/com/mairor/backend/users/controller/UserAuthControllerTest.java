package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import java.text.Normalizer;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;

/**
 * 로그인·로그아웃·내 계정 조회의 응답 계약과 오류 분기 (API-USERS-002·003·004). 실제 호출 조건 그대로 인증·CSRF 토큰 없이 허용 Origin 헤더만
 * 보낸다. 세션·쿠키가 서버 안에서 어떻게 이어지는지는 {@code SessionFlowIntegrationTest} 에서 실제 HTTP 로 확인한다.
 *
 * <p>시도 제한 상태는 앱 안에서 이메일별로 공유되므로 테스트마다 서로 다른 이메일을 쓴다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "app.security.allowed-origins=http://localhost:3000")
@AutoConfigureMockMvc
@Transactional
class UserAuthControllerTest {

  private static final String ORIGIN = "http://localhost:3000";
  private static final String PASSWORD = "ExampleOnly!2026";

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private PasswordEncoder passwordEncoder;

  private static String uniqueEmail() {
    return "auth-" + UUID.randomUUID() + "@example.com";
  }

  private User member(String email, String password) {
    return userRepository.saveAndFlush(new User(email, passwordEncoder.encode(password)));
  }

  private static String json(String email, String password) {
    return "{\"email\": %s, \"password\": %s}".formatted(quote(email), quote(password));
  }

  private static String quote(String value) {
    return value == null ? "null" : "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
  }

  private static MockHttpServletRequestBuilder login(String json) {
    return post("/v1/users/login")
        .header("Origin", ORIGIN)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }

  private String loginBody(String email, String password) throws Exception {
    return mockMvc
        .perform(login(json(email, password)))
        .andReturn()
        .getResponse()
        .getContentAsString();
  }

  // ---- 성공 ----

  @Test
  void login_returns200WithTheUserAndACsrfTokenAndNeverCaches() throws Exception {
    String email = uniqueEmail();
    User saved = member(email, PASSWORD);

    MvcResult result =
        mockMvc
            .perform(login(json(email, PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.user.userId").value(saved.getId().toString()))
            .andExpect(jsonPath("$.user.email").value(email))
            .andExpect(jsonPath("$.user.provider").value("LOCAL"))
            .andExpect(jsonPath("$.csrfToken").isNotEmpty())
            .andReturn();

    String body = result.getResponse().getContentAsString();
    assertThat(body).doesNotContain(PASSWORD).doesNotContain(saved.getPasswordHash());
    assertThat(body).doesNotContain("passwordHash").doesNotContain("password");
  }

  @Test
  void login_looksUpTheNormalizedEmail() throws Exception {
    String email = uniqueEmail();
    member(email, PASSWORD);

    mockMvc
        .perform(login(json("  " + email.toUpperCase() + " ", PASSWORD)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.user.email").value(email));
  }

  @Test
  void login_acceptsAPasswordTypedInTheDecomposedUnicodeForm() throws Exception {
    String email = uniqueEmail();
    String nfc = "한글Pass1!";
    member(email, nfc);
    String nfd = Normalizer.normalize(nfc, Normalizer.Form.NFD);
    assertThat(nfd).isNotEqualTo(nfc);

    mockMvc.perform(login(json(email, nfd))).andExpect(status().isOk());
  }

  @Test
  void login_doesNotApplyPasswordStrengthRules() throws Exception {
    String email = uniqueEmail();
    member(email, "a");

    mockMvc.perform(login(json(email, "a"))).andExpect(status().isOk());
  }

  // ---- 실패: 원인을 구분하지 않는다 ----

  @Test
  void login_withAWrongPassword_returns401WithoutASessionCookie() throws Exception {
    String email = uniqueEmail();
    member(email, PASSWORD);

    mockMvc
        .perform(login(json(email, "Wrong-Password1!")))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("USERS_INVALID_CREDENTIALS"))
        .andExpect(jsonPath("$.message").value("이메일 또는 비밀번호를 확인해 주세요."))
        // 실패한 로그인이 익명 세션 쿠키를 만들지 않는다
        .andExpect(header().doesNotExist("Set-Cookie"));
  }

  @Test
  void
      login_failuresAreIdenticalWhetherTheEmailIsUnknownTheAccountIsGoogleOnlyOrThePasswordIsWrong()
          throws Exception {
    String known = uniqueEmail();
    member(known, PASSWORD);
    String googleOnly = uniqueEmail();
    userRepository.saveAndFlush(
        new User(googleOnly, null, AuthProvider.GOOGLE, null, null, null, null, null, null));

    String wrongPassword = loginBody(known, "Wrong-Password1!");
    String unknownEmail = loginBody(uniqueEmail(), PASSWORD);
    String googleAccount = loginBody(googleOnly, PASSWORD);

    assertThat(wrongPassword).contains("USERS_INVALID_CREDENTIALS");
    assertThat(unknownEmail).isEqualTo(wrongPassword);
    assertThat(googleAccount).isEqualTo(wrongPassword);
  }

  @Test
  void login_withAPasswordOver72Bytes_returns401EvenWhenThe72BytePrefixMatches() throws Exception {
    String email = uniqueEmail();
    member(email, "a".repeat(72));

    mockMvc
        .perform(login(json(email, "a".repeat(73))))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("USERS_INVALID_CREDENTIALS"));
  }

  // ---- 입력 검증 ----

  @Test
  void login_withMissingOrBlankValues_returns400() throws Exception {
    mockMvc
        .perform(login(json(null, PASSWORD)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("email"));
    mockMvc
        .perform(login(json("   ", PASSWORD)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("email"));
    mockMvc
        .perform(login(json("member@example.com", null)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("password"));
    mockMvc
        .perform(login(json("member@example.com", "")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("password"));
  }

  @Test
  void login_withOversizedInput_returns400BeforeAnyHashing() throws Exception {
    String tooLongEmail = "a".repeat(243) + "@example.com";
    mockMvc
        .perform(login(json(tooLongEmail, PASSWORD)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("email"));
    mockMvc
        .perform(login(json("member@example.com", "p".repeat(257))))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("password"));
  }

  @Test
  void login_withMalformedJson_returns400() throws Exception {
    mockMvc
        .perform(login("{\"email\": "))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void login_withANonJsonContentType_returns415() throws Exception {
    mockMvc
        .perform(
            post("/v1/users/login")
                .header("Origin", ORIGIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content("email=a"))
        .andExpect(status().isUnsupportedMediaType())
        .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"));
  }

  // ---- 허용 Origin ----

  @Test
  void login_withoutOrNotAllowedOrigin_returns403() throws Exception {
    mockMvc
        .perform(
            post("/v1/users/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("member@example.com", PASSWORD)))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    for (String origin :
        new String[] {"null", "https://evil.example.com", "http://localhost:3001"}) {
      mockMvc
          .perform(
              post("/v1/users/login")
                  .header("Origin", origin)
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(json("member@example.com", PASSWORD)))
          .andExpect(status().isForbidden())
          .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }
  }

  // ---- 반복 시도 제한 ----

  @Test
  void login_locksTheEmailAfterThreeWrongPasswordsEvenForTheRightOne() throws Exception {
    String email = uniqueEmail();
    member(email, PASSWORD);
    for (int i = 0; i < 3; i++) {
      mockMvc.perform(login(json(email, "Wrong-Password1!"))).andExpect(status().isUnauthorized());
    }

    MvcResult locked =
        mockMvc
            .perform(login(json(email, PASSWORD)))
            .andExpect(status().isTooManyRequests())
            .andExpect(jsonPath("$.code").value("USERS_LOGIN_RATE_LIMITED"))
            .andExpect(header().exists("Retry-After"))
            .andReturn();

    long retryAfter = Long.parseLong(locked.getResponse().getHeader("Retry-After"));
    assertThat(retryAfter).isBetween(1L, 30L);
    // 다른 이메일은 영향이 없다
    String other = uniqueEmail();
    member(other, PASSWORD);
    mockMvc.perform(login(json(other, PASSWORD))).andExpect(status().isOk());
  }

  @Test
  void login_locksAnUnknownEmailTheSameWay() throws Exception {
    String email = uniqueEmail();
    for (int i = 0; i < 3; i++) {
      mockMvc.perform(login(json(email, PASSWORD))).andExpect(status().isUnauthorized());
    }

    mockMvc
        .perform(login(json(email, PASSWORD)))
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_LOGIN_RATE_LIMITED"));
  }

  // ---- 로그인이 필요한 경로 ----

  @Test
  void me_withoutASession_returns401() throws Exception {
    mockMvc
        .perform(get("/v1/users/me"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }

  @Test
  void logout_withoutASession_returns403CsrfInvalid() throws Exception {
    // CSRF 필터가 인가보다 먼저 돌아서 세션 없는 변경 요청은 401 이 아니라 403 이다
    mockMvc
        .perform(post("/v1/users/logout"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"))
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON));
  }
}
