package com.mairor.backend.analysis.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import tools.jackson.databind.JsonNode;

/**
 * AI 서버 가이드 생성 콜백({@code shared/guide-job/guide_job_callback.v1.schema.json}). 상태 조회 응답도 같은 칸을 쓴다.
 * {@code guide}·{@code area}는 받은 그대로 저장하므로 JSON 노드로 받는다.
 */
public record AiGuideJobCallbackRequest(
    @Schema(
            description = "AI 작업 ID(가이드 생성 요청의 202 응답)",
            example = "8728c83b0d124c74a23863a50d4d7c0c")
        String jobId,
    @Schema(description = "유튜브 영상 ID", example = "VxAXD6PP76I") String videoId,
    @Schema(description = "COMPLETED 또는 FAILED", example = "COMPLETED") String status,
    @Schema(description = "쉬운 설명(steps[]). COMPLETED 일 때만", type = "object") JsonNode guide,
    @Schema(description = "가이드 영역(shared/guide-area). 프레임 없이 맡긴 작업이면 null", type = "object")
        JsonNode area,
    @Schema(description = "실패 원인 {code, message, details}. FAILED 일 때만", type = "object")
        JsonNode error) {}
