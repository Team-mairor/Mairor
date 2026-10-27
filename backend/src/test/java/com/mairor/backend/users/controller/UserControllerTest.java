package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import jakarta.servlet.http.Cookie;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회원가입 API 계약 (API-USERS-001). 실제 호출 조건 그대로 인증·CSRF 토큰 없이 허용 Origin 헤더만 보낸다. {@code @WithMockUser}나
 * {@code csrf()}를 붙이지 않는 것이 이 테스트의 핵심이다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "app.security.allowed-origins=http://localhost:3000")
@AutoConfigureMockMvc
@Transactional
@ExtendWith(OutputCaptureExtension.class)
class UserControllerTest {

  private static final String ORIGIN = "http://localhost:3000";
  private static final String PASSWORD = "ExampleOnly!2026";

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private PasswordEncoder passwordEncoder;

  private static String body(String email, String password, String confirm) {
    return """
        {"email": %s, "password": %s, "passwordConfirm": %s}"""
        .formatted(quote(email), quote(password), quote(confirm));
  }

  private static String quote(String value) {
    return value == null ? "null" : "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
  }

  private static MockHttpServletRequestBuilder signUp(String json) {
    return post("/v1/users")
        .header("Origin", ORIGIN)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }

  // ---- 성공 ----

  @Test
  void signUp_returns201WithUserAndNoSecrets() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(
            jsonPath("$.userId").value(org.hamcrest.Matchers.matchesPattern("[0-9a-f-]{36}")))
        .andExpect(jsonPath("$.email").value("member@example.com"))
        .andExpect(jsonPath("$.createdAt").exists())
        .andExpect(jsonPath("$.password").doesNotExist())
        .andExpect(jsonPath("$.passwordConfirm").doesNotExist())
        .andExpect(jsonPath("$.passwordHash").doesNotExist())
        .andExpect(
            content()
                .string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("bcrypt"))));
  }

  @Test
  void signUp_storesNormalizedEmailAndHashedPassword() throws Exception {
    mockMvc
        .perform(signUp(body("  Member@Example.COM ", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.email").value("member@example.com"));

    User saved =
        userRepository.findAll().stream()
            .filter(u -> u.getEmail().equals("member@example.com"))
            .findFirst()
            .orElseThrow();
    assertThat(saved.getPasswordHash()).startsWith("{bcrypt}$2").doesNotContain(PASSWORD);
    assertThat(passwordEncoder.matches(PASSWORD, saved.getPasswordHash())).isTrue();
  }

  @Test
  void signUp_doesNotLogTheUserIn() throws Exception {
    MvcResult result =
        mockMvc
            .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
            .andExpect(status().isCreated())
            .andReturn();

    // 세션 쿠키를 주지 않고, 쿠키가 있더라도 그대로 실어 보낸 보호된 API는 여전히 401이다
    Cookie[] cookies = result.getResponse().getCookies();
    assertThat(cookies).extracting(Cookie::getName).doesNotContain("__Host-sessionId");
    MockHttpServletRequestBuilder next = get("/v1/any");
    if (cookies.length > 0) {
      next = next.cookie(cookies);
    }
    mockMvc.perform(next).andExpect(status().isUnauthorized());
    assertThat(result.getResponse().getHeader("Authorization")).isNull();
    assertThat(result.getResponse().getHeader("X-CSRF-Token")).isNull();
  }

  @Test
  void signUp_returnsCreatedAtAsUtcIso8601() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated())
        .andExpect(
            jsonPath("$.createdAt")
                .value(
                    org.hamcrest.Matchers.matchesPattern(
                        "\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?Z")));
  }

  @ParameterizedTest
  @ValueSource(ints = {8, 64})
  void signUp_acceptsPasswordLengthBounds(int length) throws Exception {
    String password = "a1!" + "x".repeat(length - 3);

    mockMvc
        .perform(signUp(body("len" + length + "@example.com", password, password)))
        .andExpect(status().isCreated());
  }

  @ParameterizedTest
  @ValueSource(ints = {7, 65})
  void signUp_rejectsPasswordLengthOutOfBounds(int length) throws Exception {
    String password = "a1!" + "x".repeat(length - 3);

    mockMvc
        .perform(signUp(body("len" + length + "@example.com", password, password)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("password"));
    assertThat(userRepository.existsByEmail("len" + length + "@example.com")).isFalse();
  }

  @Test
  void signUp_neverWritesThePasswordOrItsHashToTheLog(CapturedOutput output) throws Exception {
    String secret = "LogProbe-Secret-2026!";

    mockMvc
        .perform(signUp(body("logprobe@example.com", secret, secret)))
        .andExpect(status().isCreated());
    mockMvc
        .perform(signUp(body("logprobe@example.com", secret, secret)))
        .andExpect(status().isConflict());
    mockMvc
        .perform(signUp(body("bad-email", secret, secret + "x")))
        .andExpect(status().isBadRequest());
    String hash =
        userRepository.findAll().stream()
            .filter(u -> u.getEmail().equals("logprobe@example.com"))
            .findFirst()
            .orElseThrow()
            .getPasswordHash();

    assertThat(output.getAll())
        .doesNotContain(secret)
        .doesNotContain(hash)
        .doesNotContain("{bcrypt}");
  }

  // ---- 400 ----

  @Test
  void signUp_withInvalidFields_returns400WithFieldDetails() throws Exception {
    mockMvc
        .perform(signUp(body("not-an-email", "short", "short")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(
            jsonPath("$.details[*].field")
                .value(org.hamcrest.Matchers.hasItems("email", "password")));
  }

  @Test
  void signUp_withMissingFields_returns400() throws Exception {
    mockMvc
        .perform(signUp("{}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(
            jsonPath("$.details[*].field")
                .value(org.hamcrest.Matchers.hasItems("email", "password", "passwordConfirm")));
  }

  @Test
  void signUp_withPasswordMissingRule_reportsWhichRule() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", "abcdefgh!", "abcdefgh!")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("password"))
        .andExpect(jsonPath("$.details[0].reason").value("숫자를 1개 이상 포함해야 합니다."));
  }

  @Test
  void signUp_withMismatchedConfirm_returns400OnConfirmField() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD + "x")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("passwordConfirm"));
  }

  @Test
  void signUp_withMalformedJson_returns400() throws Exception {
    mockMvc
        .perform(signUp("{not json"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void signUp_withoutBody_returns400() throws Exception {
    mockMvc
        .perform(post("/v1/users").header("Origin", ORIGIN).contentType(MediaType.APPLICATION_JSON))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void signUp_passwordIsNeverEchoedInErrors() throws Exception {
    mockMvc
        .perform(signUp(body("not-an-email", "secret-password-123", "secret-password-123")))
        .andExpect(status().isBadRequest())
        .andExpect(
            content()
                .string(
                    org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("secret-password"))));
  }

  // ---- 409 ----

  @Test
  void signUp_withExistingEmail_returns409() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated());

    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_DUPLICATE"));
  }

  @Test
  void signUp_withEmailDifferingOnlyByCaseAndSpaces_returns409() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated());

    mockMvc
        .perform(signUp(body("  MEMBER@Example.com ", PASSWORD, PASSWORD)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_DUPLICATE"));
  }

  // ---- 415 ----

  @Test
  void signUp_withNonJsonContentType_returns415() throws Exception {
    mockMvc
        .perform(
            post("/v1/users")
                .header("Origin", ORIGIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content("x"))
        .andExpect(status().isUnsupportedMediaType())
        .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"));
  }

  // ---- 허용 Origin ----

  @Test
  void signUp_withoutOrigin_returns403() throws Exception {
    mockMvc
        .perform(
            post("/v1/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  @Test
  void signUp_withDisallowedOrigins_returns403() throws Exception {
    for (String origin :
        new String[] {
          "https://evil.com",
          "null",
          "http://localhost:3001",
          "https://localhost:3000",
          "http://localhost:3000.evil.com"
        }) {
      mockMvc
          .perform(
              post("/v1/users")
                  .header("Origin", origin)
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(body("member@example.com", PASSWORD, PASSWORD)))
          .andExpect(status().isForbidden())
          .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  // ---- 열어 준 범위는 가입 경로 하나뿐 ----

  @Test
  void otherEndpoints_stillRequireLogin() throws Exception {
    mockMvc.perform(get("/v1/any")).andExpect(status().isUnauthorized());
    mockMvc.perform(get("/v1/users")).andExpect(status().isUnauthorized());
    mockMvc.perform(get("/v1/users/" + UUID.randomUUID())).andExpect(status().isUnauthorized());
  }

  @Test
  void csrfExemption_isLimitedToPostOnTheSignUpPath() throws Exception {
    // 같은 경로의 다른 메서드, 하위 경로의 POST 는 여전히 CSRF 토큰이 필요하다 (토큰 없음 → 403)
    mockMvc
        .perform(
            put("/v1/users")
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isForbidden());
    mockMvc
        .perform(
            post("/v1/users/anything")
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isForbidden());
  }
}
