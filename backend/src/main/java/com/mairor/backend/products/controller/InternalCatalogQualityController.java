package com.mairor.backend.products.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.products.dto.response.CatalogQualityResponse;
import com.mairor.backend.products.imports.CatalogImportStatsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 화장품 카탈로그의 현재 색 품질(내부). 공유 토큰 헤더({@code X-Internal-Token})로 지킨다. */
@Tag(
    name = "운영 · 화장품 카탈로그 품질",
    description =
        "지금 카탈로그의 호수·색 칸이 사용 가능, 기준 미달, 색 미확보 중 어디에 있는지 센다. 공유 토큰 헤더(X-Internal-Token)가 필요하다.")
@RestController
@RequestMapping("/v1/internal/catalog/quality")
public class InternalCatalogQualityController {

  private final CatalogImportStatsService statsService;

  public InternalCatalogQualityController(CatalogImportStatsService statsService) {
    this.statsService = statsService;
  }

  @Operation(
      summary = "카탈로그 색 품질 통계",
      description =
          """
          지금 카탈로그의 호수와 색 칸을 사용 가능, 기준 미달, 색 미확보로 나눠 개수와 비율을 돌려준다.

          - 어느 적재가 만들었는지와 상관없는 현재 상태다. 임계값을 바꾸거나 다시 수집하면 달라진다.
          - source 를 주면 그 출처의 제품만 센다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "200",
      description = "현재 색 품질.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogQualityResponse.class)))
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @GetMapping
  public CatalogQualityResponse quality(
      @Parameter(
              description = "제품 출처(products.source 값 그대로). 없으면 모든 출처",
              example = "OFFICIAL:etude.com")
          @RequestParam(required = false)
          String source) {
    return CatalogQualityResponse.from(
        statsService.quality(source == null || source.isBlank() ? null : source));
  }
}
