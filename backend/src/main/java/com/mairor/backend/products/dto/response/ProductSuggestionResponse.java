package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.Product;
import io.swagger.v3.oas.annotations.media.Schema;

/** 제품 후보 한 건. 호수는 싣지 않는다. 고르면 제품 상세로 호수를 받는다. */
public record ProductSuggestionResponse(
    @Schema(description = "제품 ID. 제품 상세 조회에 쓴다", example = "00000000-0000-4000-8000-000000000101")
        String productId,
    @Schema(description = "브랜드 (카탈로그 원문)", example = "롬앤") String brand,
    @Schema(description = "제품명 (카탈로그 원문)", example = "블러 퍼지 틴트 #오리지널") String name,
    @Schema(description = "카테고리 코드", example = "LIP") String category,
    @Schema(description = "종류 코드", example = "LIP_TINT") String type) {

  public static ProductSuggestionResponse of(Product product) {
    return new ProductSuggestionResponse(
        product.getId().toString(),
        product.getBrand(),
        product.getName(),
        product.getCategory().getCode(),
        product.getType().getCode());
  }
}
