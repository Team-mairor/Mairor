package com.mairor.backend.analysis.dto.response;

import com.mairor.backend.guides.dto.response.ReferenceProductResponse;
import io.swagger.v3.oas.annotations.media.Schema;

/** 분석 영상에서 단계별로 확인한 제품과 현재 회원 파우치의 보유 여부. */
public record FoundProductResponse(
    @Schema(nullable = true) String stepId,
    @Schema(description = "화장 종류 코드", nullable = true, example = "lip") String part,
    ReferenceProductResponse referenceProduct,
    @Schema(description = "조회 시점 파우치 보유 상태", example = "NOT_OWNED") Ownership ownership) {

  public enum Ownership {
    OWNED,
    NOT_OWNED,
    UNKNOWN
  }
}
