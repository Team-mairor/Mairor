package com.mairor.backend.guides.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.dto.response.GuideResponse;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 검수 승인된 가이드를 API 응답으로 조회한다. */
@Service
public class GuideQueryService {

  /** 화장 종류 → 제품 매칭 카테고리(product_categories 시드). other 는 없음. */
  static final Map<String, String> MATCH_CATEGORY =
      Map.of(
          "foundation", "BASE",
          "eyeshadow", "EYE",
          "eyeliner", "EYE",
          "mascara", "EYE",
          "brow", "BROW",
          "blush", "CHEEK",
          "highlight", "CHEEK",
          "contour", "CHEEK",
          "lip", "LIP");

  private final GuideRepository guides;
  private final GuideStepProductLinkRepository productLinks;
  private final GuideResponseAssembler assembler;

  GuideQueryService(
      GuideRepository guides,
      GuideStepProductLinkRepository productLinks,
      GuideResponseAssembler assembler) {
    this.guides = guides;
    this.productLinks = productLinks;
    this.assembler = assembler;
  }

  /**
   * @throws BusinessException NOT_FOUND — 없거나 검수 승인 전·반려(사용자에게는 같은 404)
   */
  @Transactional(readOnly = true)
  public GuideResponse get(UUID guideId) {
    Guide guide =
        guides
            .findById(guideId)
            .filter(value -> value.getReviewStatus() == ReviewStatus.APPROVED)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    return assembler.assemble(guide, productLinks.findByGuideIdOrderByStepIdAsc(guideId));
  }
}
