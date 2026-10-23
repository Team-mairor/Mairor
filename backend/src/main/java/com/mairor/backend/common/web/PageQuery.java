package com.mairor.backend.common.web;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

/**
 * 목록 API의 공통 쿼리 파라미터 {@code ?page=0&size=20}. 컨트롤러에서 {@code @Valid @ModelAttribute PageQuery}로 받는다.
 *
 * <p>규약(노션 API 명세): page는 0부터, size는 기본 20·최대 100. 범위를 벗어나면 400 VALIDATION_FAILED.
 */
public record PageQuery(
    @Min(value = 0, message = "0 이상이어야 합니다.") Integer page,
    @Min(value = 1, message = "1 이상이어야 합니다.") @Max(value = MAX_SIZE, message = "100 이하여야 합니다.")
        Integer size) {

  public static final int DEFAULT_SIZE = 20;
  public static final int MAX_SIZE = 100;

  public PageQuery {
    if (page == null) {
      page = 0;
    }
    if (size == null) {
      size = DEFAULT_SIZE;
    }
  }

  public static PageQuery first() {
    return new PageQuery(0, DEFAULT_SIZE);
  }

  public Pageable toPageable() {
    return PageRequest.of(page, size);
  }
}
