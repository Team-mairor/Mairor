package com.mairor.backend.guides.entity;

/**
 * 가이드 검수 상태. API 명세 v2 reviewStatus 와 같다. NOT_READY → (분석 완료 후) PENDING → APPROVED | REJECTED.
 * APPROVED 인 가이드만 사용자에게 보인다.
 */
public enum ReviewStatus {
  NOT_READY,
  PENDING,
  APPROVED,
  REJECTED
}
