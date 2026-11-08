package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.CookieSerializer.CookieValue;

/**
 * 서비스 세션 쿠키 속성 (docs/references/api-spec.md 인증·배포 상세): {@code __Host-sessionId},
 * HttpOnly·Secure·SameSite=Strict·Path=/. Spring Session이 쓰는 {@link CookieSerializer}는 Boot가 {@code
 * server.servlet.session.cookie.*} 설정으로 만든다.
 *
 * <p>내장 서버로 띄워야 한다. 기본 MOCK 환경은 Boot가 WAR 배포처럼 다뤄 {@code ServletContext}의 쿠키 설정(기본값 {@code
 * SESSION})으로 직렬화기를 만들기 때문에 위 설정이 반영되지 않는다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionCookieTest {

  @Autowired private CookieSerializer cookieSerializer;

  @Test
  void sessionCookie_isHostPrefixedStrict() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setSecure(true);
    request.setContextPath("/api");
    MockHttpServletResponse response = new MockHttpServletResponse();

    cookieSerializer.writeCookieValue(new CookieValue(request, response, "session-id"));

    String setCookie = response.getHeader(HttpHeaders.SET_COOKIE);
    assertThat(setCookie)
        .startsWith("__Host-sessionId=")
        .contains("; Path=/;")
        .contains("; Secure")
        .contains("; HttpOnly")
        .contains("; SameSite=Strict");
  }

  @Test
  void sessionCookie_maxAgeIsTheConfiguredThreeDays() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setSecure(true);
    request.setContextPath("/api");
    MockHttpServletResponse response = new MockHttpServletResponse();

    cookieSerializer.writeCookieValue(new CookieValue(request, response, "session-id"));

    assertThat(response.getHeader(HttpHeaders.SET_COOKIE)).contains("; Max-Age=259200;");
  }

  @Test
  void sessionCookie_maxAgeCanBeSetPerRequestWithoutChangingTheSharedDefault() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setSecure(true);
    request.setContextPath("/api");
    MockHttpServletResponse shortLived = new MockHttpServletResponse();
    CookieValue cookie = new CookieValue(request, shortLived, "session-id");
    cookie.setCookieMaxAge(3600);

    cookieSerializer.writeCookieValue(cookie);
    MockHttpServletResponse byDefault = new MockHttpServletResponse();
    cookieSerializer.writeCookieValue(new CookieValue(request, byDefault, "session-id"));

    assertThat(shortLived.getHeader(HttpHeaders.SET_COOKIE)).contains("; Max-Age=3600;");
    assertThat(byDefault.getHeader(HttpHeaders.SET_COOKIE)).contains("; Max-Age=259200;");
  }
}
