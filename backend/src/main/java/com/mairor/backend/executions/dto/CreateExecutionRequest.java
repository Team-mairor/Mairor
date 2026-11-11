package com.mairor.backend.executions.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;

public record CreateExecutionRequest(
    @NotNull UUID guideId,
    @NotNull UUID matchId,
    @NotNull UUID faceRegistrationId,
    @NotNull List<@NotNull @Valid StartSelection> selections,
    @NotNull Boolean acceptMissingProducts) {
  public record StartSelection(
      @NotBlank @Size(max = 200) @Schema(description = "가이드 단계 식별자", example = "lip") String stepId,
      @JsonProperty(value = "selectedPouchItemId", required = true)
          @Schema(description = "본인 파우치 항목 ID 또는 명시적 null(미선택). 색 칸은 서버가 확정한다.", nullable = true)
          UUID selectedPouchItemId) {}
}
