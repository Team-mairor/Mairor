package com.mairor.backend.products.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.products.collect.CollectRequestQueryService;
import com.mairor.backend.products.collect.CollectResultService;
import com.mairor.backend.products.dto.request.CollectJobResultRequest;
import com.mairor.backend.products.dto.response.CollectJobResultResponse;
import com.mairor.backend.products.dto.response.CollectRequestResponse;
import com.mairor.backend.products.entity.CollectRequestStatus;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 화장품 수집 요청(내부): 수집 워커의 작업 결과와 운영 확인. 공유 토큰 헤더({@code X-Internal-Token})로 지킨다. */
@Tag(
    name = "운영 · 화장품 수집 요청",
    description =
        "DB 에 없는 화장품 수집 요청의 결과를 받고(수집 워커가 부른다) 요청 상태를 본다. 공유 토큰 헤더(X-Internal-Token)가 필요하다.")
@RestController
@RequestMapping("/v1/internal/catalog")
public class InternalCatalogCollectController {

  private final CollectResultService resultService;
  private final CollectRequestQueryService queryService;

  public InternalCatalogCollectController(
      CollectResultService resultService, CollectRequestQueryService queryService) {
    this.resultService = resultService;
    this.queryService = queryService;
  }

  @Operation(
      summary = "수집 작업 결과",
      description =
          """
          수집 워커가 수집·적재를 끝낸 작업의 결과로 수집 요청을 끝낸다.

          - COLLECTED 면 카탈로그를 다시 읽어 요청한 제품·호수가 생겼는지 판정한다. 제품을 찾았다는 것만으로 해결로 보지 않는다.
          - 이미 끝난 요청에 같은 결과가 다시 오면 바꾸지 않고 200 으로 답한다(changed=false).
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "200",
      description = "반영한 뒤의 요청 상태.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CollectJobResultResponse.class)))
  @ApiResponse(
      responseCode = "400",
      description = "본문 형식이 틀리거나 본문의 jobId 가 주소와 다르다. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "그런 수집 요청이 없다. (NOT_FOUND)")
  @PostMapping("/collect-jobs/{jobId}/result")
  public CollectJobResultResponse result(
      @Parameter(description = "수집 요청 ID(작업 ID)", example = "5f0c2a1e-8d3b-4c71-9a2e-1b7f3c9d4e10")
          @PathVariable
          UUID jobId,
      @Valid @RequestBody CollectJobResultRequest request) {
    return CollectJobResultResponse.from(jobId, resultService.apply(jobId, request));
  }

  @Operation(
      summary = "수집 요청 목록",
      description =
          """
          최근 화장품 수집 요청을 상태·사유와 요청한 회원의 자동 연결 결과와 함께 돌려준다.

          - status 를 주면 그 상태만 본다. 최근 요청부터 limit 개다.
          - 회원에게 보이지 않는 운영 확인용이다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "200",
      description = "최근 수집 요청.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              array =
                  @ArraySchema(schema = @Schema(implementation = CollectRequestResponse.class))))
  @ApiResponse(
      responseCode = "400",
      description = "status 가 알 수 없는 값이거나 limit 가 범위를 벗어난다. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @GetMapping("/collect-requests")
  public List<CollectRequestResponse> requests(
      @Parameter(description = "요청 상태. 없으면 모든 상태", example = "UNRESOLVED")
          @RequestParam(required = false)
          CollectRequestStatus status,
      @Parameter(description = "돌려줄 최대 개수(1~200)", example = "50")
          @RequestParam(defaultValue = "50")
          @Min(1)
          @Max(200)
          int limit) {
    return queryService.recent(status, limit);
  }
}
