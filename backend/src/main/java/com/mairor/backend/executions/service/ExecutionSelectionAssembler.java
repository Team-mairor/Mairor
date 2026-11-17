package com.mairor.backend.executions.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.executions.dto.CreateExecutionRequest.StartSelection;
import com.mairor.backend.guides.dto.response.GuideResponse;
import com.mairor.backend.guides.dto.response.GuideStepResponse;
import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.matching.service.PouchCandidateAssembler;
import com.mairor.backend.matching.service.PouchCompatibilityPolicy;
import com.mairor.backend.matching.service.RecommendationCandidateSelector;
import com.mairor.backend.matching.service.RecommendationCandidateSelector.Candidate;
import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 요청에서 색 칸을 받지 않는다. 저장 매칭의 추천 칸과 현재 검증된 수동 선택에서 스냅샷을 만든다. */
@Component
public class ExecutionSelectionAssembler {
  private final ObjectMapper mapper;
  private final PouchCandidateAssembler candidates;

  public ExecutionSelectionAssembler(ObjectMapper mapper, PouchCandidateAssembler candidates) {
    this.mapper = mapper;
    this.candidates = candidates;
  }

  /** 소유권은 stale/선택 정책 오류보다 먼저 검사해 타인 항목의 정보를 노출하지 않는다. */
  public void verifyOwnership(List<StartSelection> selections, Map<UUID, PouchItem> items) {
    for (StartSelection selection : selections) {
      if (selection.selectedPouchItemId() != null
          && !items.containsKey(selection.selectedPouchItemId())) {
        throw new BusinessException(ErrorCode.NOT_FOUND);
      }
    }
  }

  public List<PreparedStep> assemble(
      GuideResponse guide,
      JsonNode matchSnapshot,
      List<StartSelection> selections,
      Map<UUID, PouchItem> items,
      Map<UUID, ProductShade> shades,
      Map<String, GuideStepProductLink> links,
      boolean acceptMissingProducts) {
    List<GuideStepResponse> guideSteps =
        guide.steps().stream()
            .filter(step -> step.type() == GuideStepResponse.StepType.GUIDE)
            .sorted(
                Comparator.comparingInt(GuideStepResponse::order)
                    .thenComparing(GuideStepResponse::stepId))
            .toList();
    Map<String, StartSelection> byStep = new HashMap<>();
    for (StartSelection selection : selections) {
      if (byStep.putIfAbsent(selection.stepId(), selection) != null) {
        throw invalid();
      }
    }
    if (byStep.size() != guideSteps.size()
        || guideSteps.stream().anyMatch(step -> !byStep.containsKey(step.stepId()))) {
      throw invalid();
    }
    Map<String, JsonNode> matched = new HashMap<>();
    for (JsonNode step : matchSnapshot.path("steps")) {
      matched.put(step.path("stepId").asString(), step);
    }
    if (matched.size() != guideSteps.size()) {
      throw stale();
    }
    List<PreparedStep> result = new ArrayList<>();
    boolean missing = false;
    for (GuideStepResponse guideStep : guideSteps) {
      JsonNode matchStep = matched.get(guideStep.stepId());
      if (matchStep == null || !matchStep.isObject()) {
        throw stale();
      }
      ObjectNode snapshot = mapper.valueToTree(guideStep);
      snapshot.setAll((ObjectNode) matchStep.deepCopy());
      UUID selectedId = byStep.get(guideStep.stepId()).selectedPouchItemId();
      snapshot.putNull("photo");
      if (selectedId == null) {
        missing = true;
        if (!"NONE".equals(matchStep.path("result").asString())) {
          snapshot.put("noneReason", "NOT_SELECTED");
        }
        snapshot.put("result", "NONE");
        snapshot.putNull("selectedPouchItemId");
        snapshot.putNull("selectedProduct");
        snapshot.putNull("selectedColorId");
        snapshot.putNull("selectedColor");
        snapshot.put("skipped", true);
      } else {
        PouchItem item = items.get(selectedId);
        GuideStepProductLink link = links.get(guideStep.stepId());
        boolean same = isSame(item, link);
        Candidate candidate = candidates.assemble(item, shades);
        if (!same
            && (!PouchCompatibilityPolicy.supports(guideStep.part(), item.getType())
                || candidate.colors().isEmpty())) {
          throw invalid();
        }
        JsonNode reference = matchSnapshot.path("referenceColors").path(guideStep.stepId());
        SelectedColor selected =
            same ? sameColor(link) : substituteColor(item, candidate, matchStep, reference, shades);
        ObjectNode product = mapper.valueToTree(PouchItemResponse.from(item));
        if (selected.color() != null) {
          product.set("color", selected.color());
          product.put("colorSource", selected.color().path("source").asString());
        }
        snapshot.put("result", same ? "SAME" : "SUBSTITUTE");
        snapshot.putNull("noneReason");
        snapshot.put("selectedPouchItemId", selectedId.toString());
        snapshot.set("selectedProduct", product);
        if (selected.id() == null) {
          snapshot.putNull("selectedColorId");
        } else {
          snapshot.put("selectedColorId", selected.id().toString());
        }
        snapshot.set("selectedColor", selected.color());
        snapshot.put("skipped", false);
      }
      result.add(new PreparedStep(guideStep.stepId(), selectedId == null, snapshot));
    }
    if (missing && !acceptMissingProducts) {
      throw new BusinessException(
          HttpStatus.CONFLICT, "GUIDE_MISSING_PRODUCTS_NOT_ACKNOWLEDGED", "제품 없이 진행할 단계를 확인해 주세요.");
    }
    return List.copyOf(result);
  }

  private SelectedColor substituteColor(
      PouchItem item,
      Candidate candidate,
      JsonNode matchStep,
      JsonNode reference,
      Map<UUID, ProductShade> shades) {
    if (!reference.isObject() || reference.path("hex").asString("").isBlank()) {
      return new SelectedColor(null, null);
    }
    for (JsonNode saved : matchStep.path("candidates")) {
      if (item.getId().toString().equals(saved.path("pouchItemId").asString())) {
        UUID colorId =
            saved.path("matchedColorId").isString()
                ? UUID.fromString(saved.path("matchedColorId").asString())
                : null;
        JsonNode color = saved.path("product").path("color");
        if (!color.isObject()
            || candidate.colors().stream()
                .noneMatch(
                    option ->
                        java.util.Objects.equals(option.colorId(), colorId)
                            && option.hex().equals(color.path("hex").asString()))) {
          throw stale();
        }
        return new SelectedColor(colorId, color.deepCopy());
      }
    }
    var closest =
        RecommendationCandidateSelector.closestColor(candidate, reference.path("hex").asString());
    if (closest == null) {
      throw invalid();
    }
    if (closest.matchedColorId() == null) {
      var color = item.getColor();
      return new SelectedColor(
          null,
          mapper.valueToTree(
              new PouchItemResponse.ColorInfo(
                  "sRGB",
                  closest.matchedColorHex(),
                  color.getSource().name(),
                  color.isEstimated())));
    }
    ProductShade shade = shades.get(item.getShadeId());
    ProductShadeColor slot =
        shade.getColors().stream()
            .filter(value -> value.getId().equals(closest.matchedColorId()))
            .findFirst()
            .orElseThrow();
    return catalogColor(slot);
  }

  private SelectedColor sameColor(GuideStepProductLink link) {
    return link.getColor() == null || !link.getColor().hasUsableColor()
        ? new SelectedColor(null, null)
        : catalogColor(link.getColor());
  }

  private SelectedColor catalogColor(ProductShadeColor slot) {
    return new SelectedColor(
        slot.getId(),
        mapper.valueToTree(
            new PouchItemResponse.ColorInfo(
                "sRGB", slot.getColor().getHex(), "CATALOG", slot.getColor().isEstimated())));
  }

  private static boolean isSame(PouchItem item, GuideStepProductLink link) {
    return link != null
        && link.getReasonCode() != ReferenceMatchReason.LINK_CONFLICT
        && link.getProduct() != null
        && link.getShade() != null
        && RecommendationCandidateSelector.isSame(
            link.getProduct().getId(),
            link.getShade().getId(),
            item.getProductId(),
            item.getShadeId());
  }

  private static BusinessException invalid() {
    return new BusinessException(
        HttpStatus.BAD_REQUEST, "GUIDE_SELECTION_INVALID", "가이드 단계의 제품 선택이 유효하지 않습니다.");
  }

  public static BusinessException stale() {
    return new BusinessException(HttpStatus.CONFLICT, "GUIDE_MATCH_STALE", "제품 정보를 다시 매칭해 주세요.");
  }

  public record PreparedStep(String stepId, boolean skipped, JsonNode snapshot) {}

  private record SelectedColor(UUID id, JsonNode color) {}
}
