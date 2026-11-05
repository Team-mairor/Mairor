package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** 제품의 호수 하나. 색은 호수 안의 색 칸 목록으로 준다. */
public record ShadeResponse(
    @Schema(description = "호수 ID. 파우치 등록에 보낸다", example = "00000000-0000-4000-8000-000000000201")
        String shadeId,
    @Schema(description = "호수명", example = "01 Coral") String name,
    @ArraySchema(
            arraySchema =
                @Schema(description = "색 칸 목록. 단색 호수는 칸 1개, 듀오·팔레트는 여러 개이며 칸 순서대로 온다. 칸이 없으면 빈 목록"))
        List<ShadeColorResponse> colors) {

  /** 색 칸은 호수 컬렉션을 건드리지 않도록 따로 읽은 정렬된 목록을 받는다. */
  public static ShadeResponse of(ProductShade shade, List<ProductShadeColor> colors) {
    return new ShadeResponse(
        shade.getId().toString(),
        shade.getName(),
        colors.stream().map(ShadeColorResponse::from).toList());
  }
}
