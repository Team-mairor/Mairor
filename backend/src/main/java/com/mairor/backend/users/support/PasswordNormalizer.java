package com.mairor.backend.users.support;

import java.text.Normalizer;

/**
 * 비밀번호 유니코드 정규화(NFC). 같은 글자가 입력 방식에 따라 다른 바이트로 들어와(예: 한글 조합형/완성형) 로그인이 안 되는 문제를 막는다. 공백은 건드리지 않는다.
 *
 * <p>바이트 수 검사와 해시는 정규화한 값으로 한다. 가입과 로그인이 같은 함수를 써야 한다.
 */
public final class PasswordNormalizer {

  private PasswordNormalizer() {}

  /** {@code null}은 그대로 돌려줘서 필수 값 검증이 처리하게 한다. */
  public static String normalize(String password) {
    return password == null ? null : Normalizer.normalize(password, Normalizer.Form.NFC);
  }
}
