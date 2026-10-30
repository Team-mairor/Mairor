package com.mairor.backend.common.security;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;

/** 요청의 인증 여부 판단. 필터와 로그인 처리가 같은 기준을 쓴다. */
public final class AuthenticationState {

  private AuthenticationState() {}

  /** 익명 인증(Spring Security 가 미인증 요청에 채우는 값)은 인증된 것으로 보지 않는다. */
  public static boolean isAuthenticated(Authentication authentication) {
    return authentication != null
        && authentication.isAuthenticated()
        && !(authentication instanceof AnonymousAuthenticationToken);
  }
}
