package com.mairor.backend.analysis.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;

/** 노트북 진행 알림 본문. */
public record ProcessorProgressRequest(
    @Schema(
            description = "지금 단계. LOADING_VIDEO · EXTRACTING_STEPS · SEGMENTING",
            example = "EXTRACTING_STEPS")
        String stage,
    @Schema(description = "단계 안 진행률(0~100). 지금은 로그에만 남긴다", example = "40") Integer percent) {}
