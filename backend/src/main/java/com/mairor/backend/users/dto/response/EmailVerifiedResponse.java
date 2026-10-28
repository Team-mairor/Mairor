package com.mairor.backend.users.dto.response;

import java.time.Instant;

/**
 * 인증번호 확인 응답 (API-USERS-013). {@code verificationToken}은 이 응답에서만 평문으로 나가고, 서버에는 해시만 남는다. 가입 요청에 실어
 * 보내면 이메일 소유 확인으로 인정된다.
 */
public record EmailVerifiedResponse(String verificationToken, Instant expiresAt) {}
