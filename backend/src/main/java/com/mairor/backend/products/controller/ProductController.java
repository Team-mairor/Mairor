package com.mairor.backend.products.controller;

import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.products.dto.request.ProductSearchQuery;
import com.mairor.backend.products.dto.response.ProductListResponse;
import com.mairor.backend.products.dto.response.ProductResponse;
import com.mairor.backend.products.service.ProductSearchService;
import com.mairor.backend.users.controller.AuthApiDocs;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 카탈로그 제품 검색(API-POUCH-001)과 상세 조회(API-POUCH-002). 로그인이 필요하며, 회원과 무관한 공용 데이터다.
 *
 * <p>검색은 형식 검사({@code @Valid})를 먼저 하고, 카테고리·종류 코드 확인은 서비스가 한다. 두 단계 모두 400 {@code
 * VALIDATION_FAILED} 와 {@code details} 로 응답한다.
 */
@Tag(name = "화장품 카탈로그", description = "화장품 카테고리·종류 목록과 제품 검색.")
@RestController
@RequestMapping("/v1/products")
public class ProductController {

  private final ProductSearchService productSearchService;

  public ProductController(ProductSearchService productSearchService) {
    this.productSearchService = productSearchService;
  }

  /** 제품 검색. */
  @Operation(
      summary = "제품 검색",
      description =
          """
          카테고리·종류·브랜드·제품명이 정확히 같은 카탈로그 제품과 호수를 찾는다.

          - 대소문자·공백 차이는 같은 이름으로 본다.
          - 결과는 0~1건이며, 없으면 빈 목록이다. 화면은 직접 입력으로 넘어간다.
          - 호수는 색 칸 목록(`colors`)을 가진다. 호수·칸이 없으면 빈 목록이고, 쓸 수 있는 색이 없는 칸의 `color`는 `null` 이다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "정확히 일치하는 제품. 없으면 빈 목록이다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ProductListResponse.class),
              examples = {
                @ExampleObject(name = "일치 1건", value = ProductApiDocs.PRODUCT_SEARCH),
                @ExampleObject(name = "일치 없음", value = ProductApiDocs.PRODUCT_SEARCH_EMPTY)
              }))
  @ApiResponse(
      responseCode = "400",
      description =
          "값이 비었거나 길다. 없는 카테고리(category), 없는 종류·다른 카테고리의 종류(type)도 같다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(
                      name = "VALIDATION_FAILED",
                      value = ProductApiDocs.TYPE_NOT_IN_CATEGORY)))
  @AuthApiDocs.Unauthorized
  @GetMapping
  public ProductListResponse search(
      @Valid @ParameterObject @ModelAttribute ProductSearchQuery query) {
    return new ProductListResponse(productSearchService.search(query));
  }

  /** 제품 상세. */
  @Operation(
      summary = "제품 상세",
      description =
          """
          제품 하나와 호수 목록을 준다.

          - 응답은 검색 결과 항목과 같은 모양이다.
          - 없는 제품이면 404 이며, 화면은 직접 입력으로 돌아간다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "제품과 호수 목록.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ProductResponse.class),
              examples = @ExampleObject(name = "제품 상세", value = ProductApiDocs.PRODUCT_DETAIL)))
  @ApiResponse(
      responseCode = "400",
      description = "productId 가 UUID 형식이 아니다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(
      responseCode = "404",
      description = "제품이 없다. (NOT_FOUND)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(name = "NOT_FOUND", value = ProductApiDocs.PRODUCT_NOT_FOUND)))
  @AuthApiDocs.Unauthorized
  @GetMapping("/{productId}")
  public ProductResponse get(
      @Parameter(description = "제품 ID", example = "00000000-0000-4000-8000-000000000101")
          @PathVariable
          UUID productId) {
    return productSearchService.get(productId);
  }
}
