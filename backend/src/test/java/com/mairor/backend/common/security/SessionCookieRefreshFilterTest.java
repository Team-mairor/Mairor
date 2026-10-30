package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import jakarta.servlet.http.HttpServletResponse;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.session.web.http.CookieSerializer;

/** 쿠키 갱신이 실패해도 업무 응답은 그대로 나가고, 실패 횟수는 지표로 남는다. */
class SessionCookieRefreshFilterTest {

  private static final Instant NOW = Instant.parse("2026-10-29T03:00:00Z");

  private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
  private final CookieSerializer cookies = mock(CookieSerializer.class);
  private final SessionCookieRefreshFilter filter =
      new SessionCookieRefreshFilter(
          new SessionLifetimePolicy(Duration.ofDays(3), Duration.ofDays(3), Duration.ofDays(30)),
          Clock.fixed(NOW, ZoneOffset.UTC),
          cookies,
          new SessionMetrics(registry));

  @AfterEach
  void tearDown() {
    SecurityContextHolder.clearContext();
  }

  private MockHttpServletRequest authenticatedRequest() {
    SecurityContextHolder.getContext()
        .setAuthentication(
            UsernamePasswordAuthenticationToken.authenticated(
                "user", null, List.of(new SimpleGrantedAuthority("ROLE_USER"))));
    MockHttpSession session = new MockHttpSession();
    session.setAttribute(SessionAttributes.AUTHENTICATED_AT, NOW.minus(Duration.ofDays(1)));
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setSession(session);
    return request;
  }

  @Test
  void aFailedRefreshDoesNotBreakTheResponseAndIsCounted() throws Exception {
    doThrow(new IllegalStateException("cookie write failed")).when(cookies).writeCookieValue(any());
    MockHttpServletResponse response = new MockHttpServletResponse();

    filter.doFilter(
        authenticatedRequest(),
        response,
        (req, res) -> {
          ((HttpServletResponse) res).setStatus(200);
          res.getWriter().write("ok");
        });

    assertThat(response.getStatus()).isEqualTo(200);
    assertThat(response.getContentAsString()).isEqualTo("ok");
    assertThat(registry.get("mairor.session.cookie_refresh.failures").counter().count())
        .isEqualTo(1);
  }

  @Test
  void aSuccessfulRefreshIsNotCountedAsAFailure() throws Exception {
    MockHttpServletResponse response = new MockHttpServletResponse();

    filter.doFilter(
        authenticatedRequest(), response, (req, res) -> ((HttpServletResponse) res).setStatus(200));

    assertThat(registry.find("mairor.session.cookie_refresh.failures").counter()).isNull();
  }
}
