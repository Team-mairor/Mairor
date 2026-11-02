package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.service.GoogleLoginService;
import com.mairor.backend.users.support.GoogleAuthorizationStore;
import com.mairor.backend.users.support.VerificationHasher;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.util.MultiValueMap;
import org.springframework.web.util.UriComponents;
import org.springframework.web.util.UriComponentsBuilder;

/** Google 로그인 시작(API-USERS-006): 인가 요청 주소, 인가 요청 쿠키, 세션을 만들지 않는 것, 시도 제한. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.oauth.google.client-id=test-client",
      "app.oauth.google.client-secret=test-secret",
      "app.oauth.google.redirect-uri=http://localhost:3000/api/v1/users/oauth/google/callback",
      "app.rate-limit.google-login.limit=3",
      "app.rate-limit.google-login.window=10m"
    })
@AutoConfigureMockMvc
class GoogleLoginStartTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private GoogleAuthorizationStore store;
  @Autowired private VerificationHasher hasher;

  private static String randomIp() {
    return "198.51." + (int) (Math.random() * 250) + "." + (int) (Math.random() * 250);
  }

  private ResultActions start(String remoteAddr) throws Exception {
    return mockMvc.perform(
        get("/v1/users/oauth/google")
            .with(
                r -> {
                  r.setRemoteAddr(remoteAddr);
                  return r;
                }));
  }

  private static String authorizationCookie(MvcResult result) {
    return result.getResponse().getHeaders(HttpHeaders.SET_COOKIE).stream()
        .filter(c -> c.startsWith(GoogleLoginService.AUTHORIZATION_COOKIE + "="))
        .findFirst()
        .orElseThrow();
  }

  @Test
  void redirectsToGoogleWithStateNonceAndPkce() throws Exception {
    MvcResult result =
        start(randomIp())
            .andExpect(status().isFound())
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andReturn();

    UriComponents location =
        UriComponentsBuilder.fromUriString(result.getResponse().getHeader(HttpHeaders.LOCATION))
            .build();
    assertThat(location.getHost()).isEqualTo("accounts.google.com");
    MultiValueMap<String, String> query = location.getQueryParams();
    assertThat(query.getFirst("response_type")).isEqualTo("code");
    assertThat(query.getFirst("client_id")).isEqualTo("test-client");
    assertThat(decode(query.getFirst("redirect_uri")))
        .isEqualTo("http://localhost:3000/api/v1/users/oauth/google/callback");
    assertThat(decode(query.getFirst("scope")).split(" ")).contains("openid", "email", "profile");
    assertThat(query.getFirst("state")).isNotBlank();
    assertThat(query.getFirst("nonce")).isNotBlank();
    assertThat(query.getFirst("code_challenge")).isNotBlank();
    assertThat(query.getFirst("code_challenge_method")).isEqualTo("S256");
  }

  @Test
  void setsAShortLivedLaxAuthorizationCookieAndNoSessionCookie() throws Exception {
    MvcResult result = start(randomIp()).andExpect(status().isFound()).andReturn();

    String cookie = authorizationCookie(result);
    assertThat(cookie)
        .contains("HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=600")
        .doesNotContain("Domain");
    List<String> setCookies = result.getResponse().getHeaders(HttpHeaders.SET_COOKIE);
    assertThat(setCookies).noneMatch(c -> c.startsWith("__Host-sessionId="));
    assertThat(result.getRequest().getSession(false)).isNull();
  }

  @Test
  void cookieValueFindsTheStoredRequestWithTheSameState() throws Exception {
    MvcResult result = start(randomIp()).andExpect(status().isFound()).andReturn();

    String cookie = authorizationCookie(result);
    String value = cookie.substring(cookie.indexOf('=') + 1, cookie.indexOf(';'));
    String state =
        UriComponentsBuilder.fromUriString(result.getResponse().getHeader(HttpHeaders.LOCATION))
            .build()
            .getQueryParams()
            .getFirst("state");

    OAuth2AuthorizationRequest stored =
        store.take(hasher.hashToken(value), Instant.now()).orElseThrow();
    assertThat(stored.getState()).isEqualTo(decode(state));
    // 쿠키 값 자체로는 찾을 수 없다(해시로 보관)
    assertThat(store.take(value, Instant.now())).isEmpty();
  }

  @Test
  void tooManyStartsFromOneClient_areLimited() throws Exception {
    String ip = randomIp();
    for (int i = 0; i < 3; i++) {
      start(ip).andExpect(status().isFound());
    }

    start(ip)
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_LOGIN_RATE_LIMITED"))
        .andExpect(header().exists("Retry-After"));
    start(randomIp()).andExpect(status().isFound());
  }

  @Test
  void springDefaultOAuthPathsAreNotOpen() throws Exception {
    mockMvc.perform(get("/oauth2/authorization/google")).andExpect(status().isUnauthorized());
    mockMvc.perform(get("/login/oauth2/code/google")).andExpect(status().isUnauthorized());
  }

  private static String decode(String value) {
    return java.net.URLDecoder.decode(value, java.nio.charset.StandardCharsets.UTF_8);
  }
}
