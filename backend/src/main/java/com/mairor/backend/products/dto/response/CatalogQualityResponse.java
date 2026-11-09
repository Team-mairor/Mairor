package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.imports.CatalogImportStatsService.Counts;
import com.mairor.backend.products.imports.CatalogImportStatsService.Quality;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.Map;

/**
 * 지금 카탈로그의 색 품질. 어느 적재가 만들었는지와 상관없이 현재 저장된 색이 사용 가능, 기준 미달, 미확보 중 어디에 있는지 센다. 임계값을 바꾸거나 다시 수집하면 숫자가
 * 달라진다.
 */
public record CatalogQualityResponse(
    @Schema(description = "센 범위의 출처. 모든 출처면 null", example = "OFFICIAL:etude.com", nullable = true)
        String source,
    @Schema(description = "제품 수", example = "120") int products,
    @Schema(
            description =
                "호수 기준. 사용 가능=사용할 수 있는 칸이 하나라도 있음, 기준 미달=값은 있지만 모두 쓸 수 없음, 미확보=값이 있는 칸이 없음(칸이 없는 호수 포함)")
        CountsResponse shades,
    @Schema(description = "색 칸 기준. 사용 가능=서비스에 쓰는 색, 기준 미달=값은 있지만 쓰지 않음, 미확보=HEX 없음")
        CountsResponse slots,
    @Schema(description = "사용 가능한 색 칸의 색 출처별 개수. 많은 순") Map<String, Integer> usableBySource) {

  public static CatalogQualityResponse from(Quality quality) {
    return new CatalogQualityResponse(
        quality.source(),
        quality.products(),
        CountsResponse.from(quality.shades()),
        CountsResponse.from(quality.slots()),
        quality.usableBySource());
  }

  /** 개수와 비율. 비율은 전체가 0이면 null 이다. */
  public record CountsResponse(
      @Schema(description = "전체", example = "300") int total,
      @Schema(description = "사용 가능", example = "180") int usable,
      @Schema(description = "기준 미달", example = "60") int belowThreshold,
      @Schema(description = "색 미확보", example = "60") int withoutColor,
      @Schema(description = "사용 가능 비율(0~1, 소수 넷째 자리)", example = "0.6", nullable = true)
          Double usableRatio,
      @Schema(description = "기준 미달 비율", example = "0.2", nullable = true)
          Double belowThresholdRatio,
      @Schema(description = "색 미확보 비율", example = "0.2", nullable = true)
          Double withoutColorRatio) {

    static CountsResponse from(Counts counts) {
      return new CountsResponse(
          counts.total(),
          counts.usable(),
          counts.belowThreshold(),
          counts.withoutColor(),
          counts.usableRatio(),
          counts.belowThresholdRatio(),
          counts.withoutColorRatio());
    }
  }
}
