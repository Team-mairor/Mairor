package com.mairor.backend.testsupport;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.testsupport.SessionTestClient.Response;
import com.mairor.backend.users.SignUpRequests;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 실제 HTTP 로 가입·로그인·요청을 보내는 테스트용 흐름 도우미. 쿠키 값과 CSRF 토큰을 응답에서 꺼내 다음 요청에 직접 실어 보낸다. 회원마다 서로 다른 이메일을
 * 쓰므로 시도 제한이 테스트끼리 섞이지 않는다.
 */
public class AuthFlowClient {

  public static final String ORIGIN = "http://localhost:3000";
  public static final String PASSWORD = "ExampleOnly!2026";
  public static final String CHROME_WINDOWS =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          + "Chrome/130.0.0.0 Safari/537.36";
  public static final String SAFARI_IPHONE =
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
          + "(KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1";

  private static final Pattern USER_ID = Pattern.compile("\"userId\"\\s*:\\s*\"([^\"]+)\"");
  private static final Pattern CSRF_TOKEN = Pattern.compile("\"csrfToken\"\\s*:\\s*\"([^\"]+)\"");

  public record Account(String email, UUID userId) {}

  public record Login(Response response, String cookie, String csrfToken) {}

  private final SessionTestClient client;

  public AuthFlowClient(SessionTestClient client) {
    this.client = client;
  }

  public Account signUp() throws IOException, InterruptedException {
    String email = "flow-" + UUID.randomUUID() + "@example.com";
    String body =
        """
        {"email": "%s", "password": "%s", "passwordConfirm": "%s", "agreements": %s}"""
            .formatted(email, PASSWORD, PASSWORD, SignUpRequests.AGREEMENTS_JSON);
    Response response = client.postJson("/v1/users/signup", body, null, Map.of("Origin", ORIGIN));
    assertThat(response.status()).isEqualTo(201);
    return new Account(email, UUID.fromString(find(USER_ID, response.body())));
  }

  /** 로그인한다. {@code sessionCookie} 는 이미 가진 쿠키(없으면 {@code null}). */
  public Login login(Account account, String sessionCookie, String userAgent)
      throws IOException, InterruptedException {
    String body = "{\"email\": \"%s\", \"password\": \"%s\"}".formatted(account.email(), PASSWORD);
    Response response =
        client.postJson(
            "/v1/users/login",
            body,
            sessionCookie,
            Map.of("Origin", ORIGIN, "User-Agent", userAgent));
    assertThat(response.status()).as("로그인 응답: %s", response.body()).isEqualTo(200);
    return new Login(response, response.sessionCookieValue(), find(CSRF_TOKEN, response.body()));
  }

  public Login login(Account account, String userAgent) throws IOException, InterruptedException {
    return login(account, null, userAgent);
  }

  public Response get(String path, String cookie) throws IOException, InterruptedException {
    return client.get(path, cookie);
  }

  public Response me(String cookie) throws IOException, InterruptedException {
    return client.get("/v1/users/me", cookie);
  }

  public Response logout(String cookie, String csrfToken) throws IOException, InterruptedException {
    return post("/v1/users/logout", cookie, csrfToken);
  }

  /** 변경 요청(POST). {@code csrfToken} 이 {@code null} 이면 헤더를 보내지 않는다. */
  public Response post(String path, String cookie, String csrfToken)
      throws IOException, InterruptedException {
    return client.call(
        "POST", path, null, cookie, csrfToken == null ? null : Map.of("X-CSRF-TOKEN", csrfToken));
  }

  /** 로그인 요청만 보내고 결과를 그대로 돌려준다(상태 검증 없음). */
  public Response loginRaw(String email, String password, String userAgent)
      throws IOException, InterruptedException {
    return loginRaw(email, password, userAgent, null);
  }

  /** 이미 가진 세션 쿠키({@code null} 이면 없음)로 로그인 요청만 보내고 결과를 그대로 돌려준다. */
  public Response loginRaw(String email, String password, String userAgent, String sessionCookie)
      throws IOException, InterruptedException {
    String body = "{\"email\": \"%s\", \"password\": \"%s\"}".formatted(email, password);
    return client.postJson(
        "/v1/users/login", body, sessionCookie, Map.of("Origin", ORIGIN, "User-Agent", userAgent));
  }

  public Response delete(String path, String cookie, String csrfToken)
      throws IOException, InterruptedException {
    return client.call(
        "DELETE", path, null, cookie, csrfToken == null ? null : Map.of("X-CSRF-TOKEN", csrfToken));
  }

  /** 세션 쿠키 값(Base64)에서 실제 세션 ID 를 꺼낸다. */
  public static String sessionId(String cookie) {
    return new String(java.util.Base64.getDecoder().decode(cookie));
  }

  private static String find(Pattern pattern, String text) {
    Matcher matcher = pattern.matcher(text);
    assertThat(matcher.find()).as("응답에 %s 가 있어야 한다: %s", pattern, text).isTrue();
    return matcher.group(1);
  }
}
