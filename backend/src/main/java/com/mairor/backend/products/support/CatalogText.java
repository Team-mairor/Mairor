package com.mairor.backend.products.support;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 카탈로그 텍스트(브랜드·제품명) 입력 규칙: 비어 있지 않고, 앞뒤 유니코드 공백을 지운 원문이 {@link #max()} 자 이하여야 한다.
 *
 * <p>공백 기준은 {@link CatalogTextNormalizer}와 같아서 NBSP·전각 공백만 있는 값도 빈 값이다. 길이는 {@link
 * CatalogTextNormalizer#trimmed}의 {@link String#length()}로 센다(엔티티 상한과 같은 NFC 전 UTF-16 단위). {@code
 * null}도 빈 값으로 막는다(필수 입력에만 쓴다).
 */
@Documented
@Constraint(validatedBy = CatalogTextValidator.class)
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
public @interface CatalogText {

  /** 앞뒤 공백을 지운 원문의 최대 길이. 엔티티 상수(예: {@code Product.NAME_MAX_LENGTH})를 넣는다. */
  int max();

  String message() default "카탈로그 텍스트 규칙에 맞지 않습니다.";

  Class<?>[] groups() default {};

  Class<? extends Payload>[] payload() default {};
}
