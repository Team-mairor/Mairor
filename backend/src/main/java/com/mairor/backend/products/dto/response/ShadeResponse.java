package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.ProductShade;
import io.swagger.v3.oas.annotations.media.Schema;

/** 제품의 호수 하나. */
public record ShadeResponse(
    @Schema(description = "호수 ID. 파우치 등록에 보낸다", example = "00000000-0000-4000-8000-000000000201")
        String shadeId,
    @Schema(description = "호수명", example = "01 Coral") String name,
    @Schema(description = "대표 색상. 모르면 null", nullable = true) ColorInfoResponse color) {

  public static ShadeResponse from(ProductShade shade) {
    return new ShadeResponse(
        shade.getId().toString(), shade.getName(), ColorInfoResponse.ofCatalog(shade.getColor()));
  }
}
