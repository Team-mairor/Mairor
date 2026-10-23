package com.mairor.backend.common.web;

import java.util.List;
import org.springframework.data.domain.Page;

/**
 * 목록 API의 공통 응답 {@code {items, page, size, hasNext}} (노션 API 명세). 전체 개수는 주지 않는다.
 *
 * @param <T> 항목 타입
 */
public record PageResponse<T>(List<T> items, int page, int size, boolean hasNext) {

  public PageResponse {
    items = items == null ? List.of() : List.copyOf(items);
  }

  public static <T> PageResponse<T> of(Page<T> page) {
    return new PageResponse<>(page.getContent(), page.getNumber(), page.getSize(), page.hasNext());
  }

  public static <T> PageResponse<T> of(List<T> items, PageQuery query, boolean hasNext) {
    return new PageResponse<>(items, query.page(), query.size(), hasNext);
  }

  public static <T> PageResponse<T> empty(PageQuery query) {
    return new PageResponse<>(List.of(), query.page(), query.size(), false);
  }
}
