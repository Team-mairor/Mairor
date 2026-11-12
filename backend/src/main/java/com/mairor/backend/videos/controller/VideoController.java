package com.mairor.backend.videos.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import com.mairor.backend.videos.dto.PopularVideoResponse;
import com.mairor.backend.videos.dto.VideoSearchPage;
import com.mairor.backend.videos.dto.VideoSelection;
import com.mairor.backend.videos.dto.VideoSelectionRequest;
import com.mairor.backend.videos.service.PopularVideoService;
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

/** 영상 입력: YouTube 메이크업 영상 검색(API-VIDEO-004), 선택(API-VIDEO-001), 서비스 안 인기 영상(API-VIDEO-005). */
@Tag(name = "영상", description = "YouTube 메이크업 영상 검색, 영상 선택(챕터 · 가이드 유무 · 진행 중 분석), 서비스 안 인기 영상.")
@RestController
@RequestMapping("/v1/videos")
public class VideoController {

  private final VideoSearchService searchService;
  private final VideoSelectionService selectionService;
  private final PopularVideoService popularService;

  public VideoController(
      VideoSearchService searchService,
      VideoSelectionService selectionService,
      PopularVideoService popularService) {
    this.searchService = searchService;
    this.selectionService = selectionService;
    this.popularService = popularService;
  }

  @Operation(
      summary = "영상 검색",
      description =
          """
          YouTube 에서 크리에이티브 커먼즈(CC BY) 메이크업 영상을 관련도순으로 찾는다.
          - 검색어에 메이크업 · makeup 이 없으면 앞에 "메이크업"을 붙여 찾는다. 분석할 수 없는 영상(연령 제한 · 라이브)은 빼서 size 보다 적게 올 수 있다.
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
      summary = "인기 영상 Top 4",
      description =
          """
          서비스 안에서 최근 많이 선택된 영상을 순위대로 최대 4개 준다(YouTube 인기 순위가 아니다).
          - 영상을 고른 서로 다른 회원 수로 센다. 같으면 마지막 선택이 늦은 영상이 앞이다.
          - 선택할 때 분석할 수 있던 영상만 센다(그 뒤 바뀐 영상은 분석 요청이 다시 확인한다). guideAvailable=false 영상도 들어온다.
          - 서버가 센 결과를 잠시 담아 두고 nextRefreshAt 이 지나면 다시 센다. 하나도 없을 때(503)는 담지 않는다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(responseCode = "200", description = "인기 영상 1~4개")
  @AuthApiDocs.Unauthorized
  @ApiResponse(responseCode = "503", description = "셀 선택 기록이 아직 없다. (VIDEO_POPULAR_UNAVAILABLE)")
  @GetMapping(path = "/popular", produces = MediaType.APPLICATION_JSON_VALUE)
  public PopularVideoResponse popular() {
    return popularService.popular();
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
