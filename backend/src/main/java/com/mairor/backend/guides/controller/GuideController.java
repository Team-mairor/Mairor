package com.mairor.backend.guides.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.guides.dto.response.GuideResponse;
import com.mairor.backend.guides.service.GuideQueryService;
import com.mairor.backend.guides.service.GuideReferenceLinkRefresher;
import com.mairor.backend.users.controller.AuthApiDocs;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 튜토리얼이 보는 가이드(API-ANALYSIS-001). */
@Tag(name = "가이드", description = "검수 승인된 메이크업 가이드의 단계·쉬운 설명·가이드 영역.")
@RestController
@RequestMapping("/v1/guides")
public class GuideController {

  private final GuideQueryService guideQueryService;

  private final GuideReferenceLinkRefresher linkRefresher;

  public GuideController(
      GuideQueryService guideQueryService, GuideReferenceLinkRefresher linkRefresher) {
    this.guideQueryService = guideQueryService;
    this.linkRefresher = linkRefresher;
  }

  @Operation(
      summary = "가이드 조회",
      description =
          """
          검수 승인된 가이드의 단계별 요약·동작·도구·제품과 가이드 영역을 준다.

          - 영역은 shared/guide-area 의 하위 단계(subSteps)를 그대로 싣는다(명세 v2 의 application 대신).
          - type EXCLUDED 단계는 진행률·stepCount 에서 빠진다. 마스카라는 영역이 없어도 GUIDE 다.
          - 검수 전·반려·없는 가이드는 모두 404 다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(responseCode = "200", description = "가이드")
  @AuthApiDocs.Unauthorized
  @ApiResponse(responseCode = "404", description = "없거나 검수 승인 전인 가이드. (NOT_FOUND)")
  @GetMapping("/{guideId}")
  public GuideResponse get(@PathVariable UUID guideId) {
    GuideResponse response = guideQueryService.get(guideId);
    linkRefresher.refreshIfNeeded(guideId);
    return response;
  }
}
