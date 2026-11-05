package com.mairor.backend.products.imports;

/**
 * 한 건을 처리하면서 일부만 반영하거나 기존 값을 지킨 사유. 서비스는 그대로 돌고 운영 확인용으로 기록한다. 사람의 처리를 기다리는 상태가 아니다. 하나라도 있으면 그 건은
 * 부분 반영이다.
 */
public enum ImportReason {
  /** 같은 이름의 기존 호수가 있는데 옵션 값이 달라 같은 호수인지 알 수 없다. 그 호수는 반영하지 않는다. */
  SHADE_AMBIGUOUS,
  /** 비교 키가 같은 옵션이지만 구분 정보가 다르거나 없어서 한 호수로 합치지 않고 따로 둔다. */
  SHADE_MERGE_HELD,
  /** 같은 제품 안에서 호수 이름(비교용 키)이 겹쳐 저장할 수 없다. 뒤에 온 호수는 반영하지 않는다. */
  SHADE_NAME_CONFLICT,
  /** 기존 칸과 새 칸의 대응을 확인할 수 없다. 기존 칸·색·colorId 를 그대로 쓰고 새 칸 구성은 반영하지 않는다. */
  SHADE_LAYOUT_CHANGED,
  /** 쓰던 색을 더 좋거나 더 최신인 새 색으로 바꿨다. 정상 반영이라 부분 반영으로 세지 않는다. */
  COLOR_REPLACED,
  /** 새 색이 통과하지 못했거나 우선순위가 낮아 기존 색을 유지했다. */
  COLOR_KEPT_BETTER,
  /** 운영 정정 값이라 덮지 않았다. */
  COLOR_KEPT_OPERATOR,
  /** 수집이 실패해서 기존 색을 지우지 않았다. */
  COLOR_KEPT_ON_FAILURE,
  /** 근거가 되는 이미지나 값을 못 찾아 기존 색을 유지했다. */
  COLOR_KEPT_NOT_FOUND,
  /** 기존 색이 더 최근에 수집된 것이라 유지했다. */
  COLOR_KEPT_STALE,
  /** 이미 있는 제품의 종류가 새 수집과 달라 종류는 바꾸지 않았다. */
  TYPE_KEPT,
  /** 쓰던 색이 현재 정책으로는 서비스에 쓸 수 없게 돼 사용 불가로 내렸다. 값은 남긴다. 정책을 따른 정상 반영이라 부분 반영으로 세지 않는다. */
  COLOR_DOWNGRADED,
  /** 갱신할 제품 이름이 같은 종류의 다른 제품과 겹쳐 이 건을 반영하지 않는다. */
  PRODUCT_NAME_CONFLICT;

  /** 새 수집의 일부를 반영하지 않았다는 뜻인가. 색 교체와 정책에 따른 사용 불가 전환은 정상 반영이다. */
  public boolean isPartial() {
    return this != COLOR_REPLACED && this != COLOR_DOWNGRADED;
  }
}
