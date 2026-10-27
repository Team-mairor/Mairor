package com.mairor.backend.users.support;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.nio.charset.StandardCharsets;

public class StrongPasswordValidator implements ConstraintValidator<StrongPassword, String> {

  /** BCrypt는 입력을 72바이트까지만 쓴다. */
  static final int MAX_BYTES = 72;

  @Override
  public boolean isValid(String password, ConstraintValidatorContext context) {
    if (password == null) {
      return true;
    }
    String normalized = PasswordNormalizer.normalize(password);

    boolean letter = false;
    boolean digit = false;
    boolean symbol = false;
    for (int i = 0; i < normalized.length(); i++) {
      char c = normalized.charAt(i);
      if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')) {
        letter = true;
      } else if (c >= '0' && c <= '9') {
        digit = true;
      } else if (c > 0x20 && c < 0x7F) {
        // 출력 가능한 ASCII 중 영문자·숫자가 아닌 것 = 기호. 한글·이모지·공백은 특수문자로 세지 않는다.
        symbol = true;
      }
    }

    context.disableDefaultConstraintViolation();
    boolean valid = true;
    if (!letter) {
      valid = fail(context, "영문자를 1개 이상 포함해야 합니다.");
    }
    if (!digit) {
      valid = fail(context, "숫자를 1개 이상 포함해야 합니다.");
    }
    if (!symbol) {
      valid = fail(context, "특수문자(!@#$ 등 ASCII 기호)를 1개 이상 포함해야 합니다.");
    }
    if (normalized.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) {
      valid = fail(context, "UTF-8 기준 72바이트를 넘을 수 없습니다. 한글 등은 글자당 3바이트로 계산됩니다.");
    }
    return valid;
  }

  private static boolean fail(ConstraintValidatorContext context, String message) {
    context.buildConstraintViolationWithTemplate(message).addConstraintViolation();
    return false;
  }
}
