package com.mairor.backend.common.security;

/**
 * 세션 수명 필터와 로그인 쪽이 함께 쓰는 속성 이름. {@code common} 은 {@code users} 를 import 하지 않으므로, 로그인(users)이 세션에
 * 기록하는 값의 이름을 여기에 둔다.
 */
public final class SessionAttributes {

  /**
   * 로그인에 성공한 시각({@link java.time.Instant}). 세션 속성. 절대 만료의 기준이며 로그인할 때만 기록하고 일반 요청이나 쿠키 갱신으로 바꾸지
   * 않는다.
   */
  public static final String AUTHENTICATED_AT = "authenticatedAt";

  /**
   * 이 요청의 응답에서는 세션 쿠키를 갱신하지 않는다. 요청 속성. 로그인·로그아웃처럼 세션을 새로 만들거나 끝내는 경로가 세운다. 세션 쿠키 발급·만료는 Spring
   * Session 이 하므로, 갱신 필터가 그 쿠키를 덮어쓰지 않게 하는 안전장치다.
   */
  public static final String COOKIE_REFRESH_SUPPRESSED =
      SessionAttributes.class.getName() + ".COOKIE_REFRESH_SUPPRESSED";

  private SessionAttributes() {}
}
