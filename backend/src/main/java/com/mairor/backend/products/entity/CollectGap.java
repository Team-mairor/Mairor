package com.mairor.backend.products.entity;

/**
 * 영상 분석 부족분 수집 요청이 채우려는 것(S15P31A306-518). 완료 조건이 다르다.
 *
 * <ul>
 *   <li>{@link #PRODUCT_MISSING}: 같은 카테고리에서 브랜드·제품명이 일치하는 제품이 정확히 하나 생긴다
 *   <li>{@link #SHADE_MISSING}: 대상 제품에 영상의 호수명과 일치하는 호수가 생긴다
 *   <li>{@link #COLOR_MISSING}: 대상 칸(또는 대상 호수의 해당 칸)에 쓸 수 있는 색이 생긴다
 * </ul>
 */
public enum CollectGap {
  PRODUCT_MISSING,
  SHADE_MISSING,
  COLOR_MISSING
}
