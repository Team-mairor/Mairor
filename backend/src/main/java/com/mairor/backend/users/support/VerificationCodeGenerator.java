package com.mairor.backend.users.support;

import java.security.SecureRandom;
import org.springframework.stereotype.Component;

/** 이메일 인증번호(6자리 숫자) 생성. 예측할 수 없도록 {@link SecureRandom}을 쓰고, 앞자리가 0이어도 6자리로 맞춘다. */
@Component
public class VerificationCodeGenerator {

  public static final int LENGTH = 6;

  private final SecureRandom random = new SecureRandom();

  public String generate() {
    return "%06d".formatted(random.nextInt(1_000_000));
  }
}
