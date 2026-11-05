package com.mairor.backend.products.imports;

/**
 * 수집 상품의 카테고리·종류 확정 결과.
 *
 * @param categoryCode 카테고리 코드 (종류의 소속 카테고리)
 * @param typeCode 종류 코드
 * @param origin 어떻게 정했나
 */
public record TypeResolution(String categoryCode, String typeCode, Origin origin) {

  public enum Origin {
    /** 매핑표 {@code catalog/type-mapping.json} 으로 정했다. */
    MAPPING,
    /** 수집기가 보낸 힌트가 실제 종류이고 카테고리와 맞아서 받아들였다. */
    HINT
  }
}
