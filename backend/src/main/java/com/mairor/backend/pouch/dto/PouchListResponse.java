package com.mairor.backend.pouch.dto;

import com.mairor.backend.common.web.PageResponse;
import java.util.List;

/** 내 파우치 목록과 페이지 메타데이터, 해당 조회 스냅샷의 버전. */
public record PouchListResponse(
    List<PouchItemResponse> items, int page, int size, boolean hasNext, long pouchVersion) {

  public PouchListResponse {
    items = items == null ? List.of() : List.copyOf(items);
  }

  public static PouchListResponse of(PageResponse<PouchItemResponse> page, long pouchVersion) {
    return new PouchListResponse(
        page.items(), page.page(), page.size(), page.hasNext(), pouchVersion);
  }
}
