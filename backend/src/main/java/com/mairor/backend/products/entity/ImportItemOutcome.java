package com.mairor.backend.products.entity;

/**
 * 적재 실행의 건 하나가 어떻게 처리됐는지. 앞의 다섯은 {@code ImportPlan.Outcome}과 같은 제품 단위 판정이고, {@link #INVALID}·{@link
 * #FAILED}는 판정 전에 틀렸거나 처리 중 오류가 난 건이다.
 */
public enum ImportItemOutcome {
  /** 새 제품으로 반영했다. */
  NEW(true),
  /** 같은 출처·상품 번호의 기존 제품을 갱신했다. */
  UPDATE(true),
  /** 기존 제품이 더 최근에 수집돼 반영하지 않았다. */
  STALE(false),
  /** 다른 출처의 같은 제품이 있어 자동으로 합치지 않았다. */
  AMBIGUOUS(false),
  /** 카테고리·종류를 정할 수 없어 반영하지 않았다. */
  UNCLASSIFIED(false),
  /** 형식이 틀려 읽을 수 없었다. */
  INVALID(false),
  /** 처리 중 오류가 나서 그 건만 롤백했다. */
  FAILED(false);

  private final boolean applied;

  ImportItemOutcome(boolean applied) {
    this.applied = applied;
  }

  /** 제품을 카탈로그에 반영한 결과인가. */
  public boolean isApplied() {
    return applied;
  }
}
