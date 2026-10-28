package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.service.UserSignUpService;
import java.util.UUID;
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
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;

/**
 * 가입 가능 이메일 확인 API 계약 (API-USERS-011). 가입과 마찬가지로 인증·CSRF 토큰 없이 허용 Origin 헤더만 보낸다. 요청 제한은 테스트마다 다른
 * 클라이언트 IP 를 써서 서로 영향을 주지 않게 하고, 한도는 3회로 낮춰 확인한다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.rate-limit.email-availability.limit=3",
      "app.rate-limit.email-availability.window=1m"
    })
@AutoConfigureMockMvc
@Transactional
@ExtendWith(OutputCaptureExtension.class)
class EmailAvailabilityControllerTest {

  private static final String ORIGIN = "http://localhost:3000";
  private static final String URL = "/v1/users/email-availability";

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private UserSignUpService signUpService;

  /** 이 테스트만 쓰는 클라이언트 IP. */
  private final String ip =
      "10." + (int) (Math.random() * 250) + ".0." + (int) (Math.random() * 250);

  private MockHttpServletRequestBuilder check(String json) {
    return post(URL)
        .header("Origin", ORIGIN)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json)
        .with(
            request -> {
              request.setRemoteAddr(ip);
              return request;
            });
  }

  private static String body(String email) {
    return "{\"email\": " + (email == null ? "null" : "\"" + email + "\"") + "}";
  }

  private void register(String email) {
    signUpService.signUp(SignUpRequests.basic(email, "ExampleOnly!2026", "ExampleOnly!2026"));
  }

  // ---- 결과 ----

  @Test
  void unregisteredEmail_isAvailable() throws Exception {
    mockMvc
        .perform(check(body("new@example.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.email").value("new@example.com"))
        .andExpect(jsonPath("$.available").value(true));
  }

  @Test
  void registeredEmail_isNotAvailable() throws Exception {
    register("taken@example.com");

    mockMvc
        .perform(check(body("taken@example.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.email").value("taken@example.com"))
        .andExpect(jsonPath("$.available").value(false));
  }

  @Test
  void emailIsNormalizedLikeSignUp() throws Exception {
    register("taken@example.com");

    mockMvc
        .perform(check(body("  TAKEN@Example.COM ")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.email").value("taken@example.com"))
        .andExpect(jsonPath("$.available").value(false));
  }

  @Test
  void checkingDoesNotCreateAnything() throws Exception {
    long before = userRepository.count();

    mockMvc.perform(check(body("new@example.com"))).andExpect(status().isOk());

    assertThat(userRepository.count()).isEqualTo(before);
    assertThat(userRepository.existsByEmail("new@example.com")).isFalse();
  }

  // ---- 400 ----

  @Test
  void invalidFormat_returns400WithEmailField() throws Exception {
    for (String invalid : new String[] {"plain", "a@b", "@example.com", "member@", "a b@c.com"}) {
      mockMvc
          .perform(check(body(invalid)))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
          .andExpect(jsonPath("$.details[0].field").value("email"));
    }
  }

  @Test
  void blankOrMissingEmail_returns400() throws Exception {
    for (String json : new String[] {body(""), body("   "), body(null), "{}"}) {
      mockMvc
          .perform(check(json))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
          .andExpect(jsonPath("$.details[0].field").value("email"));
    }
  }

  @Test
  void emailLengthLimitAppliesAfterTrimming() throws Exception {
    // 로컬 파트(@ 앞)는 64자까지만 허용되므로 도메인을 길게 만들어 전체를 254자에 맞춘다
    String domain =
        "@"
            + "b".repeat(60)
            + "."
            + "c".repeat(60)
            + "."
            + "d".repeat(60)
            + "."
            + "e".repeat(60)
            + ".com";
    String atLimit = "a".repeat(254 - domain.length()) + domain;
    assertThat(atLimit).hasSize(254);

    mockMvc.perform(check(body("  " + atLimit + "  "))).andExpect(status().isOk());
    mockMvc
        .perform(check(body("a" + atLimit)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("email"));
  }

  @Test
  void malformedJsonOrNoBody_returns400() throws Exception {
    mockMvc.perform(check("{not json")).andExpect(status().isBadRequest());
    mockMvc
        .perform(
            post(URL)
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .with(
                    request -> {
                      request.setRemoteAddr(ip);
                      return request;
                    }))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void nonJsonContentType_returns415() throws Exception {
    mockMvc
        .perform(
            post(URL)
                .header("Origin", ORIGIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content("a@example.com"))
        .andExpect(status().isUnsupportedMediaType())
        .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"));
  }

  // ---- 허용 Origin ----

  @Test
  void withoutOrigin_returns403() throws Exception {
    mockMvc
        .perform(post(URL).contentType(MediaType.APPLICATION_JSON).content(body("new@example.com")))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("FORBIDDEN"));
  }

  @Test
  void withDisallowedOrigin_returns403() throws Exception {
    for (String origin : new String[] {"https://evil.com", "null", "http://localhost:3001"}) {
      mockMvc
          .perform(
              post(URL)
                  .header("Origin", origin)
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(body("new@example.com")))
          .andExpect(status().isForbidden())
          .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }
  }

  @Test
  void rejectedOriginDoesNotUseUpTheRateLimit() throws Exception {
    for (int i = 0; i < 5; i++) {
      mockMvc
          .perform(
              post(URL)
                  .header("Origin", "https://evil.com")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(body("new@example.com"))
                  .with(
                      request -> {
                        request.setRemoteAddr(ip);
                        return request;
                      }))
          .andExpect(status().isForbidden());
    }

    mockMvc.perform(check(body("new@example.com"))).andExpect(status().isOk());
  }

  // ---- 열어 준 범위는 이 경로의 POST 하나뿐 ----

  @Test
  void otherMethodsAndSubPaths_stillRequireLoginOrCsrf() throws Exception {
    mockMvc.perform(get(URL)).andExpect(status().isUnauthorized());
    mockMvc
        .perform(
            put(URL).header("Origin", ORIGIN).contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
    mockMvc
        .perform(
            post(URL + "/anything")
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
  }

  // ---- 요청 제한 ----

  @Test
  void overTheLimit_returns429WithRetryAfter() throws Exception {
    for (int i = 0; i < 3; i++) {
      mockMvc.perform(check(body("new@example.com"))).andExpect(status().isOk());
    }

    mockMvc
        .perform(check(body("new@example.com")))
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_CHECK_RATE_LIMITED"))
        .andExpect(jsonPath("$.available").doesNotExist())
        .andExpect(
            org.springframework.test.web.servlet.result.MockMvcResultMatchers.header()
                .string(
                    "Retry-After", org.hamcrest.Matchers.matchesPattern("([1-9]|[1-5][0-9]|60)")));
  }

  @Test
  void rateLimitIsPerClient() throws Exception {
    for (int i = 0; i < 4; i++) {
      mockMvc.perform(check(body("new@example.com")));
    }

    mockMvc
        .perform(
            post(URL)
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body("new@example.com"))
                .with(
                    request -> {
                      request.setRemoteAddr("192.0.2." + (int) (Math.random() * 250));
                      return request;
                    }))
        .andExpect(status().isOk());
  }

  @Test
  void invalidRequestsDoNotUseUpTheLimit() throws Exception {
    for (int i = 0; i < 6; i++) {
      mockMvc.perform(check(body("not-an-email"))).andExpect(status().isBadRequest());
    }

    for (int i = 0; i < 3; i++) {
      mockMvc.perform(check(body("new@example.com"))).andExpect(status().isOk());
    }
  }

  @Test
  void spoofedForwardedHeaderDoesNotEscapeTheLimit() throws Exception {
    for (int i = 0; i < 3; i++) {
      mockMvc.perform(check(body("new@example.com"))).andExpect(status().isOk());
    }

    // 요청마다 다른 X-Forwarded-For 를 보내도 접속한 주소 기준으로 센다
    mockMvc
        .perform(
            check(body("new@example.com"))
                .header("X-Forwarded-For", "203.0.113." + UUID.randomUUID().hashCode() % 200))
        .andExpect(status().isTooManyRequests());
  }

  // ---- 로그 ----

  @Test
  void emailIsNotLogged(CapturedOutput output) throws Exception {
    String email = "secret-" + UUID.randomUUID() + "@example.com";

    mockMvc.perform(check(body(email))).andExpect(status().isOk());

    assertThat(output.getAll()).doesNotContain(email);
  }
}
