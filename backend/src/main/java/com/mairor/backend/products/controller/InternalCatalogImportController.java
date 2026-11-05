package com.mairor.backend.products.controller;

import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.products.dto.request.CatalogDryRunRequest;
import com.mairor.backend.products.dto.response.CatalogDryRunResponse;
import com.mairor.backend.products.imports.CatalogDryRunService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 화장품 카탈로그 수집(내부). 수집기(S15P31A306-293)가 보낸 데이터를 DB 에 넣기 전에 어떻게 판정될지 본다. 공유 토큰 헤더({@code
 * X-Internal-Token})로 지킨다.
 *
 * <p>실행 기록이 필요한 시작·묶음 전송·종료 입구는 적재 단계(S15P31A306-295)에서 같은 판정 위에 더한다.
 */
@Tag(
    name = "운영 · 화장품 카탈로그 수집",
    description = "수집기가 보낸 상품이 카탈로그에 어떻게 반영될지 미리 본다. 공유 토큰 헤더(X-Internal-Token)가 필요하다.")
@RestController
@RequestMapping("/v1/internal/catalog/import-runs")
public class InternalCatalogImportController {

  private final CatalogDryRunService dryRunService;

  public InternalCatalogImportController(CatalogDryRunService dryRunService) {
    this.dryRunService = dryRunService;
  }

  @Operation(
      summary = "수집 상품 판정 시험",
      description =
          """
          수집한 상품 1~100건이 카탈로그에 어떻게 반영될지 건마다 판정해서 돌려준다. 아무것도 저장하지 않는다.

          - 사전 판정이다. 호출 시점의 DB 기준이라 그 사이 다른 적재나 정정이 있으면 실제 결과가 달라질 수 있다.
          - 한 건이 틀려도 요청 전체는 실패하지 않는다. 그 건만 INVALID 로 사유와 함께 돌려주고 나머지는 판정한다.
          - 사진에서 얻은 색은 설정한 임계값을 넘어야 서비스에 쓴다. 임계값을 정하기 전에는 어떤 색도 쓰지 않는 것으로 판정한다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @io.swagger.v3.oas.annotations.parameters.RequestBody(
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogDryRunRequest.class),
              examples =
                  @ExampleObject(name = "수집 상품 1건", value = CatalogImportApiDocs.DRY_RUN_REQUEST)))
  @ApiResponse(
      responseCode = "200",
      description = "건별 판정. 요청 항목과 같은 순서.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogDryRunResponse.class),
              examples =
                  @ExampleObject(name = "판정 결과", value = CatalogImportApiDocs.DRY_RUN_RESPONSE)))
  @ApiResponse(
      responseCode = "400",
      description = "items 가 배열이 아니거나 비었거나 100건을 넘는다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(
                      name = "VALIDATION_FAILED",
                      value = CatalogImportApiDocs.ITEMS_TOO_MANY)))
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @PostMapping("/dry-run")
  public CatalogDryRunResponse dryRun(@RequestBody CatalogDryRunRequest request) {
    return dryRunService.dryRun(request);
  }
}
