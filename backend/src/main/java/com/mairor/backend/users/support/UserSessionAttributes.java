package com.mairor.backend.users.support;

/**
 * 로그인할 때 세션에 기록하는 회원 쪽 속성 이름. 값은 JDBC 세션이 JDK 직렬화로 저장하므로 UUID·문자열처럼 단순한 값만 쓴다. 세션 수명에 필요한 로그인 시각은
 * {@code common} 이 읽으므로 {@code SessionAttributes} 에 있다.
 */
public final class UserSessionAttributes {

  /** 기기 목록·개별 로그아웃에서 세션을 가리키는 공개용 식별자({@link java.util.UUID}). 실제 세션 ID 는 쿠키 값이라 밖으로 내보내지 않는다. */
  public static final String SESSION_REF = "sessionRef";

  /** 로그인 기기 요약 (예: {@code Chrome · Windows}). {@link DeviceSummary} 가 만든다. */
  public static final String DEVICE = "device";

  private UserSessionAttributes() {}
}
