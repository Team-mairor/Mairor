package com.mairor.backend.guides.dto.request;

import com.mairor.backend.guides.service.GuideReviewService;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

/** 가이드 검수 결정. */
public record ReviewGuideRequest(
    @Schema(description = "검수 결과. 반려하면 공개 가이드도 내려간다", example = "REJECTED") @NotNull
        GuideReviewService.Decision decision) {}
