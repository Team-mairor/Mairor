package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.collect.CollectResultService.Applied;
import com.mairor.backend.products.entity.CollectRequestStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

/** 수집 작업 결과를 반영한 뒤의 요청 상태. */
public record CollectJobResultResponse(
    @Schema(description = "수집 요청 ID(작업 ID)", example = "5f0c2a1e-8d3b-4c71-9a2e-1b7f3c9d4e10")
        UUID requestId,
    @Schema(description = "요청 상태: RESOLVED·UNRESOLVED·NOT_FOUND·FAILED", example = "RESOLVED")
        CollectRequestStatus status,
    @Schema(description = "해결되지 않은 사유", example = "SHADE_NOT_FOUND", nullable = true) String reason,
    @Schema(description = "이번 호출이 요청을 끝냈으면 true. 이미 끝난 요청이면 false", example = "true")
        boolean changed) {

  public static CollectJobResultResponse from(UUID requestId, Applied applied) {
    return new CollectJobResultResponse(
        requestId, applied.status(), applied.reason(), applied.changed());
  }
}
