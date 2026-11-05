package com.mairor.backend.products.entity;

/**
 * 색 칸의 HEX 를 어디서 얻었는지. 우선순위는 {@link #rank()}가 낮을수록 높다. 재수집 때 사용 조건을 통과한 더 높은 우선순위의 색이 나오면 낮은 것을
 * 교체하고, 낮은 우선순위는 높은 것을 덮지 못한다. 교체 판정 자체는 적재 코드가 한다.
 *
 * <p>{@link #SAMPLE}은 개발용 시드이고 우선순위가 가장 낮다.
 */
public enum ColorSource {
  /** 사이트가 호수에 직접 준 색값. */
  SOURCE_VALUE(1, true),
  /** 옵션 컬러칩 사진. */
  SWATCH_CHIP(2, true),
  /** 공식 홈 제품 사진. */
  PRODUCT_PHOTO(3, true),
  /** 공식 홈 밖 웹 사진. */
  WEB_PHOTO(4, true),
  /** 모델 추정. */
  LLM_ESTIMATE(5, true),
  /** 개발용 시드. */
  SAMPLE(99, false);

  private final int rank;
  private final boolean alwaysEstimated;

  ColorSource(int rank, boolean alwaysEstimated) {
    this.rank = rank;
    this.alwaysEstimated = alwaysEstimated;
  }

  /** 낮을수록 우선순위가 높다. */
  public int rank() {
    return rank;
  }

  /** 이 출처의 색은 항상 추정값({@code estimated=true})이다. 사람이 정정해도 같다. */
  public boolean isAlwaysEstimated() {
    return alwaysEstimated;
  }

  public boolean outranks(ColorSource other) {
    return rank < other.rank;
  }
}
