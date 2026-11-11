package com.mairor.backend.executions.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;

public record PhotoConsentResponse(
    @Schema(example = "true") boolean enabled,
    @Schema(example = "v1") String policyVersion,
    @Schema(example = "2026-11-10T00:00:00Z") Instant consentedAt) {}
