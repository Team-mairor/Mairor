package com.mairor.backend.products.support;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

/** {@link CatalogText} 검사. 예외를 던지지 않고 규칙마다 메시지를 따로 낸다. */
public class CatalogTextValidator implements ConstraintValidator<CatalogText, String> {

  static final String REQUIRED = "필수 값입니다.";

  private int max;

  @Override
  public void initialize(CatalogText annotation) {
    this.max = annotation.max();
  }

  @Override
  public boolean isValid(String value, ConstraintValidatorContext context) {
    if (value == null) {
      return fail(context, REQUIRED);
    }
    String trimmed = CatalogTextNormalizer.trimmed(value);
    if (trimmed.isEmpty()) {
      return fail(context, REQUIRED);
    }
    if (trimmed.length() > max) {
      return fail(context, max + "자 이하여야 합니다.");
    }
    return true;
  }

  private static boolean fail(ConstraintValidatorContext context, String message) {
    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(message).addConstraintViolation();
    return false;
  }
}
