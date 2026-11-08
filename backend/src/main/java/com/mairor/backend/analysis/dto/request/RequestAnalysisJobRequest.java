package com.mairor.backend.analysis.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;

/** 회원 분석 요청 본문(API-VIDEO-002). 형식 검사는 서비스가 해서 오류 칸을 {@code videoId}로 준다. */
public record RequestAnalysisJobRequest(
    @Schema(
            description = "내부 영상 ID. 영상 선택(POST /v1/videos) 응답의 videoId",
            example = "7d3e2a1b-6c5f-4e8d-9a0b-2c3d4e5f6a7b",
            requiredMode = Schema.RequiredMode.REQUIRED)
        String videoId) {}
