package com.mairor.backend.videos.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import com.mairor.backend.videos.dto.VideoSearchPage;
import com.mairor.backend.videos.dto.VideoSelection;
import com.mairor.backend.videos.dto.VideoSelectionRequest;
import com.mairor.backend.videos.service.VideoSearchService;
import com.mairor.backend.videos.service.VideoSelectionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 영상 입력: YouTube 메이크업 영상 검색(API-VIDEO-004)과 선택(API-VIDEO-001). */
@Tag(name = "영상", description = "YouTube 메이크업 영상 검색과 영상 선택(챕터 · 가이드 유무 · 진행 중 분석).")
@RestController
@RequestMapping("/v1/videos")
public class VideoController {

  private final VideoSearchService searchService;
  private final VideoSelectionService selectionService;

  public VideoController(VideoSearchService searchService, VideoSelectionService selectionService) {
    this.searchService = searchService;
    this.selectionService = selectionService;
  }

  @Operation(
      summary = "영상 검색",
      description =
          """
          YouTube 에서 크리에이티브 커먼즈(CC BY) 영상을 관련도순으로 찾는다.
          - 분석할 수 없는 영상(연령 제한 · 라이브)은 빼서 size 보다 적게 올 수 있다.
          - 다음 페이지는 nextPageToken 으로 받는다. 검색어를 바꾸면 pageToken 을 빼고 다시 부른다.
          - 검색을 쓸 수 없을 때 빈 결과나 다른 목록으로 대신하지 않는다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(responseCode = "200", description = "검색 결과 한 페이지")
  @ApiResponse(
      responseCode = "400",
      description = "검색어가 비었거나 너무 길다, size 가 범위 밖이다. (VALIDATION_FAILED)")
  @AuthApiDocs.Unauthorized
  @ApiResponse(responseCode = "502", description = "YouTube 가 답을 주지 못했다. (VIDEO_PROVIDER_ERROR)")
  @ApiResponse(
      responseCode = "503",
      description = "검색 할당량을 다 썼거나 검색을 쓸 수 없다. (VIDEO_SEARCH_UNAVAILABLE)")
  @ApiResponse(responseCode = "504", description = "YouTube 응답이 늦다. (VIDEO_PROVIDER_TIMEOUT)")
  @GetMapping(path = "/search", produces = MediaType.APPLICATION_JSON_VALUE)
  public VideoSearchPage search(
      @Parameter(description = "검색어(공백을 뺀 1~100자)", example = "데일리 메이크업")
          @RequestParam(required = false)
          String q,
      @Parameter(description = "다음 페이지 토큰. 첫 페이지는 비운다", example = "CBQQAA")
          @RequestParam(required = false)
          String pageToken,
      @Parameter(description = "한 페이지 개수(1~50, 기본 20)", example = "20")
          @RequestParam(required = false)
          Integer size) {
    return searchService.search(q, pageToken, size);
  }

  @Operation(
      summary = "영상 선택",
      description =
          """
          고른 영상의 메타 · 챕터와 가이드 유무, 내가 요청해 진행 중인 분석을 준다.
          - YouTube 에서 공개 여부 · 라이선스를 다시 확인한다. 분석은 만들지 않는다(API-VIDEO-002).
          - 없거나 비공개 · 삭제 · 연령 제한 · 라이브 · CC BY 가 아닌 영상은 409 다(YouTube 가 없음 · 비공개 · 삭제를 구분해 주지 않는다).
          """,
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "200", description = "고른 영상(처음 고른 영상도 200)")
  @ApiResponse(responseCode = "400", description = "YouTube 영상 ID 형식이 아니다. (VALIDATION_FAILED)")
  @AuthApiDocs.Unauthorized
  @ApiResponse(responseCode = "403", description = "X-CSRF-TOKEN 이 없거나 유효하지 않다. (CSRF_INVALID)")
  @ApiResponse(
      responseCode = "409",
      description = "분석할 수 없는 영상이다. (VIDEO_UNSUPPORTED_FOR_ANALYSIS)")
  @ApiResponse(responseCode = "502", description = "YouTube 가 답을 주지 못했다. (VIDEO_PROVIDER_ERROR)")
  @ApiResponse(responseCode = "504", description = "YouTube 응답이 늦다. (VIDEO_PROVIDER_TIMEOUT)")
  @PostMapping(
      consumes = MediaType.APPLICATION_JSON_VALUE,
      produces = MediaType.APPLICATION_JSON_VALUE)
  public VideoSelection select(
      @AuthenticationPrincipal AuthenticatedUser principal,
      @RequestBody VideoSelectionRequest request) {
    return selectionService.select(principal.userId(), request);
  }
}
