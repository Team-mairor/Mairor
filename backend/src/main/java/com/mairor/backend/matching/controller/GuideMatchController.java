package com.mairor.backend.matching.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.matching.dto.CreateGuideMatchRequest;
import com.mairor.backend.matching.dto.GuideMatchDetailResponse;
import com.mairor.backend.matching.dto.GuideMatchResponse;
import com.mairor.backend.matching.service.GuideMatchGenerationService;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 내 가이드 매칭 생성(API-RECOMMEND-001). */
@Tag(name = "가이드 매칭", description = "승인된 가이드와 로그인 회원의 파우치를 매칭해 스냅샷을 만든다.")
@RestController
@RequestMapping("/v1/users/me/guide-matches")
public class GuideMatchController {

  private final GuideMatchGenerationService generation;

  public GuideMatchController(GuideMatchGenerationService generation) {
    this.generation = generation;
  }

  @Operation(
      summary = "가이드 매칭 생성",
      description = "승인된 가이드의 단계와 내 파우치 제품을 매칭해 생성 시점 스냅샷을 저장한다." + " 카탈로그 데이터를 생성·수정하거나 수집하지 않는다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "201", description = "생성된 매칭 스냅샷.")
  @ApiResponse(responseCode = "400", description = "guideId가 누락됐거나 형식이 잘못됐다.")
  @ApiResponse(responseCode = "404", description = "가이드가 없거나 승인 상태가 아니다.")
  @ApiResponse(responseCode = "403", description = "X-CSRF-TOKEN 이 없거나 유효하지 않다. (CSRF_INVALID)")
  @AuthApiDocs.Unauthorized
  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public GuideMatchResponse create(
      @AuthenticationPrincipal AuthenticatedUser principal,
      @Valid @RequestBody CreateGuideMatchRequest request) {
    return generation.create(principal.userId(), request);
  }

  @Operation(
      summary = "가이드 매칭 조회",
      description = "내 매칭의 저장 스냅샷을 반환하고 현재 가이드·파우치와 다르면 stale을 표시한다.",
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(responseCode = "200", description = "저장된 매칭 스냅샷과 stale 여부.")
  @ApiResponse(responseCode = "404", description = "매칭이 없거나 다른 회원 소유다.")
  @AuthApiDocs.Unauthorized
  @GetMapping("/{matchId}")
  public GuideMatchDetailResponse get(
      @AuthenticationPrincipal AuthenticatedUser principal, @PathVariable UUID matchId) {
    return generation.get(principal.userId(), matchId);
  }
}
