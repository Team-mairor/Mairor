package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import com.mairor.backend.users.FakeGoogle;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserIdentityRepository;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.service.GoogleLoginService;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * Google 가입 완료. 실제 HTTP 로 시작 → 가짜 Google → callback(가입 대기) → 가입 완료를 거쳐 회원·연결·약관 기록과 로그인 세션이 생기는지,
 * 실패하면 무엇이 남는지 확인한다.
 */
@Import({TestcontainersConfiguration.class, FakeGoogle.Registrations.class})
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.rate-limit.google-login.limit=1000"
    })
class GoogleSignUpTest {

  private static final String ORIGIN = "http://localhost:3000";
  private static final String FULL_PROFILE =
      """
      {"nickname": "미러러버", "name": "홍길동", "phone": "010-1234-5678",
       "birthDate": "2000-01-01", "gender": "FEMALE", "agreements": %s}"""
          .formatted(SignUpRequests.AGREEMENTS_JSON);
  private static final String MINIMAL =
      "{\"agreements\": %s}".formatted(SignUpRequests.AGREEMENTS_JSON);

  @LocalServerPort private int port;
  @Autowired private UserRepository userRepository;
  @Autowired private UserIdentityRepository identityRepository;
  @Autowired private JdbcTemplate jdbc;

  private SessionTestClient client;
  private final List<String> emails = new ArrayList<>();

  @BeforeEach
  void setUp() {
    client = new SessionTestClient(port);
  }

  @AfterEach
  void cleanUp() {
    for (String email : emails) {
      jdbc.update(
          "delete from user_agreements where user_id in (select id from users where email = ?)",
          email);
      jdbc.update(
          "delete from user_identities where user_id in (select id from users where email = ?)",
          email);
      jdbc.update("delete from users where email = ?", email);
    }
  }

  /** Google 로 처음 온 사용자를 만든다: 시작 → 가짜 Google → callback. 가입 대기 쿠키 값을 돌려준다. */
  private String pendingSignup(String subject, String email) throws Exception {
    emails.add(email);
    Response started = client.get("/v1/users/oauth/google", null);
    String authCookie = cookieValue(started, GoogleLoginService.AUTHORIZATION_COOKIE);
    var query = UriComponentsBuilder.fromUriString(started.header("Location")).build();
    String state = decode(query.getQueryParams().getFirst("state"));
    FakeGoogle.willIssue(subject, email, decode(query.getQueryParams().getFirst("nonce")));

    Response callback = callback(authCookie, state);
    assertThat(callback.header("Location")).isEqualTo("/signup/google");
    return cookieValue(callback, GoogleLoginService.SIGNUP_COOKIE);
  }

  private Response callback(String authCookie, String state) throws Exception {
    return client.get(
        "/v1/users/oauth/google/callback?code=fake-code&state="
            + java.net.URLEncoder.encode(state, StandardCharsets.UTF_8),
        null,
        Map.of("Cookie", GoogleLoginService.AUTHORIZATION_COOKIE + "=" + authCookie));
  }

  /** 같은 Google 계정으로 다시 로그인한다. 돌아온 응답을 준다. */
  private Response loginAgain(String subject, String email) throws Exception {
    Response started = client.get("/v1/users/oauth/google", null);
    var query = UriComponentsBuilder.fromUriString(started.header("Location")).build();
    FakeGoogle.willIssue(subject, email, decode(query.getQueryParams().getFirst("nonce")));
    return callback(
        cookieValue(started, GoogleLoginService.AUTHORIZATION_COOKIE),
        decode(query.getQueryParams().getFirst("state")));
  }

  private Response complete(String signupCookie, String json) throws Exception {
    return complete(signupCookie, json, ORIGIN);
  }

  private Response complete(String signupCookie, String json, String origin) throws Exception {
    Map<String, String> headers = new HashMap<>();
    if (origin != null) {
      headers.put("Origin", origin);
    }
    if (signupCookie != null) {
      headers.put("Cookie", GoogleLoginService.SIGNUP_COOKIE + "=" + signupCookie);
    }
    return client.postJson("/v1/users/oauth/google/signup", json, null, headers);
  }

  private static String uniqueEmail() {
    return "gs-" + UUID.randomUUID() + "@gmail.com";
  }

  @Test
  void completingTheSignup_createsAGoogleMemberAndLogsIn() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    String signupCookie = pendingSignup(subject, email);

    Response response = complete(signupCookie, FULL_PROFILE);

    assertThat(response.status()).isEqualTo(201);
    assertThat(response.header("Cache-Control")).isEqualTo("no-store");
    assertThat(response.body())
        .contains("\"email\":\"" + email + "\"", "\"provider\":\"GOOGLE\"", "\"csrfToken\":\"");
    assertThat(response.sessionSetCookie()).contains("SameSite=Strict", "HttpOnly", "Secure");
    assertThat(response.setCookies())
        .anyMatch(
            c -> c.startsWith(GoogleLoginService.SIGNUP_COOKIE + "=;") && c.contains("Max-Age=0"));

    User user = userRepository.findByEmail(email).orElseThrow();
    assertThat(user.getProvider()).isEqualTo(AuthProvider.GOOGLE);
    assertThat(user.getPasswordHash()).isNull();
    assertThat(user.getEmailVerifiedAt()).isNotNull();
    assertThat(user.getNickname()).isEqualTo("미러러버");
    assertThat(user.getPhone()).isEqualTo("01012345678");
    assertThat(identityRepository.findByProviderAndProviderSubject(AuthProvider.GOOGLE, subject))
        .get()
        .extracting(i -> i.getUser().getId())
        .isEqualTo(user.getId());
    assertThat(
            jdbc.queryForObject(
                "select count(*) from user_agreements where user_id = ?",
                Integer.class,
                user.getId()))
        .isEqualTo(4);

    assertThat(client.get("/v1/users/me", response.sessionCookieValue()).status()).isEqualTo(200);
  }

  @Test
  void afterSigningUp_theSameGoogleAccountLogsInDirectly() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    complete(pendingSignup(subject, email), MINIMAL);

    Response again = loginAgain(subject, email);

    assertThat(again.header("Location")).isEqualTo("/");
    assertThat(again.sessionCookieValue()).isNotNull();
  }

  @Test
  void optionalProfileCanBeOmitted() throws Exception {
    String email = uniqueEmail();

    Response response = complete(pendingSignup("sub-" + UUID.randomUUID(), email), MINIMAL);

    assertThat(response.status()).isEqualTo(201);
    User user = userRepository.findByEmail(email).orElseThrow();
    assertThat(user.getNickname()).isNull();
    assertThat(user.getName()).isNull();
  }

  @Test
  void invalidInput_keepsThePendingSignupSoItCanBeFixed() throws Exception {
    String signupCookie = pendingSignup("sub-" + UUID.randomUUID(), uniqueEmail());

    Response invalid =
        complete(
            signupCookie,
            "{\"nickname\": \"a\", \"agreements\": %s}".formatted(SignUpRequests.AGREEMENTS_JSON));
    assertThat(invalid.status()).isEqualTo(400);
    assertThat(invalid.body()).contains("VALIDATION_FAILED", "\"field\":\"nickname\"");

    Response tooYoung =
        complete(
            signupCookie,
            "{\"birthDate\": \"2020-01-01\", \"agreements\": %s}"
                .formatted(SignUpRequests.AGREEMENTS_JSON));
    assertThat(tooYoung.status()).isEqualTo(400);
    assertThat(tooYoung.body()).contains("\"field\":\"birthDate\"");

    Response noTerms =
        complete(
            signupCookie,
            """
            {"agreements": [{"type": "PRIVACY", "version": "2026-10-26", "agreed": true},
                            {"type": "AGE_OVER_14", "version": "2026-10-26", "agreed": true}]}""");
    assertThat(noTerms.status()).isEqualTo(400);
    assertThat(noTerms.body()).contains("USERS_REQUIRED_AGREEMENT_MISSING");

    assertThat(complete(signupCookie, MINIMAL).status()).isEqualTo(201);
  }

  @Test
  void thePendingSignupCanBeUsedOnlyOnce() throws Exception {
    String signupCookie = pendingSignup("sub-" + UUID.randomUUID(), uniqueEmail());
    assertThat(complete(signupCookie, MINIMAL).status()).isEqualTo(201);

    Response second = complete(signupCookie, MINIMAL);

    assertThat(second.status()).isEqualTo(410);
    assertThat(second.body()).contains("USERS_GOOGLE_SIGNUP_EXPIRED");
  }

  @Test
  void withoutOrWithAnUnknownSignupCookie_isGone() throws Exception {
    for (String cookie : new String[] {null, "unknown"}) {
      Response response = complete(cookie, MINIMAL);
      assertThat(response.status()).isEqualTo(410);
      assertThat(response.body()).contains("USERS_GOOGLE_SIGNUP_EXPIRED");
      assertThat(response.sessionCookieValue()).isNull();
    }
  }

  @Test
  void sameEmailRegisteredMeanwhile_isNotLinked() throws Exception {
    String email = uniqueEmail();
    String signupCookie = pendingSignup("sub-" + UUID.randomUUID(), email);
    userRepository.saveAndFlush(new User(email, "{bcrypt}hash"));

    Response response = complete(signupCookie, MINIMAL);

    assertThat(response.status()).isEqualTo(409);
    assertThat(response.body()).contains("USERS_ACCOUNT_LINK_REQUIRED");
    assertThat(response.sessionCookieValue()).isNull();
    assertThat(userRepository.findByEmail(email).orElseThrow().getProvider())
        .isEqualTo(AuthProvider.LOCAL);
  }

  @Test
  void requestFromAnotherOrigin_isForbidden() throws Exception {
    String signupCookie = pendingSignup("sub-" + UUID.randomUUID(), uniqueEmail());

    assertThat(complete(signupCookie, MINIMAL, "https://evil.example").status()).isEqualTo(403);
    assertThat(complete(signupCookie, MINIMAL, null).status()).isEqualTo(403);
    // 막힌 요청은 가입 대기를 쓰지 않는다
    assertThat(complete(signupCookie, MINIMAL).status()).isEqualTo(201);
  }

  @Test
  void googleOnlyMember_cannotLogInWithAPassword() throws Exception {
    String email = uniqueEmail();
    complete(pendingSignup("sub-" + UUID.randomUUID(), email), MINIMAL);

    Response login =
        client.postJson(
            "/v1/users/login",
            "{\"email\": \"%s\", \"password\": \"ExampleOnly!2026\"}".formatted(email),
            null,
            Map.of("Origin", ORIGIN));

    assertThat(login.status()).isEqualTo(401);
    assertThat(login.body()).contains("USERS_INVALID_CREDENTIALS");
  }

  private static String cookieValue(Response response, String name) {
    String prefix = name + "=";
    String setCookie =
        response.setCookies().stream().filter(c -> c.startsWith(prefix)).findFirst().orElseThrow();
    return setCookie.substring(prefix.length(), setCookie.indexOf(';'));
  }

  private static String decode(String value) {
    return URLDecoder.decode(value, StandardCharsets.UTF_8);
  }
}
