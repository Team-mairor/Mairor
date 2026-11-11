package com.mairor.backend.camera.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record FaceRegistrationRequest(
    @NotNull
        @Schema(description = "준비 중인 내부 영상 ID", example = "00000000-0000-4000-8000-000000000101")
        UUID videoId,
    @Schema(
            description = "이미 승인 가이드가 있을 때 그 ID",
            example = "00000000-0000-4000-8000-000000000201",
            nullable = true)
        UUID guideId,
    @NotBlank @Size(max = 50) @Schema(description = "등록 용도와 보관 안내 버전", example = "v1")
        String noticeVersion,
    @NotNull @Schema(description = "등록 안내 동의 여부. true만 허용한다", example = "true") Boolean agreed,
    @NotNull @Valid @Schema(description = "클라이언트가 판정한 촬영 조건") FaceChecksData checks) {}
