package com.mairor.backend.executions.dto;

import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.entity.GuideExecution;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/** 내부 sessionId·저장소 key·기준 비교 버전은 응답에 노출하지 않는다. */
public record ExecutionResponse(
    UUID executionId,
    UUID guideId,
    int guideVersion,
    UUID matchId,
    UUID faceRegistrationId,
    ExecutionStatus status,
    @Schema(description = "사진 저장 응답 전에는 null이며 미동의로 취급", nullable = true) Boolean photoConsent,
    @Schema(description = "사진 동의 정책 버전. 동의 전에는 null", example = "v1", nullable = true)
        String consentPolicyVersion,
    Instant createdAt,
    @Schema(nullable = true) UUID recordId,
    @Schema(description = "시작 당시 GuideStep·MatchStep과 확정 선택을 합친 ExecutionStep 목록", type = "array")
        List<JsonNode> steps) {
  public static ExecutionResponse from(GuideExecution execution, List<JsonNode> steps) {
    return new ExecutionResponse(
        execution.getId(),
        execution.getGuideId(),
        execution.getGuideVersion(),
        execution.getMatchId(),
        execution.getFaceRegistrationId(),
        execution.getStatus(),
        execution.getPhotoConsent(),
        execution.getConsentPolicyVersion(),
        execution.getCreatedAt(),
        execution.getRecordId(),
        List.copyOf(steps));
  }
}
