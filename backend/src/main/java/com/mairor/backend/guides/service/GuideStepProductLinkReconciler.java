package com.mairor.backend.guides.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 저장된 가이드 단계와 제품 링크를 대조하고, 더 구체적인 연결을 반영한다. */
@Service
public class GuideStepProductLinkReconciler {

  private final GuideRepository guides;
  private final GuideStepProductLinkRepository links;
  private final GuideProductMatcher matcher;
  private final ObjectMapper objectMapper;

  GuideStepProductLinkReconciler(
      GuideRepository guides,
      GuideStepProductLinkRepository links,
      GuideProductMatcher matcher,
      ObjectMapper objectMapper) {
    this.guides = guides;
    this.links = links;
    this.matcher = matcher;
    this.objectMapper = objectMapper;
  }

  /**
   * @return 바뀐 단계 링크 수
   */
  @Transactional
  public int reconcile(UUID guideId) {
    Guide guide =
        guides
            .findByIdForUpdate(guideId)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    JsonNode stepsNode = objectMapper.readTree(guide.getGuideInput()).path("steps");
    if (!stepsNode.isArray()) {
      throw new IllegalStateException("가이드 입력의 steps 가 배열이 아니다: " + guideId);
    }

    Map<String, GuideStepProductLink> existingByStep = new LinkedHashMap<>();
    for (GuideStepProductLink link : links.findByGuideIdOrderByStepIdAsc(guideId)) {
      existingByStep.put(link.getStepId(), link);
    }

    boolean changed = false;
    int changedCount = 0;
    for (JsonNode step : stepsNode) {
      String stepId = text(step.path("stepId"));
      if (stepId == null) {
        throw new IllegalStateException("가이드 단계에 stepId 가 없다: " + guideId);
      }
      GuideProductMatcher.Candidate candidate = matcher.match(step);
      GuideStepProductLink existing = existingByStep.get(stepId);
      if (existing == null) {
        links.save(
            new GuideStepProductLink(
                guide,
                stepId,
                candidate.product(),
                candidate.shade(),
                candidate.color(),
                candidate.level(),
                candidate.reason()));
        changed = true;
        changedCount++;
      } else if (existing.reconcile(
          candidate.product(), candidate.shade(), candidate.color(), candidate.reason())) {
        changed = true;
        changedCount++;
      }
    }

    if (changed) {
      guide.incrementReferenceVersion();
    }
    return changedCount;
  }

  private static String text(JsonNode value) {
    if (value == null || !value.isString()) {
      return null;
    }
    String result = value.asString().trim();
    return result.isEmpty() ? null : result;
  }
}
