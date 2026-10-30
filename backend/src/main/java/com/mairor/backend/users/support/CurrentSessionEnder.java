package com.mairor.backend.users.support;

import com.mairor.backend.common.security.SessionAttributes;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.context.SecurityContextHolder;

/**
 * 이 요청의 세션을 끝낸다. 로그아웃과, 기기 관리에서 현재 기기를 포함해 지우는 경우가 같은 방식으로 끝내야 해서 한곳에 둔다.
 *
 * <ul>
 *   <li>세션 저장소에서 지우는 것만으로는 부족하다. 이 요청이 들고 있는 세션이 응답을 커밋할 때 다시 저장되어 되살아난다. 그래서 요청의 세션을 {@code
 *       invalidate()} 한다. 만료 쿠키는 Spring Session 이 내려 준다.
 *   <li>쿠키 갱신 필터가 이 응답에서 만료 쿠키를 덮어쓰지 못하게 억제 플래그를 세운다.
 * </ul>
 */
public final class CurrentSessionEnder {

  private CurrentSessionEnder() {}

  public static void end(HttpServletRequest request) {
    SecurityContextHolder.clearContext();
    request.setAttribute(SessionAttributes.COOKIE_REFRESH_SUPPRESSED, Boolean.TRUE);
    HttpSession session = request.getSession(false);
    if (session != null) {
      session.invalidate();
    }
  }
}
