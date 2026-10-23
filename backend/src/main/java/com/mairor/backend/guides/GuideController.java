package com.mairor.backend.guides;

import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.common.web.PageResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 가이드 API (API-ANALYSIS-002 검수 가이드 목록). 공통 템플릿 사용 예시이기도 하다: 페이지 파라미터는 {@link PageQuery}, 응답은 {@link
 * PageResponse}, 실패는 {@code GlobalExceptionHandler}가 처리한다.
 */
@RestController
@RequestMapping("/v1/guides")
public class GuideController {

  private final GuideQueryService guideQueryService;

  public GuideController(GuideQueryService guideQueryService) {
    this.guideQueryService = guideQueryService;
  }

  @GetMapping
  public PageResponse<GuideSummaryResponse> list(@Valid @ModelAttribute PageQuery query) {
    return guideQueryService.findApproved(query);
  }
}
