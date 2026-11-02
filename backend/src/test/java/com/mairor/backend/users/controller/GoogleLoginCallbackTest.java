package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import com.mairor.backend.users.FakeGoogle;
import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.entity.UserIdentity;
import com.mairor.backend.users.repository.UserIdentityRepository;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.service.GoogleLoginService;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Date;
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
 * Google 로그인 callback(API-USERS-007). 실제 HTTP 로 시작 → 가짜 Google → callback 을 거쳐, 세션 쿠키 발급과 상대 경로
 * {@code Location} 이 그대로 나가는지까지 확인한다.
 */
@Import({TestcontainersConfiguration.class, FakeGoogle.Registrations.class})
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.rate-limit.google-login.limit=1000"
    })
class GoogleLoginCallbackTest {

  @LocalServerPort private int port;
  @Autowired private UserRepository userRepository;
  @Autowired private UserIdentityRepository identityRepository;
  @Autowired private JdbcTemplate jdbc;

  private SessionTestClient client;
  private final List<UUID> createdUsers = new ArrayList<>();

  /** 로그인 시작 결과: 인가 요청 쿠키 값과 Google 로 보낸 state·nonce. */
  private record Started(String cookie, String state, String nonce) {}

  @BeforeEach
  void setUp() {
    client = new SessionTestClient(port);
  }

  @AfterEach
  void cleanUp() {
    for (UUID id : createdUsers) {
      jdbc.update("delete from user_identities where user_id = ?", id);
      jdbc.update("delete from users where id = ?", id);
    }
  }

  private Started start() throws Exception {
    Response response = client.get("/v1/users/oauth/google", null);
    assertThat(response.status()).isEqualTo(302);
    String prefix = GoogleLoginService.AUTHORIZATION_COOKIE + "=";
    String setCookie =
        response.setCookies().stream().filter(c -> c.startsWith(prefix)).findFirst().orElseThrow();
    String cookie = setCookie.substring(prefix.length(), setCookie.indexOf(';'));
    var query = UriComponentsBuilder.fromUriString(response.header("Location")).build();
    return new Started(
        cookie,
        decode(query.getQueryParams().getFirst("state")),
        decode(query.getQueryParams().getFirst("nonce")));
  }

  private Response callback(String cookie, Map<String, String> params) throws Exception {
    StringBuilder query = new StringBuilder();
    params.forEach(
        (k, v) ->
            query
                .append(query.isEmpty() ? "?" : "&")
                .append(k)
                .append('=')
                .append(URLEncoder.encode(v, StandardCharsets.UTF_8)));
    Map<String, String> headers =
        cookie == null
            ? Map.of()
            : Map.of("Cookie", GoogleLoginService.AUTHORIZATION_COOKIE + "=" + cookie);
    return client.get("/v1/users/oauth/google/callback" + query, null, headers);
  }

  private Response callbackWithCode(Started started) throws Exception {
    return callback(started.cookie(), Map.of("state", started.state(), "code", "fake-code"));
  }

  private User googleMember(String subject, String email) {
    User user =
        userRepository.saveAndFlush(
            new User(email, null, AuthProvider.GOOGLE, null, null, null, null, null, null));
    createdUsers.add(user.getId());
    identityRepository.saveAndFlush(new UserIdentity(user, AuthProvider.GOOGLE, subject));
    return user;
  }

  private User localMember(String email) {
    User user = userRepository.saveAndFlush(new User(email, "{bcrypt}hash"));
    createdUsers.add(user.getId());
    return user;
  }

  private static String uniqueEmail() {
    return "g-" + UUID.randomUUID() + "@gmail.com";
  }

  private static void assertFailedWith(Response response, String code) {
    assertThat(response.status()).isEqualTo(302);
    assertThat(response.header("Location")).isEqualTo("/login?error=" + code);
    assertThat(response.sessionCookieValue()).isNull();
    assertThat(response.header("Cache-Control")).isEqualTo("no-store");
  }

  @Test
  void linkedGoogleMember_getsASessionAndGoesToMain() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    User member = googleMember(subject, email);
    Started started = start();
    FakeGoogle.willIssue(subject, email, started.nonce());

    Response response = callbackWithCode(started);

    assertThat(response.status()).isEqualTo(302);
    assertThat(response.header("Location")).isEqualTo("/");
    assertThat(response.header("Cache-Control")).isEqualTo("no-store");
    assertThat(response.sessionSetCookie()).contains("SameSite=Strict", "HttpOnly", "Secure");
    // 인가 요청 쿠키는 지운다
    assertThat(response.setCookies())
        .anyMatch(
            c ->
                c.startsWith(GoogleLoginService.AUTHORIZATION_COOKIE + "=;")
                    && c.contains("Max-Age=0"));

    Response me = client.get("/v1/users/me", response.sessionCookieValue());
    assertThat(me.status()).isEqualTo(200);
    assertThat(me.body()).contains(member.getId().toString(), "\"provider\":\"GOOGLE\"");
  }

  @Test
  void theAuthorizationCannotBeUsedTwice() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    googleMember(subject, email);
    Started started = start();
    FakeGoogle.willIssue(subject, email, started.nonce());
    assertThat(callbackWithCode(started).header("Location")).isEqualTo("/");

    FakeGoogle.willIssue(subject, email, started.nonce());
    assertFailedWith(callbackWithCode(started), "USERS_OAUTH_STATE_INVALID");
  }

  @Test
  void sameEmailAsALocalAccount_isNotLinkedAutomatically() throws Exception {
    String email = uniqueEmail();
    localMember(email);
    String subject = "sub-" + UUID.randomUUID();
    Started started = start();
    // Google 이 대문자로 보내도 정규화해서 비교한다
    FakeGoogle.willIssue(subject, email.toUpperCase(), started.nonce());

    assertFailedWith(callbackWithCode(started), "USERS_ACCOUNT_LINK_REQUIRED");
    assertThat(identityRepository.findByProviderAndProviderSubject(AuthProvider.GOOGLE, subject))
        .isEmpty();
  }

  @Test
  void sameEmailAsAnotherGoogleSubject_isNotLinked() throws Exception {
    String email = uniqueEmail();
    googleMember("sub-" + UUID.randomUUID(), email);
    Started started = start();
    FakeGoogle.willIssue("sub-" + UUID.randomUUID(), email, started.nonce());

    assertFailedWith(callbackWithCode(started), "USERS_ACCOUNT_LINK_REQUIRED");
  }

  @Test
  void firstTimeUser_getsAPendingSignupButNoMemberOrSession() throws Exception {
    String email = uniqueEmail();
    Started started = start();
    FakeGoogle.willIssue(
        "sub-" + UUID.randomUUID(),
        email.toUpperCase(),
        started.nonce(),
        c -> c.claim("name", "홍길동"));

    Response response = callbackWithCode(started);

    assertThat(response.status()).isEqualTo(302);
    assertThat(response.header("Location")).isEqualTo("/signup/google");
    assertThat(response.sessionCookieValue()).isNull();
    assertThat(signupSetCookie(response))
        .contains("HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=600");
    assertThat(userRepository.existsByEmail(email)).isFalse();

    // 조회는 가입 대기를 지우지 않는다
    for (int i = 0; i < 2; i++) {
      Response pending = pendingSignup(signupCookie(response));
      assertThat(pending.status()).isEqualTo(200);
      assertThat(pending.header("Cache-Control")).isEqualTo("no-store");
      assertThat(pending.body())
          .contains("\"email\":\"" + email + "\"", "\"name\":\"홍길동\"", "\"expiresAt\":")
          .doesNotContain("sub-");
    }
  }

  @Test
  void firstTimeUserWithoutAName_hasANullName() throws Exception {
    Started started = start();
    FakeGoogle.willIssue(
        "sub-" + UUID.randomUUID(), uniqueEmail(), started.nonce(), c -> c.claim("name", null));

    Response pending = pendingSignup(signupCookie(callbackWithCode(started)));

    assertThat(pending.status()).isEqualTo(200);
    assertThat(pending.body()).contains("\"name\":null");
  }

  @Test
  void pendingSignupWithoutOrWithAnUnknownCookie_isGone() throws Exception {
    for (Response response : List.of(pendingSignup(null), pendingSignup("unknown"))) {
      assertThat(response.status()).isEqualTo(410);
      assertThat(response.body()).contains("USERS_GOOGLE_SIGNUP_EXPIRED");
    }
  }

  private Response pendingSignup(String signupCookie) throws Exception {
    Map<String, String> headers =
        signupCookie == null
            ? Map.of()
            : Map.of("Cookie", GoogleLoginService.SIGNUP_COOKIE + "=" + signupCookie);
    return client.get("/v1/users/oauth/google/signup", null, headers);
  }

  private static String signupSetCookie(Response response) {
    return response.setCookies().stream()
        .filter(c -> c.startsWith(GoogleLoginService.SIGNUP_COOKIE + "="))
        .findFirst()
        .orElseThrow();
  }

  private static String signupCookie(Response response) {
    String setCookie = signupSetCookie(response);
    return setCookie.substring(
        GoogleLoginService.SIGNUP_COOKIE.length() + 1, setCookie.indexOf(';'));
  }

  @Test
  void userCancelledAtGoogle() throws Exception {
    Started started = start();

    assertFailedWith(
        callback(started.cookie(), Map.of("state", started.state(), "error", "access_denied")),
        "USERS_GOOGLE_AUTH_CANCELLED");
  }

  @Test
  void otherGoogleError_isAFailureAndItsTextIsNotPassedOn() throws Exception {
    Started started = start();

    Response response =
        callback(
            started.cookie(),
            Map.of(
                "state", started.state(),
                "error", "server_error",
                "error_description", "secret detail"));

    assertFailedWith(response, "USERS_GOOGLE_AUTH_FAILED");
    assertThat(response.header("Location")).doesNotContain("secret", "server_error");
  }

  @Test
  void codeTogetherWithError_isRejected() throws Exception {
    Started started = start();

    assertFailedWith(
        callback(
            started.cookie(),
            Map.of("state", started.state(), "code", "x", "error", "access_denied")),
        "USERS_GOOGLE_AUTH_FAILED");
  }

  @Test
  void missingCookie_orWrongState_isStateInvalid() throws Exception {
    Started started = start();
    assertFailedWith(
        callback(null, Map.of("state", started.state(), "code", "x")), "USERS_OAUTH_STATE_INVALID");

    Started another = start();
    assertFailedWith(
        callback(another.cookie(), Map.of("state", "forged", "code", "x")),
        "USERS_OAUTH_STATE_INVALID");
    // state 가 틀린 시도에도 인가 요청은 소비된다
    assertFailedWith(
        callback(another.cookie(), Map.of("state", another.state(), "code", "x")),
        "USERS_OAUTH_STATE_INVALID");
  }

  @Test
  void idTokenSignedWithAnUnknownKey_fails() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    googleMember(subject, email);
    Started started = start();
    FakeGoogle.willSignWithOtherKey(subject, email, started.nonce());

    assertFailedWith(callbackWithCode(started), "USERS_GOOGLE_AUTH_FAILED");
  }

  @Test
  void idTokenWithWrongNonce_fails() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    googleMember(subject, email);
    Started started = start();
    FakeGoogle.willIssue(subject, email, "other-nonce");

    assertFailedWith(callbackWithCode(started), "USERS_GOOGLE_AUTH_FAILED");
  }

  @Test
  void idTokenForAnotherClient_fails() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    googleMember(subject, email);
    Started started = start();
    FakeGoogle.willIssue(subject, email, started.nonce(), c -> c.audience("other-client"));

    assertFailedWith(callbackWithCode(started), "USERS_GOOGLE_AUTH_FAILED");
  }

  @Test
  void expiredIdToken_fails() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    googleMember(subject, email);
    Started started = start();
    FakeGoogle.willIssue(
        subject,
        email,
        started.nonce(),
        c ->
            c.issueTime(new Date(System.currentTimeMillis() - 7_200_000))
                .expirationTime(new Date(System.currentTimeMillis() - 3_600_000)));

    assertFailedWith(callbackWithCode(started), "USERS_GOOGLE_AUTH_FAILED");
  }

  @Test
  void unverifiedEmail_fails() throws Exception {
    String subject = "sub-" + UUID.randomUUID();
    String email = uniqueEmail();
    googleMember(subject, email);
    Started started = start();
    FakeGoogle.willIssue(subject, email, started.nonce(), c -> c.claim("email_verified", false));

    assertFailedWith(callbackWithCode(started), "USERS_GOOGLE_AUTH_FAILED");
  }

  @Test
  void codeRejectedByGoogle_fails() throws Exception {
    Started started = start();
    // 가짜 Google 에 준비된 응답이 없으면 400 invalid_grant 를 준다

    assertFailedWith(callbackWithCode(started), "USERS_GOOGLE_AUTH_FAILED");
  }

  @Test
  void googleServerError_isUnavailable() throws Exception {
    Started started = start();
    FakeGoogle.willRespond(new FakeGoogle.TokenResponse(503, null, false));

    assertFailedWith(callbackWithCode(started), "USERS_GOOGLE_AUTH_UNAVAILABLE");
  }

  private static String decode(String value) {
    return URLDecoder.decode(value, StandardCharsets.UTF_8);
  }
}
