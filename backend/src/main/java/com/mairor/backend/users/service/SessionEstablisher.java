package com.mairor.backend.users.service;

import com.mairor.backend.common.security.AuthenticationState;
import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.support.AuthenticatedUser;
import com.mairor.backend.users.support.CurrentSessionEnder;
import com.mairor.backend.users.support.DeviceSummary;
import com.mairor.backend.users.support.UserSessionAttributes;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.time.Clock;
import java.util.List;
import java.util.UUID;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.DeferredCsrfToken;
import org.springframework.stereotype.Component;

/**
 * 인증이 끝난 회원의 로그인 세션을 만든다. 자체 로그인과 Google 로그인이 같이 쓴다. 자격 증명을 확인하는 일({@link UserLoginService})과 HTTP
 * 세션을 발급하는 일을 나눠서, 로그인 방식이 늘어도 세션 규칙(세션 고정 방지, 로그인 시각·기기 기록, CSRF 토큰 교체)은 한곳에만 있다.
 *
 * <p>CSRF 저장소와 핸들러는 보안 설정({@code SecurityConfig})의 빈을 쓴다. CSRF 필터가 검증하는 것과 같은 방식으로 토큰을 발급해야 필터가
 * 통과시킨다.
 */
@Component
public class SessionEstablisher {

  private final SecurityContextRepository securityContextRepository;
  private final CsrfTokenRepository csrfTokenRepository;
  private final CsrfTokenRequestHandler csrfTokenRequestHandler;
  private final Clock clock;

  public SessionEstablisher(
      SecurityContextRepository securityContextRepository,
      CsrfTokenRepository csrfTokenRepository,
      CsrfTokenRequestHandler csrfTokenRequestHandler,
      Clock clock) {
    this.securityContextRepository = securityContextRepository;
    this.csrfTokenRepository = csrfTokenRepository;
    this.csrfTokenRequestHandler = csrfTokenRequestHandler;
    this.clock = clock;
  }

  /**
   * 인증된 세션을 만들고 응답에 줄 CSRF 토큰을 돌려준다.
   *
   * <ol>
   *   <li>이미 인증된 세션이면 폐기하고 새 세션을 만든다(다른 계정으로 전환할 때 이전 계정의 속성이 넘어오지 않게). 익명 세션이면 세션 ID 만 바꾼다(세션 고정
   *       방지).
   *   <li>새 {@code SecurityContext} 를 만들어 저장한다. 기존 컨텍스트를 고쳐 쓰지 않는다.
   *   <li>로그인 시각·기기 식별자·기기 요약을 세션에 기록한다.
   *   <li>CSRF 토큰을 교체하고, 교체된 요청 속성의 토큰을 돌려준다.
   *   <li>이 응답에서는 쿠키 갱신 필터가 쓰지 않도록 표시한다. 쿠키 발급은 Spring Session 이 한다.
   * </ol>
   *
   * <p>도중에 실패하면 지금까지 만든 인증 상태(컨텍스트·세션)를 모두 버리고 예외를 그대로 던진다. 그렇지 않으면 응답은 실패인데 세션은 응답을 커밋할 때 저장되어 이후
   * 내 계정 조회가 인증된 것으로 나온다. 이미 로그인한 세션으로 다른 계정 로그인을 시작했다면 이전 세션은 시작하면서 이미 폐기된 뒤다.
   *
   * <p>세션이 JDBC 에 저장되는 시점은 응답 커밋 즈음이라 이 메서드가 끝났다고 저장이 끝난 것은 아니다. 이전 해시로 검증을 끝낸 로그인이 비밀번호 재설정 이후에
   * 세션을 발급하는 경합의 방어(비밀번호 버전 재검증)는 비밀번호 재설정 이슈에서 이 지점 뒤에 더한다.
   */
  public String establish(User user, HttpServletRequest request, HttpServletResponse response) {
    try {
      return build(user, request, response);
    } catch (RuntimeException e) {
      abandon(request, e);
      throw e;
    }
  }

  private String build(User user, HttpServletRequest request, HttpServletResponse response) {
    startFreshSession(request);

    AuthenticatedUser principal = new AuthenticatedUser(user.getId(), user.getEmail());
    Authentication authentication =
        UsernamePasswordAuthenticationToken.authenticated(
            principal, null, List.of(new SimpleGrantedAuthority("ROLE_USER")));
    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(authentication);
    SecurityContextHolder.setContext(context);
    securityContextRepository.saveContext(context, request, response);

    HttpSession session = request.getSession();
    session.setAttribute(SessionAttributes.AUTHENTICATED_AT, clock.instant());
    session.setAttribute(UserSessionAttributes.SESSION_REF, UUID.randomUUID());
    session.setAttribute(
        UserSessionAttributes.DEVICE, DeviceSummary.of(request.getHeader("User-Agent")));

    String csrfToken = issueCsrfToken(request, response);

    request.setAttribute(SessionAttributes.COOKIE_REFRESH_SUPPRESSED, Boolean.TRUE);
    return csrfToken;
  }

  /** 만들다 만 인증 상태를 버린다. 정리 중의 오류는 원래 예외에 붙이고, 원래 예외를 가리지 않는다. */
  private void abandon(HttpServletRequest request, RuntimeException cause) {
    try {
      SecurityContextHolder.clearContext();
      request.removeAttribute(RequestAttributeSecurityContextRepository.DEFAULT_REQUEST_ATTR_NAME);
      CurrentSessionEnder.end(request);
    } catch (RuntimeException cleanupFailure) {
      cause.addSuppressed(cleanupFailure);
    }
  }

  /**
   * 세션의 옛 CSRF 토큰을 지우고 새 토큰을 만들어 저장한 뒤, 요청 속성에 새 토큰을 올리고 그 값을 돌려준다. 세션 ID 를 바꿔도 세션 속성은 유지되므로 로그인
   * 전(익명) 세션의 토큰이 남기 때문에 무조건 교체한다. 컨트롤러 인자 등으로 미리 받아 둔 {@code CsrfToken} 객체는 옛 토큰을 가리키므로 쓰지 않고, 교체한
   * 뒤 요청 속성에서 다시 읽은 값을 쓴다.
   *
   * <p>{@code CsrfAuthenticationStrategy} 는 세션에 토큰이 이미 있을 때만 교체하고 없으면 아무것도 하지 않아서 쓰지 않는다.
   */
  private String issueCsrfToken(HttpServletRequest request, HttpServletResponse response) {
    csrfTokenRepository.saveToken(null, request, response);
    DeferredCsrfToken deferred = csrfTokenRepository.loadDeferredToken(request, response);
    csrfTokenRequestHandler.handle(request, response, deferred::get);
    CsrfToken token = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
    return token.getToken();
  }

  private void startFreshSession(HttpServletRequest request) {
    HttpSession existing = request.getSession(false);
    if (existing == null) {
      request.getSession(true);
    } else if (AuthenticationState.isAuthenticated(
        SecurityContextHolder.getContext().getAuthentication())) {
      existing.invalidate();
      request.getSession(true);
    } else {
      request.changeSessionId();
    }
  }
}
