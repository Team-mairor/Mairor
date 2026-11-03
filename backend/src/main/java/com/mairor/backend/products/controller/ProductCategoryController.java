package com.mairor.backend.products.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.products.dto.response.ProductCategoryListResponse;
import com.mairor.backend.products.service.ProductCategoryService;
import com.mairor.backend.users.controller.AuthApiDocs;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 화장품 카테고리·종류 목록 (API-POUCH-008). 로그인이 필요하며, 회원과 무관한 공용 데이터다. */
@Tag(name = "화장품 카탈로그", description = "화장품 카테고리·종류 목록과 제품 검색.")
@RestController
@RequestMapping("/v1/product-categories")
public class ProductCategoryController {

  /** 성공 응답 예시. 9개 중 형태가 다른 두 카테고리만 싣는다. */
  static final String CATEGORY_LIST =
      """
      {
        "items": [
          {
            "code": "BASE",
            "label": "베이스",
            "matchable": true,
            "shadeSelectable": true,
            "types": [
              {"code": "CUSHION", "label": "쿠션"},
              {"code": "FOUNDATION", "label": "파운데이션"}
            ],
            "compatibleParts": []
          },
          {
            "code": "FRAGRANCE",
            "label": "향수",
            "matchable": false,
            "shadeSelectable": false,
            "types": [{"code": "PERFUME", "label": "향수"}],
            "compatibleParts": []
          }
        ]
      }""";

  private final ProductCategoryService productCategoryService;

  public ProductCategoryController(ProductCategoryService productCategoryService) {
    this.productCategoryService = productCategoryService;
  }

  /** 카테고리·종류 목록. */
  @Operation(
      summary = "카테고리·종류 목록",
      description =
          """
          파우치 등록·수정에 쓰는 카테고리와 종류 코드를 준다.

          - 화면은 `label` 을 보여 주고, 저장·검색에는 `code` 를 보낸다.
          - 목록은 서버 데이터로 정해지므로 코드를 하드코딩하지 않는다.
          - 종류가 없는 카테고리는 `types` 가 빈 목록이다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "카테고리 전체. 표시 순서대로 온다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ProductCategoryListResponse.class),
              examples = @ExampleObject(name = "카테고리 목록", value = CATEGORY_LIST)))
  @AuthApiDocs.Unauthorized
  @GetMapping
  public ProductCategoryListResponse list() {
    return new ProductCategoryListResponse(productCategoryService.list());
  }
}
