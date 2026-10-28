package com.mairor.backend.users.support;

import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.stereotype.Component;

/** 이메일 인증 완료 토큰 생성. 32바이트 난수를 URL에 안전한 base64(43자)로 만든다. */
@Component
public class VerificationTokens {

  private final SecureRandom random = new SecureRandom();

  public String generate() {
    byte[] bytes = new byte[32];
    random.nextBytes(bytes);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }
}
