package com.mairor.backend.products.imports;

import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import com.mairor.backend.products.entity.ProductShade;
import org.springframework.stereotype.Component;

/** 가이드 원본 제품 연결이 가리키는 색 칸을 카탈로그 정리 과정에서 삭제하지 않도록 보호한다. */
@Component
class GuideColorReferenceChecker implements ColorReferenceChecker {

  private final GuideStepProductLinkRepository links;

  GuideColorReferenceChecker(GuideStepProductLinkRepository links) {
    this.links = links;
  }

  @Override
  public boolean hasReferences(ProductShade shade) {
    return links.existsColorReferenceByShadeId(shade.getId());
  }
}
