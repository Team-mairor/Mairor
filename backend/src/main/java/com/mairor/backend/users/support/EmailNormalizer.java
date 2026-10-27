package com.mairor.backend.users.support;

import java.util.Locale;

/**
 * 이메일 정규화: 앞뒤 공백을 제거하고 소문자로 바꾼다. 검증·중복 판정·저장·로그인 조회가 모두 이 값을 쓰므로, 가입과 로그인이 같은 함수를 써야 한다.
 *
 * <p>비밀번호에는 쓰지 않는다 (비밀번호는 {@link PasswordNormalizer}).
 */
public final class EmailNormalizer {

  private EmailNormalizer() {}

  /** {@code null}은 그대로 돌려줘서 필수 값 검증이 처리하게 한다. */
  public static String normalize(String email) {
    return email == null ? null : email.strip().toLowerCase(Locale.ROOT);
  }
}
