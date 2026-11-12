package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.dto.response.FoundProductResponse;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.guides.dto.response.ReferenceProductResponse;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 회원이 보는 분석 작업 상태({@link AnalysisJobStatusView})를 만든다. 상태 조회(API-VIDEO-003)와 분석 상태 SSE 가 이것으로 같은 값을
 * 만든다. 작업과 그 작업의 가이드를 읽어 칸을 채운다.
 */
@Service
public class AnalysisJobStatusService {

  private static final Logger log = LoggerFactory.getLogger(AnalysisJobStatusService.class);

  private final AnalysisJobAccess access;
  private final AnalysisJobRepository jobs;
  private final GuideRepository guides;
  private final GuideStepProductLinkRepository productLinks;
  private final PouchItemRepository pouchItems;
  private final AnalysisStatusProperties properties;
  private final AnalysisRequestProperties requestProperties;
  private final ObjectMapper objectMapper;

  AnalysisJobStatusService(
      AnalysisJobAccess access,
      AnalysisJobRepository jobs,
      GuideRepository guides,
      GuideStepProductLinkRepository productLinks,
      PouchItemRepository pouchItems,
      AnalysisStatusProperties properties,
      AnalysisRequestProperties requestProperties,
      ObjectMapper objectMapper) {
    this.access = access;
    this.jobs = jobs;
    this.guides = guides;
    this.productLinks = productLinks;
    this.pouchItems = pouchItems;
    this.properties = properties;
    this.requestProperties = requestProperties;
    this.objectMapper = objectMapper;
  }

  /**
   * 회원의 작업 상태.
   *
   * @throws com.mairor.backend.common.error.BusinessException 404 {@code NOT_FOUND} — 없거나 볼 수 없는 작업
   */
  @Transactional(readOnly = true)
  public AnalysisJobStatusView get(UUID userId, UUID jobId) {
    return assemble(userId, access.load(userId, jobId));
  }

  /**
   * 회원이 볼 수 있는 작업의 지금 상태. 분석 상태 SSE 가 연결별 회원으로 권한을 다시 확인하며 바뀔 때마다 읽는다.
   *
   * @return 작업이 없으면(지워짐) 빈 값
   */
  @Transactional(readOnly = true)
  public Optional<AnalysisJobStatusView> find(UUID userId, UUID jobId) {
    return jobs.findById(jobId)
        .filter(job -> access.canView(userId, job))
        .map(job -> assemble(userId, job));
  }

  /** 조회 회원의 상태를 만든다. 가이드를 읽으므로 트랜잭션 안에서 부른다. */
  private AnalysisJobStatusView assemble(UUID userId, AnalysisJob job) {
    Optional<Guide> guide = guides.findByAnalysisJobId(job.getId());
    FoundProducts products =
        guide.map(g -> foundProducts(g, userId)).orElseGet(FoundProducts::unavailable);
    ReviewStatus reviewStatus = guide.map(Guide::getReviewStatus).orElse(ReviewStatus.NOT_READY);
    boolean approved = reviewStatus == ReviewStatus.APPROVED;
    boolean completed = job.getStatus() == AnalysisStatus.COMPLETED;
    boolean finished =
        job.getStatus() == AnalysisStatus.FAILED
            || approved
            || reviewStatus == ReviewStatus.REJECTED;
    return new AnalysisJobStatusView(
        job.getId(),
        job.getVideo().getId(),
        job.getStatus(),
        job.getProgressStage(),
        job.getProgressPercent(),
        null,
        StageProgress.of(job.getStatus(), job.getProgressStage(), progress(job)),
        // 재시도 가능한 실패라도 시도 횟수 상한에 닿았으면 재시도 버튼을 보이지 않게 false
        requestProperties.canRetry(job),
        reviewStatus,
        approved,
        approved ? guide.get().getId() : null,
        products.items(),
        products.items().size(),
        products.totalCount(),
        job.getFailureCode(),
        job.getFailureMessage(),
        finished ? null : (int) properties.pollAfter().toSeconds(),
        job.getCreatedAt(),
        completed ? job.getFinishedAt() : null);
  }

  private FoundProducts foundProducts(Guide guide, UUID userId) {
    JsonNode input = read(guide.getGuideInput());
    JsonNode steps = input == null ? null : input.path("steps");
    if (steps == null || !steps.isArray()) {
      return FoundProducts.unavailable();
    }

    Map<String, GuideStepProductLink> links = new HashMap<>();
    for (GuideStepProductLink link : productLinks.findByGuideIdOrderByStepIdAsc(guide.getId())) {
      links.put(link.getStepId(), link);
    }
    List<PouchItem> pouch =
        userId == null ? List.of() : pouchItems.findByUserIdOrderByCreatedAtDescIdDesc(userId);
    List<FoundProductResponse> result = new ArrayList<>();
    for (JsonNode step : steps) {
      JsonNode product = step.path("product");
      if (!product.isObject()) {
        continue;
      }
      String brand = text(product.path("brand"));
      String name = text(product.path("name"));
      String shade = text(product.path("shade"));
      if (brand == null && name == null && shade == null) {
        continue;
      }
      String stepId = text(step.path("stepId"));
      GuideStepProductLink link = stepId == null ? null : links.get(stepId);
      boolean conflict = link != null && link.getReasonCode() == ReferenceMatchReason.LINK_CONFLICT;
      String productId =
          link == null || conflict || link.getProduct() == null
              ? null
              : link.getProduct().getId().toString();
      String shadeId =
          link == null
                  || conflict
                  || (link.getMatchLevel() != ReferenceMatchLevel.SHADE
                      && link.getMatchLevel() != ReferenceMatchLevel.SLOT)
              ? null
              : link.getShade().getId().toString();
      String matchStatus =
          link != null
                  && link.getMatchLevel() == ReferenceMatchLevel.NONE
                  && link.getReasonCode() == ReferenceMatchReason.PRODUCT_AMBIGUOUS
              ? "CANDIDATE"
              : productId == null ? "UNMATCHED" : "MATCHED";
      String fullName = brand == null ? name : name == null ? brand : brand + " " + name;
      ReferenceProductResponse reference =
          new ReferenceProductResponse(
              productId, shadeId, fullName, shade, matchStatus, "UNKNOWN", List.of(), Boolean.TRUE);
      result.add(
          new FoundProductResponse(
              stepId,
              text(step.path("makeup")),
              reference,
              userId == null
                  ? FoundProductResponse.Ownership.UNKNOWN
                  : ownership(productId, shadeId, brand, name, shade, pouch)));
    }
    List<FoundProductResponse> items = List.copyOf(result);
    return new FoundProducts(items, items.size());
  }

  private record FoundProducts(List<FoundProductResponse> items, Integer totalCount) {
    private static FoundProducts unavailable() {
      return new FoundProducts(List.of(), null);
    }
  }

  private static FoundProductResponse.Ownership ownership(
      String productId,
      String shadeId,
      String brand,
      String name,
      String shade,
      List<PouchItem> pouch) {
    for (PouchItem item : pouch) {
      if (productId != null) {
        if (productId.equals(item.getProductId() == null ? null : item.getProductId().toString())
            && (shadeId == null
                || shadeId.equals(
                    item.getShadeId() == null ? null : item.getShadeId().toString()))) {
          return FoundProductResponse.Ownership.OWNED;
        }
        continue;
      }
      if (same(brand, item.getBrandNormalized())
          && same(name, item.getNameNormalized())
          && (shade == null || same(shade, item.getShadeNameNormalized()))) {
        return FoundProductResponse.Ownership.OWNED;
      }
    }
    return FoundProductResponse.Ownership.NOT_OWNED;
  }

  private static boolean same(String value, String normalized) {
    if (value == null || normalized == null) {
      return false;
    }
    try {
      return CatalogTextNormalizer.normalize(value).equals(normalized);
    } catch (IllegalArgumentException e) {
      return false;
    }
  }

  private JsonNode read(String json) {
    if (json == null) {
      return null;
    }
    try {
      return objectMapper.readTree(json);
    } catch (JacksonException e) {
      log.warn("저장된 가이드 입력을 읽지 못함", e);
      return null;
    }
  }

  private static String text(JsonNode node) {
    if (!node.isString()) {
      return null;
    }
    String value = node.asString().trim();
    return value.isEmpty() ? null : value;
  }

  private JsonNode progress(AnalysisJob job) {
    String json = job.getAiProgress();
    if (json == null) {
      return null;
    }
    try {
      return objectMapper.readTree(json);
    } catch (JacksonException e) {
      // 저장할 때 검사하므로 생기지 않는다. 생겨도 상태 조회를 막지 않는다
      log.warn("저장된 AI 진행 숫자를 읽지 못함 jobId={}", job.getId(), e);
      return null;
    }
  }
}
