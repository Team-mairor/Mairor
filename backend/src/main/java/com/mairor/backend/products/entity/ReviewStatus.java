package com.mairor.backend.products.entity;

/**
 * 색 칸의 색을 서비스에 써도 되는지. 사람의 승인을 기다리는 단계는 없고, 자동 판정({@link #AUTO_APPROVED}·{@link
 * #BELOW_THRESHOLD})만으로 서비스가 돈다. {@link #APPROVED}·{@link #REJECTED}는 잘못된 자동 결과를 고치는 운영 정정 결과다.
 */
public enum ReviewStatus {
  /** 자동 기준을 통과해 서비스에 쓴다. */
  AUTO_APPROVED(true),
  /** 근거가 부족하거나 품질이 미달이다. 값은 내부에 보관하고 서비스에는 쓰지 않는다. */
  BELOW_THRESHOLD(false),
  /** 운영 정정으로 쓰기로 했다. */
  APPROVED(true),
  /** 운영 정정으로 쓰지 않기로 했다. 값은 내부에 보관한다. */
  REJECTED(false);

  private final boolean usable;

  ReviewStatus(boolean usable) {
    this.usable = usable;
  }

  /** API 가 {@code color}를 채우는 상태인가. */
  public boolean isUsable() {
    return usable;
  }

  /** 운영 정정 값이면 수집이 덮어쓰지 않는다. */
  public boolean isOperatorDecision() {
    return this == APPROVED || this == REJECTED;
  }
}
