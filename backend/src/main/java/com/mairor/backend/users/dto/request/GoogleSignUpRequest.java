package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.PhoneNormalizer;
import com.mairor.backend.users.support.TextNormalizer;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import java.util.List;

/**
 * Google 가입 완료 요청. 자체 가입({@link SignUpRequest})에서 이메일·비밀번호·확인값·이메일 인증 토큰을 뺀 나머지이고, 필드 이름과 규칙·오류 문구가
 * 같아서 FE 가 같은 입력 묶음과 {@code details[].field} 를 그대로 쓴다. 이메일은 Google 이 확인한 값을 가입 대기에서 가져온다.
 */
public record GoogleSignUpRequest(
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
        List<@NotNull(message = "필수 값입니다.") @Valid SignupAgreement> agreements) {

  public GoogleSignUpRequest {
    nickname = TextNormalizer.stripToNull(nickname);
    name = TextNormalizer.stripToNull(name);
    phone = PhoneNormalizer.normalize(phone);
    gender = TextNormalizer.stripToNull(gender);
  }

  /** 개인정보가 로그에 남지 않도록 마스킹한다 (record 기본 toString은 값을 그대로 찍는다). */
  @Override
  public String toString() {
    return "GoogleSignUpRequest[nickname=***, name=***, phone=***, birthDate=***, gender=***,"
        + " agreements="
        + (agreements == null ? 0 : agreements.size())
        + "건]";
  }
}
