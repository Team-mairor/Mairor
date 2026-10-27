package com.mairor.backend.users.support;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 비밀번호 구성 규칙: 영문자·숫자·특수문자(ASCII 기호)를 각각 1개 이상 포함하고, 유니코드 정규화(NFC) 후 UTF-8 72바이트 이하여야 한다 (BCrypt 입력
 * 한도). 길이(8~64자)는 {@code @Size}로 따로 검사한다. {@code null}은 통과시켜 {@code @NotNull}이 처리하게 한다.
 *
 * <p>규칙마다 메시지를 따로 내서 무엇이 빠졌는지 알려 준다.
 */
@Documented
@Constraint(validatedBy = StrongPasswordValidator.class)
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
public @interface StrongPassword {

  String message() default "비밀번호 규칙에 맞지 않습니다.";

  Class<?>[] groups() default {};

  Class<? extends Payload>[] payload() default {};
}
