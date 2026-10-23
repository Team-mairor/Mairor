package com.mairor.backend.guides;

import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.common.web.PageResponse;
import org.springframework.stereotype.Service;

/** 검수된 가이드 조회. 가이드 테이블이 생기기 전까지는 빈 목록을 돌려주는 골격이다 (구현은 4A-4). */
@Service
public class GuideQueryService {

  public PageResponse<GuideSummaryResponse> findApproved(PageQuery query) {
    return PageResponse.empty(query);
  }
}
