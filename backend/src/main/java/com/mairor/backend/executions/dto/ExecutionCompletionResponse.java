package com.mairor.backend.executions.dto;

import com.mairor.backend.executions.entity.ExecutionStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

public record ExecutionCompletionResponse(
    UUID executionId,
    @Schema(example = "COMPLETED") ExecutionStatus status,
    UUID recordId,
    Instant completedAt) {}
