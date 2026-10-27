package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.EmailNormalizer;
import com.mairor.backend.users.support.PasswordNormalizer;
import com.mairor.backend.users.support.StrongPassword;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * 자체 회원가입 요청 (API-USERS-001).
 *
 * <p>이메일은 생성되는 순간 정규화한다. JSON 역직렬화가 이 생성자를 거치므로 검증·중복 판정·저장이 모두 정규화한 값을 본다. 비밀번호는 정규화하지 않고 원문을 그대로
 * 두며, 해시 직전에만 {@link PasswordNormalizer}를 적용한다. 비밀번호 일치 여부는 서비스에서 확인한다.
 */
public record SignUpRequest(
    @NotBlank(message = "필수 값입니다.")
        @Size(max = 254, message = "254자 이하여야 합니다.")
        @Email(regexp = ".+@.+\\..+", message = "올바른 이메일 형식이 아닙니다.")
        String email,
    @NotNull(message = "필수 값입니다.")
        @Size(min = 8, max = 64, message = "8자 이상 64자 이하여야 합니다.")
        @StrongPassword
        String password,
    @NotNull(message = "필수 값입니다.") String passwordConfirm) {

  public SignUpRequest {
    email = EmailNormalizer.normalize(email);
  }

  /** 비밀번호가 로그에 남지 않도록 마스킹한다 (record 기본 toString은 값을 그대로 찍는다). */
  @Override
  public String toString() {
    return "SignUpRequest[email=" + email + ", password=***, passwordConfirm=***]";
  }
}
