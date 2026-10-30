package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.EmailNormalizer;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

/**
 * 자체 로그인 요청 (API-USERS-002). 이메일은 생성자에서 정규화(앞뒤 공백 제거 + 소문자)한 값으로 조회하며 형식은 검사하지 않는다. 형식이 맞지 않으면 어차피
 * 조회에 실패해 401 이 되므로, 입력 규칙을 응답으로 알려 주지 않는다.
 *
 * <p>비밀번호는 원문 그대로 두고 비교 직전에만 {@code PasswordNormalizer} 를 적용한다. 강도·최소 길이 규칙은 적용하지 않는다(정책이 바뀌기 전에
 * 가입한 비밀번호도 로그인돼야 한다). 다만 CPU 를 소진하는 과대 입력을 막으려고 크기 상한(256자)만 둔다. 가입 정책의 최대 길이(64자)의 4배다.
 */
public record LoginRequest(
    @Schema(description = "가입 이메일. 공백 제거·소문자 변환 후 조회한다", example = "user@example.com")
        @NotBlank(message = "필수 값입니다.")
        @Size(max = 254, message = "254자 이하여야 합니다.")
        String email,
    @Schema(description = "비밀번호. 강도 규칙은 검사하지 않고 입력 크기만 256자로 제한한다", example = "Password1!")
        @NotEmpty(message = "필수 값입니다.")
        @Size(max = 256, message = "256자 이하여야 합니다.")
        String password) {

  public LoginRequest {
    email = EmailNormalizer.normalize(email);
  }

  /** 비밀번호가 로그에 남지 않도록 마스킹한다 (record 기본 toString은 값을 그대로 찍는다). */
  @Override
  public String toString() {
    return "LoginRequest[email=" + email + ", password=***]";
  }
}
