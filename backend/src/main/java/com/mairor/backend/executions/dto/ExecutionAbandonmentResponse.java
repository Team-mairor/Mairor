package com.mairor.backend.executions.dto;

import com.mairor.backend.executions.entity.ExecutionStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

public record ExecutionAbandonmentResponse(
    UUID executionId,
    @Schema(example = "ABANDONED") ExecutionStatus status,
    boolean cleanupPending) {}
