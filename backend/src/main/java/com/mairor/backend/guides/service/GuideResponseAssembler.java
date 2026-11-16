package com.mairor.backend.guides.service;

import com.mairor.backend.guides.dto.response.GuideResponse;
import com.mairor.backend.guides.dto.response.GuideStepResponse;
import com.mairor.backend.guides.dto.response.GuideStepResponse.StepType;
import com.mairor.backend.guides.dto.response.ReferenceProductResponse;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.videos.entity.Video;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.JsonNodeFactory;

/** 가이드와 연관 데이터를 API 응답으로 조립한다. */
@Component
class GuideResponseAssembler {

  private static final String EXCLUDED_MAKEUP = "other";
  private static final Set<String> PREVIEWABLE =
      Set.of("eyeshadow", "eyeliner", "blush", "highlight", "lip");

  private final ObjectMapper objectMapper;

  GuideResponseAssembler(ObjectMapper objectMapper) {
    this.objectMapper = objectMapper;
  }

  GuideResponse assemble(Guide guide, List<GuideStepProductLink> productLinks) {
    Video video = guide.getVideo();
    JsonNode input = read(guide.getGuideInput());
    Map<String, JsonNode> explained = byStepId(read(guide.getExplanation()));
    JsonNode area = read(guide.getArea());
    Map<String, JsonNode> areas = byStepId(area);
    Map<String, GuideStepProductLink> linksByStep = new HashMap<>();
    for (GuideStepProductLink link : productLinks) {
      linksByStep.put(link.getStepId(), link);
    }

    List<GuideStepResponse> steps = new ArrayList<>();
    for (JsonNode step : input.path("steps")) {
      String stepId = step.path("stepId").asString("");
      steps.add(step(step, explained.get(stepId), areas.get(stepId), linksByStep.get(stepId)));
    }
    int stepCount = (int) steps.stream().filter(step -> step.type() == StepType.GUIDE).count();
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
    String makeup = step.path("makeup").asString("");
    StepType type = EXCLUDED_MAKEUP.equals(makeup) ? StepType.EXCLUDED : StepType.GUIDE;
    JsonNode facts = step.path("facts");
    String tool = text(facts.path("tool").path("value"));
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
        type == StepType.GUIDE && PREVIEWABLE.contains(makeup),
        type == StepType.GUIDE ? GuideQueryService.MATCH_CATEGORY.get(makeup) : null,
        arrayOrEmpty(area == null ? null : area.get("subSteps")));
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
