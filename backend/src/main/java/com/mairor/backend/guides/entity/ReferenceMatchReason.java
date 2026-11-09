package com.mairor.backend.guides.entity;

/** 자동 대조가 멈춘 이유. NULL 은 해당 수준까지 연결되었거나 별도 사유가 없음을 뜻한다. */
public enum ReferenceMatchReason {
  PRODUCT_NOT_PROVIDED,
  PRODUCT_DATA_INCOMPLETE,
  CATEGORY_UNSUPPORTED,
  PRODUCT_NOT_FOUND,
  PRODUCT_AMBIGUOUS,
  SHADE_NOT_PROVIDED,
  SHADE_NOT_FOUND,
  SHADE_AMBIGUOUS,
  NO_COLOR_SLOTS,
  SLOT_UNIDENTIFIED,
  LINK_CONFLICT
}
