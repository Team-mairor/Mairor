package com.mairor.backend.common.security;

import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponseWriter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.time.Clock;
import java.time.Instant;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 절대 만료. 로그인 성공 시각({@link SessionAttributes#AUTHENTICATED_AT})부터 절대 만료 시간이 지난 세션은 활동 중이어도 끝낸다. 서버
 * 유휴 만료는 슬라이딩이라 탈취된 세션을 계속 쓰면 연장되기만 하므로 이 상한이 필요하다. Spring Session 에는 이 기능이 없다.
 *
 * <p>{@code SecurityContextHolderFilter} 뒤, {@code CsrfFilter} 앞에 둔다. 세션의 인증 정보를 읽은 뒤에 판단해야 하고, 만료된
 * 요청이 CSRF 검사(403)에 먼저 걸리면 "만료 = 401" 이 깨진다.
 *
 * <ul>
 *   <li>보호 경로: 세션을 끝내고 체인을 계속하지 않은 채 곧바로 401 을 쓴다. 변경 요청(POST 등)도 403 이 아니라 401 이다.
 *   <li>공개 경로(permitAll): 세션만 끝내고 체인을 계속한다. 만료된 쿠키를 가진 브라우저도 다시 로그인할 수 있어야 한다.
 *   <li>익명 요청과 세션이 없는 요청은 건드리지 않는다. 유휴 만료된 세션은 Spring Session 이 이미 지워서 세션이 없는 요청과 구분되지 않는다.
 * </ul>
 *
 * <p>인증 여부는 구체 타입이 아니라 {@link Authentication} 으로 판단한다. {@code common} 은 {@code users} 를 import 하지
 * 않는다.
 */
public class SessionLifetimeFilter extends OncePerRequestFilter {

  private final SessionLifetimePolicy policy;
  private final Clock clock;
  private final ErrorResponseWriter errorWriter;
  private final RequestMatcher publicPaths;

  /**
   * @param publicPaths 인증 없이 열려 있는 경로. 만료된 세션이어도 요청을 막지 않고 통과시킨다
   */
  public SessionLifetimeFilter(
      SessionLifetimePolicy policy,
      Clock clock,
      ErrorResponseWriter errorWriter,
      RequestMatcher publicPaths) {
    this.policy = policy;
    this.clock = clock;
    this.errorWriter = errorWriter;
    this.publicPaths = publicPaths;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    if (!AuthenticationState.isAuthenticated(
        SecurityContextHolder.getContext().getAuthentication())) {
      chain.doFilter(request, response);
      return;
    }
    HttpSession session = request.getSession(false);
    if (session == null || !isExpired(session)) {
      chain.doFilter(request, response);
      return;
    }

    SecurityContextHolder.clearContext();
    request.setAttribute(SessionAttributes.COOKIE_REFRESH_SUPPRESSED, Boolean.TRUE);
    session.invalidate();
    if (publicPaths.matches(request)) {
      chain.doFilter(request, response);
      return;
    }
    errorWriter.write(response, ErrorCode.UNAUTHORIZED);
  }

  private boolean isExpired(HttpSession session) {
    Object value = session.getAttribute(SessionAttributes.AUTHENTICATED_AT);
    if (!(value instanceof Instant authenticatedAt)) {
      return true;
    }
    return policy.isAbsolutelyExpired(authenticatedAt, clock.instant());
  }
}
