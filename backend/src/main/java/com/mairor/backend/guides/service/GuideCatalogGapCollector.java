package com.mairor.backend.guides.service;

import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import com.mairor.backend.products.collect.CatalogCollectProperties;
import com.mairor.backend.products.collect.CollectRequestQueued;
import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CollectGap;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.repository.CatalogCollectRequestGuideRepository;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 가이드 대조가 끝난 뒤, 단계마다 카탈로그에 부족한 제품·호수·색을 골라 수집 요청을 만든다(S15P31A306-518). 회원 요청(S15P31A306-517)과 같은
 * 큐·같은 중복 묶기를 쓴다. 가이드는 기다리지 않고 먼저 보여 준다.
 *
 * <table>
 *   <tr><th>단계 연결</th><th>부족 유형</th><th>요청</th></tr>
 *   <tr><td>제품 없음({@code PRODUCT_NOT_FOUND})</td><td>PRODUCT_MISSING</td><td>영상의 브랜드·제품명으로 찾기(소분류 모름, 수집기 모델이 분류)</td></tr>
 *   <tr><td>제품만 연결, 호수 없음({@code SHADE_NOT_FOUND})</td><td>SHADE_MISSING</td><td>그 제품을 다시 수집</td></tr>
 *   <tr><td>호수 연결, 칸 행 없음({@code NO_COLOR_SLOTS})</td><td>COLOR_MISSING</td><td>그 제품을 다시 수집. 영상의 칸 이름·번호가 있으면 함께 남긴다</td></tr>
 *   <tr><td>칸 연결, 그 칸 색을 쓸 수 없음</td><td>COLOR_MISSING</td><td>그 제품을 다시 수집</td></tr>
 * </table>
 *
 * <p>후보 여럿·호수 여럿·칸을 특정할 수 없음(팔레트에서 영상이 쓴 칸을 모름)·소분류 미지원·제품 정보 없음은 외부 수집으로 풀리지 않아 요청하지 않는다. 같은 부족분이
 * 최근에 한 번 끝났으면(상태 상관없음) 다시 요청하지 않는다. 요청이 끝나면 가이드를 다시 대조하는데, 그때 아직 부족하면 같은 요청이 되풀이되지 않게 하려는 것이다. 가이드
 * 하나가 최근 24시간에 붙을 수 있는 요청 수에 한도가 있다.
 */
@Service
public class GuideCatalogGapCollector {

  static final Duration LIMIT_WINDOW = Duration.ofHours(24);

  private static final Logger log = LoggerFactory.getLogger(GuideCatalogGapCollector.class);

  private final GuideRepository guides;
  private final GuideStepProductLinkRepository links;
  private final CatalogCollectRequestRepository requests;
  private final CatalogCollectRequestGuideRepository waitingSteps;
  private final CatalogCollectProperties properties;
  private final ObjectMapper json;
  private final ApplicationEventPublisher events;
  private final Clock clock;

  GuideCatalogGapCollector(
      GuideRepository guides,
      GuideStepProductLinkRepository links,
      CatalogCollectRequestRepository requests,
      CatalogCollectRequestGuideRepository waitingSteps,
      CatalogCollectProperties properties,
      ObjectMapper json,
      ApplicationEventPublisher events,
      Clock clock) {
    this.guides = guides;
    this.links = links;
    this.requests = requests;
    this.waitingSteps = waitingSteps;
    this.properties = properties;
    this.json = json;
    this.events = events;
    this.clock = clock;
  }

  /** 한 단계의 부족분. {@code key}가 같으면 같은 요청이다. */
  record Gap(String stepId, CatalogCollectRequest draft) {}

  /**
   * @return 이번에 새로 만들거나 붙은 요청 수
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public int collect(UUID guideId) {
    if (!properties.enabled()) {
      return 0;
    }
    Guide guide = guides.findById(guideId).orElse(null);
    if (guide == null) {
      return 0;
    }
    Instant now = clock.instant();
    long used =
        waitingSteps.countByGuideIdAndCreatedAtGreaterThanEqual(guideId, now.minus(LIMIT_WINDOW));
    int attached = 0;
    for (Gap gap : gaps(guide)) {
      if (used + attached >= properties.guideLimit()) {
        log.info("가이드의 수집 요청 한도에 닿았다: guide={}", guideId);
        break;
      }
      CatalogCollectRequest draft = gap.draft();
      if (requests.existsFinishedSince(draft.getRequestKey(), now.minus(properties.retryAfter()))) {
        continue;
      }
      UUID requestId;
      if (requests.insertIfNoneOpen(draft, now) == 1) {
        requestId = draft.getId();
        events.publishEvent(new CollectRequestQueued(requestId));
      } else {
        requestId =
            requests
                .findOpenByRequestKey(draft.getRequestKey())
                .map(CatalogCollectRequest::getId)
                .orElse(null);
        if (requestId == null) {
          continue;
        }
      }
      attached += waitingSteps.attach(requestId, guideId, gap.stepId(), now);
    }
    if (attached > 0) {
      log.info("가이드 부족분 수집 요청: guide={} steps={}", guideId, attached);
    }
    return attached;
  }

  /** 단계 연결과 가이드 입력에서 부족분을 고른다. */
  List<Gap> gaps(Guide guide) {
    Map<String, JsonNode> stepsById = new HashMap<>();
    for (JsonNode step : json.readTree(guide.getGuideInput()).path("steps")) {
      String stepId = text(step.path("stepId"));
      if (stepId != null) {
        stepsById.put(stepId, step);
      }
    }
    List<Gap> found = new ArrayList<>();
    for (GuideStepProductLink link : links.findByGuideIdOrderByStepIdAsc(guide.getId())) {
      JsonNode step = stepsById.get(link.getStepId());
      if (step == null) {
        continue;
      }
      CatalogCollectRequest draft = draftFor(link, step);
      if (draft != null) {
        found.add(new Gap(link.getStepId(), draft));
      }
    }
    return found;
  }

  private CatalogCollectRequest draftFor(GuideStepProductLink link, JsonNode step) {
    JsonNode source = step.path("product");
    String shadeName = text(source.path("shade"));
    ReferenceMatchReason reason = link.getReasonCode();
    if (link.getMatchLevel() == ReferenceMatchLevel.NONE
        && reason == ReferenceMatchReason.PRODUCT_NOT_FOUND) {
      return productMissing(step, source, shadeName);
    }
    Product product = link.getProduct();
    if (product == null) {
      return null;
    }
    if (link.getMatchLevel() == ReferenceMatchLevel.PRODUCT
        && reason == ReferenceMatchReason.SHADE_NOT_FOUND
        && shadeName != null) {
      return productRefetch(
          CollectGap.SHADE_MISSING,
          "GUIDE|SHADE|" + product.getId() + "|" + normalized(shadeName),
          product,
          shadeName,
          new CatalogCollectRequest.Target(product.getId(), null, null, null));
    }
    ProductShade shade = link.getShade();
    if (link.getMatchLevel() == ReferenceMatchLevel.SHADE
        && reason == ReferenceMatchReason.NO_COLOR_SLOTS
        && shade != null) {
      String label = slotLabel(source.path("palette"));
      return productRefetch(
          CollectGap.COLOR_MISSING,
          "GUIDE|COLOR|" + shade.getId() + "|" + (label == null ? "" : normalized(label)),
          product,
          shade.getName(),
          new CatalogCollectRequest.Target(product.getId(), shade.getId(), null, label));
    }
    ProductShadeColor color = link.getColor();
    if (link.getMatchLevel() == ReferenceMatchLevel.SLOT
        && color != null
        && shade != null
        && !color.hasUsableColor()) {
      return productRefetch(
          CollectGap.COLOR_MISSING,
          "GUIDE|COLOR|" + color.getId(),
          product,
          shade.getName(),
          new CatalogCollectRequest.Target(product.getId(), shade.getId(), color.getId(), null));
    }
    return null;
  }

  private CatalogCollectRequest productMissing(JsonNode step, JsonNode source, String shadeName) {
    String category = GuideQueryService.MATCH_CATEGORY.get(GuideStepMakeup.of(step));
    String brand = text(source.path("brand"));
    String name = text(source.path("name"));
    if (category == null || brand == null || name == null) {
      return null;
    }
    try {
      // 한 제품이 시리즈별 상품으로 나뉘어 있으면 호수마다 수집할 상품이 달라서 호수도 키에 넣는다
      String key =
          "GUIDE|PRODUCT|"
              + category
              + "|"
              + CatalogTextNormalizer.normalize(brand)
              + "|"
              + CatalogTextNormalizer.compact(name)
              + "|"
              + (shadeName == null ? "" : normalizedCompact(shadeName));
      return CatalogCollectRequest.forGuide(
          CollectGap.PRODUCT_MISSING,
          key,
          category,
          null,
          brand,
          name,
          null,
          shadeName,
          CatalogCollectRequest.Target.NONE);
    } catch (IllegalArgumentException e) {
      return null;
    }
  }

  /** 이미 있는 제품을 다시 수집한다. 출처 주소가 있으면 그 상품 페이지를, 없으면 카탈로그 이름으로 공식 홈에서 찾는다. */
  private static CatalogCollectRequest productRefetch(
      CollectGap gap,
      String key,
      Product product,
      String shadeName,
      CatalogCollectRequest.Target target) {
    String url = product.getSourceUrl();
    try {
      return CatalogCollectRequest.forGuide(
          gap,
          key,
          product.getCategory().getCode(),
          product.getType().getCode(),
          product.getBrand(),
          url == null ? product.getName() : null,
          url,
          shadeName,
          target);
    } catch (IllegalArgumentException e) {
      return null;
    }
  }

  /** 팔레트에서 영상이 적은 칸 이름, 없으면 칸 번호. */
  private static String slotLabel(JsonNode palette) {
    String name = text(palette.path("slotName"));
    return name != null ? name : text(palette.path("slotNumber"));
  }

  private static String normalizedCompact(String text) {
    return normalized(text).replace(" ", "");
  }

  private static String normalized(String text) {
    try {
      return CatalogTextNormalizer.normalize(text);
    } catch (IllegalArgumentException e) {
      return "";
    }
  }

  private static String text(JsonNode value) {
    if (value == null || !value.isString()) {
      return null;
    }
    String result = value.asString().trim();
    return result.isEmpty() ? null : result;
  }
}
