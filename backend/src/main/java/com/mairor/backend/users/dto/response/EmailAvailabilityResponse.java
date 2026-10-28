package com.mairor.backend.users.dto.response;

/**
 * 가입 가능 이메일 확인 결과 (API 명세 EmailAvailability). {@code email}은 서버가 정규화한 값이다. 결과는 예약이 아니라서 가입할 때 중복을
 * 다시 검사한다.
 */
public record EmailAvailabilityResponse(String email, boolean available) {}
