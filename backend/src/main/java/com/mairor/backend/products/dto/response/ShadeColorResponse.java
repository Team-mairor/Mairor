package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.ProductShadeColor;
import io.swagger.v3.oas.annotations.media.Schema;

/**
 * 호수의 색 칸 하나 (명세 ShadeColor). 듀오·팔레트는 칸이 여러 개이고, 단색 호수는 칸이 하나다.
 *
 * <p>{@code colorId}는 칸의 영구 식별자다. {@code color}는 서비스에 쓸 수 있는 색({@code AUTO_APPROVED}·{@code
 * APPROVED})일 때만 채우고, 색을 모르거나 품질 미달·정정으로 쓰지 않는 칸이면 {@code null}이다.
 */
public record ShadeColorResponse(
    @Schema(description = "색 칸 ID. 칸의 영구 식별자", example = "00000000-0000-4000-8000-000000000404")
        String colorId,
    @Schema(description = "칸 이름. 사이트 글자나 사진에 인쇄된 이름만. 없으면 null", nullable = true) String name,
    @Schema(description = "칸 표시 순서(1부터)", example = "1") int sortOrder,
    @Schema(description = "칸의 색. 쓸 수 있는 색이 없으면 null", nullable = true) ColorInfoResponse color) {

  public static ShadeColorResponse from(ProductShadeColor slot) {
    return new ShadeColorResponse(
        slot.getId().toString(),
        slot.getName(),
        slot.getSortOrder(),
        slot.hasUsableColor() ? ColorInfoResponse.ofCatalog(slot.getColor()) : null);
  }
}
