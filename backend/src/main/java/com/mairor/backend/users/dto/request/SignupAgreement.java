package com.mairor.backend.users.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * 가입 요청의 약관 동의 한 건 (API 명세 SignupAgreement).
 *
 * <p>{@code type}은 enum 이 아니라 문자열로 받는다. enum 이면 알 수 없는 값이 JSON 읽기 오류가 되어 오류 위치가 {@code body}로 나온다.
 * 필수 약관의 동의 여부·버전 일치는 {@link com.mairor.backend.users.support.AgreementPolicy}가 확인한다.
 */
public record SignupAgreement(
    @Schema(
            description = "약관 종류. TERMS·PRIVACY·AGE_OVER_14 는 필수, MARKETING 은 선택",
            allowableValues = {"TERMS", "PRIVACY", "AGE_OVER_14", "MARKETING"},
            example = "TERMS")
        @NotBlank(message = "필수 값입니다.")
        @Pattern(
            regexp = "TERMS|PRIVACY|AGE_OVER_14|MARKETING",
            message = "TERMS, PRIVACY, AGE_OVER_14, MARKETING 중 하나여야 합니다.")
        String type,
    @Schema(
            description = "동의한 약관 버전. 필수 약관은 서버의 현재 버전(AGREEMENT_*_VERSION)과 같아야 한다",
            example = "2026-10-26")
        @NotBlank(message = "필수 값입니다.")
        @Size(max = 20, message = "20자 이하여야 합니다.")
        String version,
    @Schema(description = "동의 여부. 필수 약관은 true 여야 한다", example = "true")
        @NotNull(message = "필수 값입니다.")
        Boolean agreed) {}
