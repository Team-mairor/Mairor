package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.Product;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** 카탈로그 제품과 호수 목록 (명세 Product). 검색 결과 항목과 상세 조회 응답이 같은 모양이다. */
public record ProductResponse(
    @Schema(description = "제품 ID. 파우치 등록에 보낸다", example = "00000000-0000-4000-8000-000000000101")
        String productId,
    @Schema(description = "브랜드 (카탈로그 원문)", example = "Mairor Sample") String brand,
    @Schema(description = "제품명 (카탈로그 원문)", example = "Water Gel Tint") String name,
    @Schema(description = "카테고리 코드", example = "LIP") String category,
    @Schema(description = "종류 코드", example = "LIP_TINT") String type,
    @ArraySchema(arraySchema = @Schema(description = "호수 목록. 표시 순서대로 오며, 등록된 호수가 없으면 빈 목록"))
        List<ShadeResponse> shades) {

  /** 호수는 제품 컬렉션을 건드리지 않도록 따로 읽은 정렬된 목록을 받는다. */
  public static ProductResponse of(Product product, List<ShadeResponse> shades) {
    return new ProductResponse(
        product.getId().toString(),
        product.getBrand(),
        product.getName(),
        product.getCategory().getCode(),
        product.getType().getCode(),
        List.copyOf(shades));
  }
}
