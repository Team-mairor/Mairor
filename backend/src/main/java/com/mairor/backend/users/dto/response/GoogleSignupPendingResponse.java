package com.mairor.backend.users.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;

/** Google 가입 대기 조회 응답. 추가 정보 화면에 고정으로 보여 줄 이메일과 이름, 가입을 마쳐야 하는 시각이다. */
public record GoogleSignupPendingResponse(
    @Schema(description = "Google 이 확인한 이메일. 가입 이메일로 쓰며 바꿀 수 없다", example = "user@gmail.com")
        String email,
    @Schema(description = "Google 표시 이름. 없으면 null", example = "홍길동", nullable = true) String name,
    @Schema(description = "가입 대기가 만료되는 시각(UTC)", example = "2026-11-02T01:10:00Z")
        Instant expiresAt) {}
