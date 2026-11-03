package com.mairor.backend.guides.dto.request;

import com.mairor.backend.guides.service.GuideReviewService;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

/** 가이드 검수 결정. */
public record ReviewGuideRequest(
    @Schema(description = "검수 결과. 승인하면 이 영상의 공개 가이드가 된다", example = "APPROVED") @NotNull
        GuideReviewService.Decision decision) {}
