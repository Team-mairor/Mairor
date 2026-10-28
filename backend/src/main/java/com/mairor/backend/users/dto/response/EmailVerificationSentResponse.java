package com.mairor.backend.users.dto.response;

/**
 * 인증번호 발송 응답 (API-USERS-012). 인증번호가 유효한 시간과, 다시 보낼 수 있기까지의 시간을 초 단위로 알려 FE 가 입력 제한 시간과 재발송 버튼을 표시하게
 * 한다.
 */
public record EmailVerificationSentResponse(long expiresInSeconds, long resendAvailableInSeconds) {}
