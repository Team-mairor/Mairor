package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.EmailNormalizer;
import com.mairor.backend.users.support.PasswordNormalizer;
import com.mairor.backend.users.support.PhoneNormalizer;
import com.mairor.backend.users.support.StrongPassword;
import com.mairor.backend.users.support.TextNormalizer;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import java.util.List;

/**
 * 자체 회원가입 요청 (API-USERS-001). 이메일은 생성자에서 정규화하므로 검증·중복 판정·저장이 모두 정규화한 값을 본다. 비밀번호는 원문 그대로 두고 해시 직전에만
 * {@link PasswordNormalizer}를 적용한다.
 *
 * <p>필수는 이메일·비밀번호·확인값·약관({@code agreements})이고, 프로필 필드는 값이 있을 때만 검증한다. 생년월일 범위와 필수 약관 동의 여부는 서비스가
 * 확인한다. {@code gender}는 잘못된 값의 오류가 {@code gender} 칸에 붙도록 enum 이 아닌 문자열로 받는다. {@code
 * emailVerificationToken}은 가입에 이메일 인증을 요구할 때만 쓴다.
 */
public record SignUpRequest(
    @Schema(description = "가입 이메일. 공백 제거·소문자 변환 후 검증한다", example = "user@example.com")
        @NotBlank(message = "필수 값입니다.")
        @Size(max = 254, message = "254자 이하여야 합니다.")
        @Email(regexp = ".+@.+\\..+", message = "올바른 이메일 형식이 아닙니다.")
        String email,
    @Schema(description = "8~64자, 영문자·숫자·특수문자 각 1개 이상", example = "Password1!")
        @NotNull(message = "필수 값입니다.")
        @Size(min = 8, max = 64, message = "8자 이상 64자 이하여야 합니다.")
        @StrongPassword
        String password,
    @Schema(description = "비밀번호와 같은 값", example = "Password1!") @NotNull(message = "필수 값입니다.")
        String passwordConfirm,
    @Schema(description = "선택. 2~20자, 한글·영문·숫자·밑줄", example = "mairor_user")
        @Size(min = 2, max = 20, message = "2자 이상 20자 이하여야 합니다.")
        @Pattern(regexp = "[가-힣A-Za-z0-9_]*", message = "한글, 영문, 숫자, 밑줄(_)만 사용할 수 있습니다.")
        String nickname,
    @Schema(description = "선택. 2~50자, 한글·영문·공백", example = "홍길동")
        @Size(min = 2, max = 50, message = "2자 이상 50자 이하여야 합니다.")
        @Pattern(regexp = "[가-힣A-Za-z ]*", message = "한글, 영문, 공백만 사용할 수 있습니다.")
        String name,
    @Schema(description = "선택. 휴대폰 번호(숫자만)", example = "01012345678")
        @Pattern(regexp = "01[016789]\\d{7,8}", message = "올바른 휴대폰 번호 형식이 아닙니다.")
        String phone,
    @Schema(description = "선택. 생년월일(만 14세 이상)", example = "2000-01-01") LocalDate birthDate,
    @Schema(
            description = "선택. 성별",
            allowableValues = {"MALE", "FEMALE"},
            example = "FEMALE")
        @Pattern(regexp = "MALE|FEMALE", message = "MALE 또는 FEMALE 이어야 합니다.")
        String gender,
    @Schema(description = "약관 동의 기록. TERMS·PRIVACY·AGE_OVER_14 는 필수이고 같은 종류를 두 번 보낼 수 없다")
        @NotNull(message = "필수 값입니다.")
        @Size(max = 10, message = "약관 항목이 너무 많습니다.")
        List<@NotNull(message = "필수 값입니다.") @Valid SignupAgreement> agreements,
    @Schema(
            description = "이메일 인증 확인(API-USERS-013)이 발급한 토큰. 가입에 이메일 인증을 요구하도록 설정했을 때만 필수",
            example = "이메일 인증 확인 응답의 verificationToken")
        @Size(max = 200, message = "200자 이하여야 합니다.")
        String emailVerificationToken) {

  public SignUpRequest {
    email = EmailNormalizer.normalize(email);
    nickname = TextNormalizer.stripToNull(nickname);
    name = TextNormalizer.stripToNull(name);
    phone = PhoneNormalizer.normalize(phone);
    gender = TextNormalizer.stripToNull(gender);
    emailVerificationToken = TextNormalizer.stripToNull(emailVerificationToken);
  }

  /** 비밀번호와 개인정보가 로그에 남지 않도록 마스킹한다 (record 기본 toString은 값을 그대로 찍는다). */
  @Override
  public String toString() {
    return "SignUpRequest[email="
        + email
        + ", password=***, passwordConfirm=***, nickname=***, name=***, phone=***, birthDate=***,"
        + " gender=***, agreements="
        + (agreements == null ? 0 : agreements.size())
        + "건, emailVerificationToken=***]";
  }
}
