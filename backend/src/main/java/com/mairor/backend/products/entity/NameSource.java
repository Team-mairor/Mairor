package com.mairor.backend.products.entity;

/**
 * 색 칸 이름의 근거. 모델이나 수집기가 순서대로 센 번호는 이름이 아니다(순서는 {@code sortOrder}). 이름이 없으면 {@link #NONE}이고 이름도 없다.
 */
public enum NameSource {
  /** 사이트 글자에 적힌 이름·번호. */
  SITE_TEXT,
  /** 사진에 인쇄된 이름·번호를 읽었다. */
  IMAGE_PRINT,
  /** 이름이 없다. */
  NONE
}
