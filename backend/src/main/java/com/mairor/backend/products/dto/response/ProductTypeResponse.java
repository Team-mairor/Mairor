package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.ProductType;
import io.swagger.v3.oas.annotations.media.Schema;

/** 카테고리 안의 세부 종류 하나. */
public record ProductTypeResponse(
    @Schema(description = "종류 코드. 파우치 등록·제품 검색에 이 값을 보낸다", example = "CUSHION") String code,
    @Schema(description = "화면에 보여 줄 이름", example = "쿠션") String label) {

  public static ProductTypeResponse from(ProductType type) {
    return new ProductTypeResponse(type.getCode(), type.getLabel());
  }
}
