package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.ShadeColor;
import io.swagger.v3.oas.annotations.media.Schema;

/**
 * 대표 색상 (명세 ColorInfo). 색상을 모르면 이 객체 자체를 {@code null}로 응답한다.
 *
 * <p>카탈로그 색상의 {@code source}는 항상 {@code CATALOG}다. 저장된 내부 출처값(예: 크롤링 출처명)은 내보내지 않는다.
 */
public record ColorInfoResponse(
    @Schema(description = "색 공간. 항상 sRGB", example = "sRGB") String colorSpace,
    @Schema(description = "#RRGGBB 대문자", example = "#F2665A") String hex,
    @Schema(description = "색상을 얻은 곳. 카탈로그 제품은 CATALOG", example = "CATALOG") String source,
    @Schema(description = "추정 색상인지 (실제 발색을 보장하지 않는다)", example = "false") boolean estimated) {

  public static final String SRGB = "sRGB";
  public static final String CATALOG = "CATALOG";

  /** 카탈로그 호수 색상. 색상이 없으면 {@code null}. */
  public static ColorInfoResponse ofCatalog(ShadeColor color) {
    if (color == null) {
      return null;
    }
    return new ColorInfoResponse(SRGB, color.getHex(), CATALOG, color.isEstimated());
  }
}
