package com.mairor.backend.camera.dto;

import com.mairor.backend.camera.entity.FaceChecks;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

public record FaceChecksData(
    @NotNull @Schema(description = "밝고 고른 조명 여부", example = "true") Boolean lighting,
    @NotNull @Schema(description = "적정 촬영 거리 여부", example = "true") Boolean distance,
    @NotNull @Schema(description = "정면 촬영 여부", example = "true") Boolean frontal,
    @NotNull @Schema(description = "얼굴 가림이 없는지 여부", example = "true") Boolean unobstructed,
    @NotNull @Schema(description = "클라이언트의 메이크업 감지 여부", example = "false") Boolean makeupDetected) {
  public static FaceChecksData from(FaceChecks checks) {
    return new FaceChecksData(
        checks.isLighting(),
        checks.isDistance(),
        checks.isFrontal(),
        checks.isUnobstructed(),
        checks.isMakeupDetected());
  }
}
