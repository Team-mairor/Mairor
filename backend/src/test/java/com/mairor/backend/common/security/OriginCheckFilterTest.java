package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.common.error.ErrorResponseWriter;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.util.matcher.RequestMatcher;
import tools.jackson.databind.json.JsonMapper;

class OriginCheckFilterTest {

  private static final String APP = "https://app.example.com";

  private final RequestMatcher signUp =
      request -> "POST".equals(request.getMethod()) && "/v1/users".equals(request.getRequestURI());

  private final OriginCheckFilter filter =
      new OriginCheckFilter(
          List.of(signUp),
          List.of(APP, "http://localhost:3000"),
          new ErrorResponseWriter(JsonMapper.builder().build()));

  private static MockHttpServletRequest post(String path, String... origins) {
    MockHttpServletRequest request = new MockHttpServletRequest("POST", path);
    request.setRequestURI(path);
    for (String origin : origins) {
      request.addHeader("Origin", origin);
    }
    return request;
  }

  /** 필터를 통과시키고 응답과 "다음 필터가 호출됐는지"를 돌려준다. */
  private Result run(MockHttpServletRequest request) throws Exception {
    MockHttpServletResponse response = new MockHttpServletResponse();
    MockFilterChain chain = new MockFilterChain();
    filter.doFilter(request, response, chain);
    return new Result(response, chain.getRequest() != null);
  }

  private record Result(MockHttpServletResponse response, boolean passed) {}

  // ---- 허용 ----

  @Test
  void allowedOrigin_passesToTheChain() throws Exception {
    Result result = run(post("/v1/users", APP));

    assertThat(result.passed()).isTrue();
    assertThat(result.response().getStatus()).isEqualTo(200);
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "https://APP.Example.com",
        "https://app.example.com/",
        "https://app.example.com:443",
        "HTTPS://app.example.com",
        "http://localhost:3000",
        "  https://app.example.com  "
      })
  void equivalentSpellingsOfAllowedOrigins_pass(String origin) throws Exception {
    assertThat(run(post("/v1/users", origin)).passed()).isTrue();
  }

  // ---- 거절 ----

  @Test
  void missingOrigin_isRejectedWithForbiddenJson() throws Exception {
    Result result = run(post("/v1/users"));

    assertThat(result.passed()).isFalse();
    assertThat(result.response().getStatus()).isEqualTo(403);
    assertThat(result.response().getContentType()).startsWith("application/json");
    assertThat(result.response().getContentAsString()).contains("\"code\":\"FORBIDDEN\"");
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "null",
        "NULL",
        "",
        "   ",
        "app.example.com",
        "not a url",
        "ftp://app.example.com",
        "https://app.example.com/path",
        "https://app.example.com?x=1",
        "https://app.example.com#top",
        "https://user@app.example.com",
        "https://",
        // 허용 목록에 없는 곳
        "https://evil.com",
        "http://app.example.com",
        "https://app.example.com:8443",
        "http://localhost:3001",
        // 접미사·접두사·부분 문자열 흉내
        "https://app.example.com.evil.com",
        "https://xapp.example.com",
        "https://evil.com/https://app.example.com",
        "https://app.example.com@evil.com"
      })
  void invalidOrDisallowedOrigin_isRejected(String origin) throws Exception {
    Result result = run(post("/v1/users", origin));

    assertThat(result.passed()).as("origin=%s", origin).isFalse();
    assertThat(result.response().getStatus()).isEqualTo(403);
  }

  @Test
  void multipleOriginHeaders_areRejectedEvenIfEachIsAllowed() throws Exception {
    assertThat(run(post("/v1/users", APP, "http://localhost:3000")).passed()).isFalse();
    assertThat(run(post("/v1/users", APP, APP)).passed()).isFalse();
  }

  @Test
  void headerInjectionInRejectedOrigin_doesNotBreakTheResponse() throws Exception {
    Result result = run(post("/v1/users", "https://evil.com\r\nX-Injected: 1"));

    assertThat(result.passed()).isFalse();
    assertThat(result.response().getStatus()).isEqualTo(403);
  }

  // ---- 보호 대상 아님 ----

  @Test
  void requestsOutsideTheProtectedList_passWithoutOrigin() throws Exception {
    assertThat(run(new MockHttpServletRequest("GET", "/v1/users")).passed()).isTrue();
    assertThat(run(post("/v1/guides")).passed()).isTrue();
    assertThat(run(post("/health")).passed()).isTrue();
  }

  @Test
  void anotherProtectedPath_canBeAddedWithoutAffectingOthers() throws Exception {
    OriginCheckFilter twoPaths =
        new OriginCheckFilter(
            List.of(signUp, request -> "/v1/users/sessions".equals(request.getRequestURI())),
            List.of(APP),
            new ErrorResponseWriter(JsonMapper.builder().build()));
    MockHttpServletResponse response = new MockHttpServletResponse();
    MockFilterChain chain = new MockFilterChain();

    twoPaths.doFilter(post("/v1/users/sessions"), response, chain);

    assertThat(response.getStatus()).isEqualTo(403);
    assertThat(chain.getRequest()).isNull();
  }

  // ---- 설정 오류는 시작 단계에서 ----

  @ParameterizedTest
  @ValueSource(
      strings = {"app.example.com", "https://", "https://app.example.com/path", "null", ""})
  void invalidConfiguredOrigin_failsAtConstruction(String configured) {
    assertThatThrownBy(
            () ->
                new OriginCheckFilter(
                    List.of(signUp),
                    List.of(configured),
                    new ErrorResponseWriter(JsonMapper.builder().build())))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("허용 Origin 형식이 올바르지 않습니다");
  }

  // ---- 정규화 ----

  @Test
  void normalize_dropsDefaultPortsAndTrailingSlashAndLowercases() {
    assertThat(OriginCheckFilter.normalize("HTTPS://App.Example.COM:443/")).isEqualTo(APP);
    assertThat(OriginCheckFilter.normalize("http://App.Example.com:80"))
        .isEqualTo("http://app.example.com");
    assertThat(OriginCheckFilter.normalize("https://app.example.com:3000"))
        .isEqualTo("https://app.example.com:3000");
    // 스킴에 맞지 않는 "기본 포트"는 기본 포트가 아니다
    assertThat(OriginCheckFilter.normalize("http://app.example.com:443"))
        .isEqualTo("http://app.example.com:443");
    assertThat(OriginCheckFilter.normalize("http://[::1]:3000")).isEqualTo("http://[::1]:3000");
  }

  @Test
  void normalize_returnsNullForNonOrigins() {
    assertThat(OriginCheckFilter.normalize(null)).isNull();
    assertThat(OriginCheckFilter.normalize("null")).isNull();
    assertThat(OriginCheckFilter.normalize("https://app.example.com/a")).isNull();
  }
}
