package com.mairor.backend.photos.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

public record PhotoShareResponse(
    @Schema(description = "공유 사진 ID", example = "00000000-0000-4000-8000-000000000301")
        UUID shareId,
    @Schema(description = "QR 공유 링크 만료 시각", example = "2026-11-14T12:10:00Z") Instant expiresAt) {}
