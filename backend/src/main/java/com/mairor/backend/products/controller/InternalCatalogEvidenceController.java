package com.mairor.backend.products.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.products.dto.response.CatalogColorEvidenceResponse;
import com.mairor.backend.products.imports.CatalogEvidenceService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 색 칸의 근거 조회(내부). 공유 토큰 헤더({@code X-Internal-Token})로 지킨다. */
@Tag(
    name = "운영 · 화장품 색 근거",
    description = "색 칸의 현재 값이 어떤 근거에서 나왔는지 실행 결과 파일에서 찾아 준다. 공유 토큰 헤더(X-Internal-Token)가 필요하다.")
@RestController
@RequestMapping("/v1/internal/catalog/shade-colors")
public class InternalCatalogEvidenceController {

  private final CatalogEvidenceService evidenceService;

  public InternalCatalogEvidenceController(CatalogEvidenceService evidenceService) {
    this.evidenceService = evidenceService;
  }

  @Operation(
      summary = "색 칸의 근거 조회",
      description =
          """
          색 칸의 현재 값을 만든 적재 건을 따라가 실행 결과 파일에서 그 칸의 근거(이미지 URL, 영역, 방법, 품질 점수)를 돌려준다.

          - 근거는 DB 가 아니라 파일에 있다. 보관 기간이 지나 파일이 없으면 fileAvailable 이 false 이고 evidence 는 비어 있다.
          - 직접 넣은 칸처럼 적재가 만들지 않은 칸은 찾아갈 키가 없어 404 이다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "200",
      description = "칸의 근거 키와 근거 기록.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogColorEvidenceResponse.class)))
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(
      responseCode = "404",
      description = "칸이 없거나 근거를 찾아갈 키가 없다. (COLOR_NOT_FOUND, COLOR_EVIDENCE_NOT_RECORDED)")
  @GetMapping("/{colorId}/evidence")
  public CatalogColorEvidenceResponse evidence(@PathVariable UUID colorId) {
    return CatalogColorEvidenceResponse.from(evidenceService.find(colorId));
  }
}
