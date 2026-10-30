package com.mairor.backend.users.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;

/**
 * 로그인 기기 하나. {@code sessionRef} 는 로그인 때 만든 무작위 UUID 이며 표시·선택용이다. 세션 쿠키 값(실제 세션 ID)은 응답 어디에도 담지 않는다.
 */
public record SessionItemResponse(
    @Schema(description = "기기 로그아웃 때 이 기기를 가리키는 값. 세션 ID 가 아니다") String sessionRef,
    @Schema(description = "브라우저 · 운영체제 요약. 알 수 없으면 '알 수 없는 기기'", example = "Chrome · Windows")
        String device,
    @Schema(description = "로그인한 시각") Instant createdAt,
    @Schema(description = "마지막으로 이 기기에서 요청한 시각") Instant lastAccessedAt,
    @Schema(description = "지금 요청을 보낸 기기인지") boolean current) {}
