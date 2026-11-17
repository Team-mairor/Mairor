package com.mairor.backend.matching.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import com.mairor.backend.matching.dto.CreateGuideMatchRequest;
import com.mairor.backend.matching.dto.GuideMatchDetailResponse;
import com.mairor.backend.matching.dto.GuideMatchResponse;
import com.mairor.backend.matching.entity.GuideMatch;
import com.mairor.backend.matching.repository.GuideMatchRepository;
import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.repository.ProductShadeRepository;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/** API-RECOMMEND-001: 하나의 repeatable-read 스냅샷에서 매칭을 계산하고 결과를 보존한다. */
@Service
public class GuideMatchGenerationService {

  private static final String EXCLUDED_MAKEUP = "other";

  private final GuideRepository guides;
  private final GuideStepProductLinkRepository productLinks;
  private final PouchItemRepository pouchItems;
  private final PouchVersionRepository pouchVersions;
  private final ProductShadeRepository shades;
  private final GuideMatchRepository matches;
  private final ReferenceColorResolver referenceColors;
  private final PouchCandidateAssembler candidateAssembler;
  private final RecommendationCandidateSelector candidateSelector;
  private final ObjectMapper objectMapper;

  public GuideMatchGenerationService(
      GuideRepository guides,
      GuideStepProductLinkRepository productLinks,
      PouchItemRepository pouchItems,
      PouchVersionRepository pouchVersions,
      ProductShadeRepository shades,
      GuideMatchRepository matches,
      ReferenceColorResolver referenceColors,
      PouchCandidateAssembler candidateAssembler,
      RecommendationCandidateSelector candidateSelector,
      ObjectMapper objectMapper) {
    this.guides = guides;
    this.productLinks = productLinks;
    this.pouchItems = pouchItems;
    this.pouchVersions = pouchVersions;
    this.shades = shades;
    this.matches = matches;
    this.referenceColors = referenceColors;
    this.candidateAssembler = candidateAssembler;
    this.candidateSelector = candidateSelector;
    this.objectMapper = objectMapper;
  }

  @Transactional(isolation = Isolation.REPEATABLE_READ)
  public GuideMatchResponse create(UUID userId, CreateGuideMatchRequest request) {
    long pouchVersion =
        pouchVersions
            .findByUserId(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    Guide guide =
        guides
            .findById(request.guideId())
            .filter(found -> found.getReviewStatus() == ReviewStatus.APPROVED)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));

    List<PouchItem> ownedItems = pouchItems.findByUserIdOrderByCreatedAtDescIdDesc(userId);
    Map<UUID, PouchItem> itemsById =
        ownedItems.stream().collect(Collectors.toMap(PouchItem::getId, Function.identity()));
    List<UUID> shadeIds =
        ownedItems.stream().map(PouchItem::getShadeId).filter(id -> id != null).distinct().toList();
    Map<UUID, ProductShade> shadesById =
        shadeIds.isEmpty()
            ? Map.of()
            : shades.findByIdIn(shadeIds).stream()
                .collect(Collectors.toMap(ProductShade::getId, Function.identity()));
    List<RecommendationCandidateSelector.Candidate> candidates =
        ownedItems.stream().map(item -> candidateAssembler.assemble(item, shadesById)).toList();
    Map<String, GuideStepProductLink> linksByStep =
        productLinks.findByGuideIdOrderByStepIdAsc(guide.getId()).stream()
            .collect(Collectors.toMap(GuideStepProductLink::getStepId, Function.identity()));

    JsonNode guideInput = objectMapper.readTree(guide.getGuideInput());
    ArrayNode steps = JsonNodeFactory.instance.arrayNode();
    ObjectNode referenceColorSnapshots = JsonNodeFactory.instance.objectNode();
    for (JsonNode guideStep : guideInput.path("steps")) {
      String makeup = guideStep.path("makeup").asString("");
      if (EXCLUDED_MAKEUP.equals(makeup)) {
        continue;
      }
      String stepId = guideStep.path("stepId").asString("");
      GuideStepProductLink link = linksByStep.get(stepId);
      ReferenceColorResolver.ReferenceColor referenceColor =
          referenceColors.resolve(link, guideStep.path("targetColor"));
      snapshotReferenceColor(referenceColorSnapshots, stepId, link, referenceColor);
      steps.add(
          matchStep(
              guideStep,
              makeup,
              link,
              referenceColor,
              ownedItems,
              itemsById,
              candidates,
              shadesById));
    }

    ObjectNode snapshot = JsonNodeFactory.instance.objectNode();
    snapshot.set("steps", steps);
    snapshot.set("referenceColors", referenceColorSnapshots);

    GuideMatch match =
        matches.saveAndFlush(
            new GuideMatch(
                UUID.randomUUID(),
                userId,
                guide.getId(),
                guide.getVersion(),
                pouchVersion,
                guide.getReferenceVersion(),
                PouchCompatibilityPolicy.VERSION,
                objectMapper.writeValueAsString(snapshot)));
    return GuideMatchResponse.from(match, steps);
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public GuideMatchDetailResponse get(UUID userId, UUID matchId) {
    GuideMatch match =
        matches
            .findByIdAndUserId(matchId, userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    Guide guide =
        guides
            .findById(match.getGuideId())
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    long currentPouchVersion =
        pouchVersions
            .findByUserId(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    boolean stale =
        match.getPouchVersion() != currentPouchVersion
            || match.getGuideVersion() != guide.getVersion()
            || match.getReferenceVersion() != guide.getReferenceVersion()
            || guide.getReviewStatus() != ReviewStatus.APPROVED
            || match.getCompatibilityVersion() != PouchCompatibilityPolicy.VERSION;
    JsonNode snapshot = objectMapper.readTree(match.getMatchSnapshot());
    return GuideMatchDetailResponse.from(match, snapshot.path("steps"), stale);
  }

  private ObjectNode matchStep(
      JsonNode guideStep,
      String makeup,
      GuideStepProductLink link,
      ReferenceColorResolver.ReferenceColor referenceColor,
      List<PouchItem> ownedItems,
      Map<UUID, PouchItem> itemsById,
      List<RecommendationCandidateSelector.Candidate> candidates,
      Map<UUID, ProductShade> shadesById) {
    String stepId = guideStep.path("stepId").asString("");
    boolean comparisonAvailable = referenceColor != null;
    UUID sourceProductId = linkedProductId(link);
    UUID sourceShadeId = linkedShadeId(link);
    UUID sameItemId = findSameItem(sourceProductId, sourceShadeId, ownedItems);

    List<RecommendationCandidateSelector.RankedCandidate> alternatives =
        candidateSelector
            .selectAll(makeup, comparisonAvailable ? referenceColor.hex() : null, candidates)
            .stream()
            .filter(candidate -> !candidate.candidate().pouchItemId().equals(sameItemId))
            .toList();

    ObjectNode result = JsonNodeFactory.instance.objectNode();
    result.put("stepId", stepId);
    String category = PouchCompatibilityPolicy.categoryFor(makeup);
    if (category == null) {
      result.putNull("category");
    } else {
      result.put("category", category);
    }
    result.put("comparisonAvailable", comparisonAvailable);
    ArrayNode candidateNodes = result.putArray("candidates");
    ArrayNode alternativeNodes = result.putArray("alternatives");
    for (int index = 0; index < alternatives.size(); index++) {
      ObjectNode alternative = alternativeNodes.addObject();
      alternative.put("pouchItemId", alternatives.get(index).candidate().pouchItemId().toString());
      alternative.put("rank", index + 1);
      alternative.put("matchedColorHex", alternatives.get(index).matchedColorHex());
    }

    if (sameItemId != null) {
      result.put("result", "SAME");
      result.put("samePouchItemId", sameItemId.toString());
      result.putNull("noneReason");
      return result;
    }
    result.putNull("samePouchItemId");

    if (ownedItems.isEmpty()) {
      result.put("result", "NONE");
      result.put("noneReason", "NO_ITEMS");
      return result;
    }

    List<RecommendationCandidateSelector.RankedCandidate> ranked =
        alternatives.stream().limit(RecommendationCandidateSelector.MAX_CANDIDATES).toList();
    if (ranked.isEmpty()) {
      result.put("result", "NONE");
      result.put("noneReason", comparisonAvailable ? "NO_SUITABLE_ITEM" : "COMPARISON_UNAVAILABLE");
      return result;
    }

    result.put("result", "SUBSTITUTE");
    result.putNull("noneReason");
    for (int index = 0; index < ranked.size(); index++) {
      RecommendationCandidateSelector.RankedCandidate rankedCandidate = ranked.get(index);
      PouchItem item = itemsById.get(rankedCandidate.candidate().pouchItemId());
      ObjectNode candidate = candidateNodes.addObject();
      candidate.put("pouchItemId", item.getId().toString());
      candidate.put("rank", index + 1);
      candidate.set("product", pouchSnapshot(item, rankedCandidate, shadesById));
      if (rankedCandidate.matchedColorId() == null) {
        candidate.putNull("matchedColorId");
      } else {
        candidate.put("matchedColorId", rankedCandidate.matchedColorId().toString());
      }
    }
    return result;
  }

  private static void snapshotReferenceColor(
      ObjectNode referenceColors,
      String stepId,
      GuideStepProductLink link,
      ReferenceColorResolver.ReferenceColor referenceColor) {
    if (referenceColor == null) {
      referenceColors.putNull(stepId);
      return;
    }
    ObjectNode color = referenceColors.putObject(stepId);
    color.put("colorSpace", "sRGB");
    color.put("hex", referenceColor.hex());
    color.put("source", referenceColor.source());
    color.put("estimated", referenceColor.estimated());
    if ("CATALOG".equals(referenceColor.source()) && link != null && link.getColor() != null) {
      color.put("sourceColorId", link.getColor().getId().toString());
    } else {
      color.putNull("sourceColorId");
    }
  }

  private ObjectNode pouchSnapshot(
      PouchItem item,
      RecommendationCandidateSelector.RankedCandidate ranked,
      Map<UUID, ProductShade> shadesById) {
    ObjectNode product = objectMapper.valueToTree(PouchItemResponse.from(item));
    String source = "CATALOG";
    boolean estimated = true;
    if (ranked.matchedColorId() == null) {
      PouchColor storedColor = item.getColor();
      source = storedColor == null ? "CATALOG" : storedColor.getSource().name();
      estimated = storedColor == null || storedColor.isEstimated();
    } else {
      ProductShade shade = shadesById.get(item.getShadeId());
      ProductShadeColor slot =
          shade == null
              ? null
              : shade.getColors().stream()
                  .filter(color -> ranked.matchedColorId().equals(color.getId()))
                  .findFirst()
                  .orElse(null);
      estimated = slot == null || slot.getColor().isEstimated();
    }
    ObjectNode color = JsonNodeFactory.instance.objectNode();
    color.put("colorSpace", "sRGB");
    color.put("hex", ranked.matchedColorHex());
    color.put("source", source);
    color.put("estimated", estimated);
    product.set("color", color);
    product.put("colorSource", source);
    return product;
  }

  private static UUID findSameItem(
      UUID sourceProductId, UUID sourceShadeId, List<PouchItem> items) {
    if (sourceProductId == null || sourceShadeId == null) {
      return null;
    }
    return items.stream()
        .filter(item -> sourceProductId.equals(item.getProductId()))
        .filter(item -> sourceShadeId.equals(item.getShadeId()))
        .map(PouchItem::getId)
        .findFirst()
        .orElse(null);
  }

  private static UUID linkedProductId(GuideStepProductLink link) {
    if (link == null
        || link.getReasonCode() == ReferenceMatchReason.LINK_CONFLICT
        || link.getProduct() == null) {
      return null;
    }
    return link.getProduct().getId();
  }

  private static UUID linkedShadeId(GuideStepProductLink link) {
    if (link == null
        || link.getReasonCode() == ReferenceMatchReason.LINK_CONFLICT
        || (link.getMatchLevel() != ReferenceMatchLevel.SHADE
            && link.getMatchLevel() != ReferenceMatchLevel.SLOT)
        || link.getShade() == null) {
      return null;
    }
    return link.getShade().getId();
  }
}
