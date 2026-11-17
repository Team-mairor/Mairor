package com.mairor.backend.guides.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.dto.response.GuideResponse;
import com.mairor.backend.guides.dto.response.GuideStepResponse;
import com.mairor.backend.guides.dto.response.GuideStepResponse.StepType;
import com.mairor.backend.guides.dto.response.ReferenceProductResponse;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import com.mairor.backend.videos.entity.Video;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.JsonNodeFactory;

/**
 * API-ANALYSIS-001: 검수 승인된 가이드를 단계별로 합쳐 준다. 단계 목록·사실은 가이드 입력({@code guide_input}), 동작·끝내는 때는 AI 쉬운
 * 설명({@code explanation}), 영역은 AI 가이드 영역({@code area})에서 {@code stepId}로 찾는다.
 *
 * <p>단계 종류(현수 api-v2-application 요청 답): {@code other}는 EXCLUDED(진행률에서 빠짐), {@code mascara}는 영역이 없어도
 * GUIDE. 설명·영역이 없는 단계는 빈 목록·null 로 준다.
 */
@Service
public class GuideQueryService {

  /**
   * 미리보기(색 레이어)가 되는 화장 종류. API 명세 v2: 아이섀도·아이라이너·블러셔·하이라이터·립. 이 종류여도 AI 영역의 하위 단계가 없거나 모두 {@code
   * notApplicable}(컨실러 단계)이면 미리보기가 아니다(현수 요청, S15P31A306-533).
   */
  static final Set<String> PREVIEWABLE =
      Set.of("eyeshadow", "eyeliner", "blush", "highlight", "lip");

  private static final String NOT_APPLICABLE = "notApplicable";

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

  private static final String EXCLUDED_MAKEUP = "other";

  private final GuideRepository guides;
  private final GuideStepProductLinkRepository productLinks;
  private final ObjectMapper objectMapper;

  GuideQueryService(
      GuideRepository guides,
      GuideStepProductLinkRepository productLinks,
      ObjectMapper objectMapper) {
    this.guides = guides;
    this.productLinks = productLinks;
    this.objectMapper = objectMapper;
  }

  /**
   * @throws BusinessException NOT_FOUND — 없거나 검수 승인 전·반려(사용자에게는 같은 404)
   */
  @Transactional(readOnly = true)
  public GuideResponse get(UUID guideId) {
    Guide guide =
        guides
            .findById(guideId)
            .filter(g -> g.getReviewStatus() == ReviewStatus.APPROVED)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    Video video = guide.getVideo();
    JsonNode input = read(guide.getGuideInput());
    Map<String, JsonNode> explained = byStepId(read(guide.getExplanation()));
    JsonNode area = read(guide.getArea());
    Map<String, JsonNode> areas = byStepId(area);
    Map<String, GuideStepProductLink> linksByStep = new HashMap<>();
    for (GuideStepProductLink link : productLinks.findByGuideIdOrderByStepIdAsc(guideId)) {
      linksByStep.put(link.getStepId(), link);
    }

    List<GuideStepResponse> steps = new ArrayList<>();
    for (JsonNode step : input.path("steps")) {
      String stepId = step.path("stepId").asString("");
      steps.add(step(step, explained.get(stepId), areas.get(stepId), linksByStep.get(stepId)));
    }
    int stepCount = (int) steps.stream().filter(s -> s.type() == StepType.GUIDE).count();
    int previewable = (int) steps.stream().filter(GuideStepResponse::previewable).count();
    String meshVersion =
        area == null
            ? guide.getMeshVersion()
            : area.path("meshVersion").asString(guide.getMeshVersion());

    return new GuideResponse(
        guide.getId(),
        guide.getVersion(),
        video.getId(),
        video.getYoutubeVideoId(),
        video.getTitle(),
        video.getChannelTitle(),
        video.getThumbnailUrl(),
        meshVersion,
        null,
        stepCount,
        previewable,
        List.copyOf(steps));
  }

  private GuideStepResponse step(
      JsonNode step, JsonNode explanation, JsonNode area, GuideStepProductLink productLink) {
    String makeup = GuideStepMakeup.of(step);
    StepType type = EXCLUDED_MAKEUP.equals(makeup) ? StepType.EXCLUDED : StepType.GUIDE;
    JsonNode facts = step.path("facts");
    String tool = text(facts.path("tool").path("value"));
    JsonNode subSteps = arrayOrEmpty(area == null ? null : area.get("subSteps"));
    return new GuideStepResponse(
        step.path("stepId").asString(""),
        step.path("order").asInt(),
        type,
        makeup,
        text(step.path("partLabel")),
        text(step.path("summary")),
        arrayOrEmpty(explanation == null ? null : explanation.get("actions")),
        explanation == null ? null : text(explanation.path("doneWhen")),
        tool == null ? List.of() : List.of(tool),
        product(step.path("product"), productLink),
        null,
        new GuideStepResponse.VideoRange(
            step.path("startSeconds").asDouble(), step.path("endSeconds").asDouble()),
        type == StepType.GUIDE && PREVIEWABLE.contains(makeup) && hasApplicableArea(subSteps),
        type == StepType.GUIDE ? MATCH_CATEGORY.get(makeup) : null,
        subSteps);
  }

  /** 하위 단계가 하나라도 {@code notApplicable}이 아니면 true. 하위 단계가 없으면 false. */
  private static boolean hasApplicableArea(JsonNode subSteps) {
    for (JsonNode subStep : subSteps) {
      if (!NOT_APPLICABLE.equals(subStep.path("status").asString(""))) {
        return true;
      }
    }
    return false;
  }

  private static ReferenceProductResponse product(
      JsonNode product, GuideStepProductLink productLink) {
    if (!product.isObject()) {
      return null;
    }
    String brand = text(product.path("brand"));
    String name = text(product.path("name"));
    String shade = text(product.path("shade"));
    String fullName = brand == null ? name : name == null ? brand : brand + " " + name;
    boolean linkConflict =
        productLink != null && productLink.getReasonCode() == ReferenceMatchReason.LINK_CONFLICT;
    if (fullName == null && shade == null) {
      return null;
    }
    String productId =
        productLink == null || linkConflict || productLink.getProduct() == null
            ? null
            : productLink.getProduct().getId().toString();
    String shadeId =
        productLink == null
                || linkConflict
                || (productLink.getMatchLevel() != ReferenceMatchLevel.SHADE
                    && productLink.getMatchLevel() != ReferenceMatchLevel.SLOT)
            ? null
            : productLink.getShade().getId().toString();
    String matchStatus =
        productLink != null
                && productLink.getMatchLevel() == ReferenceMatchLevel.NONE
                && productLink.getReasonCode() == ReferenceMatchReason.PRODUCT_AMBIGUOUS
            ? "CANDIDATE"
            : productId == null ? "UNMATCHED" : "MATCHED";
    return new ReferenceProductResponse(
        productId, shadeId, fullName, shade, matchStatus, "UNKNOWN", List.of(), Boolean.TRUE);
  }

  private JsonNode read(String json) {
    return json == null ? null : objectMapper.readTree(json);
  }

  private static Map<String, JsonNode> byStepId(JsonNode root) {
    Map<String, JsonNode> result = new HashMap<>();
    if (root != null) {
      for (JsonNode step : root.path("steps")) {
        result.put(step.path("stepId").asString(""), step);
      }
    }
    return result;
  }

  private static JsonNode arrayOrEmpty(JsonNode node) {
    return node != null && node.isArray() ? node : JsonNodeFactory.instance.arrayNode();
  }

  private static String text(JsonNode node) {
    if (node == null || !node.isString()) {
      return null;
    }
    String value = node.asString().trim();
    return value.isEmpty() ? null : value;
  }
}
