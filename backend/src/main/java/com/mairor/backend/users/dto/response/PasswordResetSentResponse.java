package com.mairor.backend.users.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;

/**
 * 비밀번호 재설정 인증번호 발송 응답 (API-USERS-008). 가입 여부와 상관없이 같은 값이 나간다. 인증번호가 유효한 시간과 다시 보낼 수 있기까지의 시간을 초 단위로
 * 알려 FE 가 입력 제한 시간과 재발송 버튼을 표시하게 한다.
 */
public record PasswordResetSentResponse(
    @Schema(description = "인증번호가 유효한 시간(초)", example = "600") long expiresInSeconds,
    @Schema(description = "다시 보낼 수 있기까지의 시간(초)", example = "60") long resendAvailableInSeconds) {}
