package com.mairor.backend.common.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.util.OnCommittedResponseWrapper;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.CookieSerializer.CookieValue;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 쿠키 슬라이딩 갱신. 인증된 유효 세션의 성공 응답에서 같은 세션 ID 의 쿠키를 다시 써서 브라우저 보관 기간을 늘린다. 서버 유휴 만료는 Spring Session 이
 * 세션에 접근할 때 연장하므로, 이 필터는 같은 요청에서 쿠키 쪽만 맞춘다. 세션 ID·CSRF 토큰·로그인 시각은 바꾸지 않는다.
 *
 * <p>역할 분리: 쿠키 최초 발급(로그인·계정 전환)과 만료 쿠키(세션 폐기)는 Spring Session 이 쓴다. 이 필터는 <b>요청 중 세션이 바뀌지 않은 기존 인증
 * 세션</b>만 다룬다. 커밋 훅이 실행될 시점에는 Spring Session 의 쿠키 발급이 아직 일어나지 않아 {@code Set-Cookie} 헤더 유무로는 구분할 수
 * 없으므로, 필터 진입 때와 같은 세션 ID 인지로 판단한다.
 *
 * <p>실행 시점은 두 곳이고 요청당 한 번만 실행한다. 본문이 있는 응답은 커밋 직전 훅에서, 본문 없는 204 처럼 커밋되지 않은 채 체인이 반환되는 응답은 체인 반환
 * 직후에서 실행된다. {@code SecurityContextHolderFilter} 는 체인이 반환되면 컨텍스트를 비우므로, 늦게 실행되는 커밋 훅이 읽을 값은 필터 진입
 * 시점에 스냅샷으로 잡아 둔다.
 *
 * <p>쿠키는 {@link CookieSerializer} 로 쓴다. 요청별 {@code Max-Age} 는 {@link
 * CookieValue#setCookieMaxAge(int)} 로 지정하며 공유 serializer 의 설정은 건드리지 않는다.
 */
public class SessionCookieRefreshFilter extends OncePerRequestFilter {

  private static final Logger log = LoggerFactory.getLogger(SessionCookieRefreshFilter.class);

  /** 필터 진입 시점의 상태. 인증 여부·세션 ID·로그인 시각. */
  private record Snapshot(boolean authenticated, String sessionId, Instant authenticatedAt) {

    boolean usable() {
      return authenticated && sessionId != null && authenticatedAt != null;
    }
  }

  private final SessionLifetimePolicy policy;
  private final Clock clock;
  private final CookieSerializer cookieSerializer;
  private final SessionMetrics metrics;

  public SessionCookieRefreshFilter(
      SessionLifetimePolicy policy,
      Clock clock,
      CookieSerializer cookieSerializer,
      SessionMetrics metrics) {
    this.policy = policy;
    this.clock = clock;
    this.cookieSerializer = cookieSerializer;
    this.metrics = metrics;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    Snapshot snapshot = snapshot(request);
    if (!snapshot.usable()) {
      chain.doFilter(request, response);
      return;
    }
    AtomicBoolean done = new AtomicBoolean();
    OnCommittedResponseWrapper wrapped =
        new OnCommittedResponseWrapper(response) {
          @Override
          protected void onResponseCommitted() {
            refresh(request, response, snapshot, done);
          }
        };
    boolean completed = false;
    try {
      chain.doFilter(request, wrapped);
      completed = true;
    } finally {
      // 예외로 끝난 요청은 갱신하지 않는다
      if (completed) {
        refresh(request, response, snapshot, done);
      }
    }
  }

  private Snapshot snapshot(HttpServletRequest request) {
    boolean authenticated =
        AuthenticationState.isAuthenticated(SecurityContextHolder.getContext().getAuthentication());
    HttpSession session = authenticated ? request.getSession(false) : null;
    if (session == null) {
      return new Snapshot(authenticated, null, null);
    }
    Object authenticatedAt = session.getAttribute(SessionAttributes.AUTHENTICATED_AT);
    return new Snapshot(true, session.getId(), authenticatedAt instanceof Instant at ? at : null);
  }

  private void refresh(
      HttpServletRequest request,
      HttpServletResponse response,
      Snapshot snapshot,
      AtomicBoolean done) {
    if (!done.compareAndSet(false, true)) {
      return;
    }
    try {
      if (request.getAttribute(SessionAttributes.COOKIE_REFRESH_SUPPRESSED) != null
          || response.getStatus() >= 400) {
        return;
      }
      HttpSession current = request.getSession(false);
      if (current == null || !snapshot.sessionId().equals(current.getId())) {
        return;
      }
      Instant expiresAt = policy.absoluteExpiryOf(snapshot.authenticatedAt());
      long remaining = Duration.between(clock.instant(), expiresAt).toSeconds();
      if (remaining <= 0) {
        return;
      }
      long maxAge = Math.min(policy.cookieMaxAge().toSeconds(), remaining);
      CookieValue cookie = new CookieValue(request, response, current.getId());
      cookie.setCookieMaxAge((int) maxAge);
      cookieSerializer.writeCookieValue(cookie);
    } catch (RuntimeException e) {
      // 갱신 실패가 응답 자체를 깨뜨리면 안 된다. 세션 ID 같은 민감한 값은 남기지 않는다
      metrics.cookieRefreshFailure();
      log.warn("세션 쿠키 갱신에 실패했습니다: {}", e.getClass().getSimpleName());
    }
  }
}
