package com.mairor.backend.guides.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.guides.dto.request.ReviewGuideRequest;
import com.mairor.backend.guides.dto.response.InternalGuideResponse;
import com.mairor.backend.guides.service.GuideReferenceLinkReconciliationDispatcher;
import com.mairor.backend.guides.service.GuideReviewService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 운영자 가이드 검수. AI 가이드는 저장되면 바로 공개되므로(S15P31A306-409) 운영자는 문제 가이드를 내릴 때 쓴다. 1차 MVP 는 운영자 계정 대신 공유 토큰
 * 헤더({@code X-Internal-Token})로 지킨다.
 */
@Tag(
    name = "운영 · 가이드 검수",
    description = "AI 가 만든 가이드를 보고, 문제가 있으면 내린다. 공유 토큰 헤더(X-Internal-Token)가 필요하다.")
@RestController
@RequestMapping("/v1/internal/guides")
public class InternalGuideController {

  private final GuideReviewService guideReviewService;
  private final GuideReferenceLinkReconciliationDispatcher reconciliationDispatcher;

  public InternalGuideController(
      GuideReviewService guideReviewService,
      GuideReferenceLinkReconciliationDispatcher reconciliationDispatcher) {
    this.guideReviewService = guideReviewService;
    this.reconciliationDispatcher = reconciliationDispatcher;
  }

  @Operation(
      summary = "가이드 조회",
      description =
          """
          검수할 가이드의 입력·쉬운 설명·영역과 검수 상태를 준다.

          - 가이드 ID 는 분석 작업 조회의 guideId 로 찾는다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(responseCode = "200", description = "가이드")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "없는 가이드. (NOT_FOUND)")
  @GetMapping("/{guideId}")
  public InternalGuideResponse get(@PathVariable UUID guideId) {
    return InternalGuideResponse.from(guideReviewService.get(guideId));
  }

  @Operation(
      summary = "가이드 검수",
      description =
          """
          가이드를 반려(내리기)하거나, 검수 대기로 남은 옛 가이드를 승인한다.

          - AI 가이드는 저장되면 바로 공개(APPROVED)된다. 반려하면 공개 가이드도 내려간다.
          - 승인은 검수 대기(PENDING)만, 반려는 검수 대기 · 공개만 된다. 아니면 409 다.
          - 승인하면 같은 영상의 이전 공개 가이드는 반려로 내려간다(공개는 영상당 하나).
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(responseCode = "200", description = "검수 뒤 가이드")
  @ApiResponse(responseCode = "400", description = "입력 형식 오류. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "없는 가이드. (NOT_FOUND)")
  @ApiResponse(responseCode = "409", description = "그 결정을 내릴 수 없는 검수 상태. (CONFLICT)")
  @PostMapping("/{guideId}/review")
  public InternalGuideResponse review(
      @PathVariable UUID guideId, @Valid @RequestBody ReviewGuideRequest request) {
    return InternalGuideResponse.from(guideReviewService.review(guideId, request.decision()));
  }

  @Operation(
      summary = "가이드 원본 제품 대조 재실행",
      description =
          """
          AI 콜백 후 가이드 원본 제품을 기존 카탈로그와 비동기로 다시 대조한다.

          - 202 응답은 대조 작업 예약 완료이며, 결과는 가이드 조회 API에서 확인한다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(responseCode = "202", description = "대조 작업 예약")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "없는 가이드. (NOT_FOUND)")
  @ApiResponse(responseCode = "503", description = "대조 작업 대기열을 사용할 수 없음. (SERVICE_UNAVAILABLE)")
  @PostMapping("/{guideId}/reference-links/reconcile")
  public ResponseEntity<Void> reconcileReferenceLinks(@PathVariable UUID guideId) {
    reconciliationDispatcher.requestManualReconciliation(guideId);
    return ResponseEntity.accepted().build();
  }
}
