package com.mairor.backend.common.web;

import jakarta.validation.Valid;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 테스트 전용: 목록 API 본보기. 실제 목록 API도 이 모양으로 만든다. 페이지 파라미터는 {@link PageQuery}로 받아 검증하고, 응답은 {@link
 * PageResponse}로 돌려주며, 검증 실패는 {@code GlobalExceptionHandler}가 400 {@code VALIDATION_FAILED}로 바꾼다.
 */
@RestController
@RequestMapping("/v1/page-probe")
@ConditionalOnProperty(name = "test.page-probe", havingValue = "true")
public class PageProbeController {

  record Item(String id) {}

  @GetMapping
  public PageResponse<Item> list(@Valid @ModelAttribute PageQuery query) {
    return PageResponse.empty(query);
  }
}
