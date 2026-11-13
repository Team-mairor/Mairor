package com.mairor.backend.products.collect;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.products.dto.request.CollectJobResultRequest;
import com.mairor.backend.products.dto.request.CollectJobResultRequest.Collected;
import com.mairor.backend.products.dto.request.CollectJobResultRequest.Status;
import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import com.mairor.backend.products.repository.ProductNameAliasRepository;
import com.mairor.backend.products.repository.ProductRepository;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 수집 워커의 작업 결과로 수집 요청을 끝낸다(S15P31A306-517).
 *
 * <ul>
 *   <li>{@code COLLECTED}: 적재가 끝난 카탈로그를 다시 읽어 부족 정보가 풀렸는지 판정한다({@link CollectCompletion}). 이름 요청은
 *       이름으로, 상품 주소 요청은 결과 상품의 출처 번호로 제품을 찾는다
 *   <li>{@code SEARCH_EMPTY}·{@code UNSUPPORTED_SOURCE}: NOT_FOUND. 사유는 앞의 것만 24시간 다시 요청하지 않는 데 쓰인다
 *   <li>{@code BLOCKED}·{@code FAILED}: FAILED
 * </ul>
 *
 * <p>같은 결과가 두 번 와도(콜백 응답 유실 뒤 재전송) 이미 끝난 요청은 바꾸지 않고 성공으로 답한다.
 */
@Service
public class CollectResultService {

  static final String RESULT_TIMEOUT = "RESULT_TIMEOUT";
  static final String JOB_ID_MISMATCH = "주소의 jobId 와 본문의 jobId 가 다릅니다.";

  private static final Logger log = LoggerFactory.getLogger(CollectResultService.class);

  private final CatalogCollectRequestRepository requests;
  private final CatalogImportRunRepository importRuns;
  private final ProductRepository products;
  private final ProductNameAliasRepository aliases;
  private final CollectCompletion completion;
  private final ApplicationEventPublisher events;
  private final Clock clock;

  public CollectResultService(
      CatalogCollectRequestRepository requests,
      CatalogImportRunRepository importRuns,
      ProductRepository products,
      ProductNameAliasRepository aliases,
      CollectCompletion completion,
      ApplicationEventPublisher events,
      Clock clock) {
    this.requests = requests;
    this.importRuns = importRuns;
    this.products = products;
    this.aliases = aliases;
    this.completion = completion;
    this.events = events;
    this.clock = clock;
  }

  /** 반영한 뒤의 요청 상태와, 이번 호출이 요청을 끝냈는지. */
  public record Applied(CollectRequestStatus status, String reason, boolean changed) {}

  /**
   * @throws BusinessException 400 {@code VALIDATION_FAILED}: 본문의 jobId 가 주소와 다르면. 404 {@code
   *     NOT_FOUND}: 그런 요청이 없으면
   */
  @Transactional
  public Applied apply(UUID jobId, CollectJobResultRequest result) {
    if (!jobId.toString().equalsIgnoreCase(result.jobId())) {
      throw new BusinessException(
          HttpStatus.BAD_REQUEST, ErrorCode.VALIDATION_FAILED.name(), JOB_ID_MISMATCH);
    }
    CatalogCollectRequest request =
        requests
            .findByIdForUpdate(jobId)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    if (!request.isOpen()) {
      return new Applied(request.getStatus(), request.getReason(), false);
    }
    UUID importRunId =
        result.importRunId() != null && importRuns.existsById(result.importRunId())
            ? result.importRunId()
            : null;
    request.recordResult(result.status().name(), result.resultFile(), importRunId);
    Outcome outcome = judge(request, result);
    request.finish(outcome.status(), outcome.reason(), clock.instant());
    log.info(
        "수집 결과 반영: request={} worker={} → {} {}",
        jobId,
        result.status(),
        outcome.status(),
        outcome.reason() == null ? "" : outcome.reason());
    events.publishEvent(new CollectRequestFinished(jobId, outcome.status()));
    return new Applied(outcome.status(), outcome.reason(), true);
  }

  /**
   * 결과가 오지 않은 SENT 요청을 FAILED({@code RESULT_TIMEOUT})로 끝낸다. 그 사이 결과가 왔거나 다시 보내는 중이면 그대로 둔다.
   *
   * @return 끝냈으면 true
   */
  @Transactional
  public boolean timeOut(UUID requestId) {
    CatalogCollectRequest request = requests.findByIdForUpdate(requestId).orElse(null);
    if (request == null || request.getStatus() != CollectRequestStatus.SENT) {
      return false;
    }
    request.finish(CollectRequestStatus.FAILED, RESULT_TIMEOUT, clock.instant());
    log.warn("수집 결과가 오지 않아 끝낸다: request={}", requestId);
    events.publishEvent(new CollectRequestFinished(requestId, CollectRequestStatus.FAILED));
    return true;
  }

  private record Outcome(CollectRequestStatus status, String reason) {}

  private Outcome judge(CatalogCollectRequest request, CollectJobResultRequest result) {
    return switch (result.status()) {
      case COLLECTED -> judgeCollected(request, result.productsOrEmpty());
      case SEARCH_EMPTY -> new Outcome(CollectRequestStatus.NOT_FOUND, "SEARCH_EMPTY");
      case UNSUPPORTED_SOURCE ->
          new Outcome(
              CollectRequestStatus.NOT_FOUND, withDetail(Status.UNSUPPORTED_SOURCE, result));
      case BLOCKED -> new Outcome(CollectRequestStatus.FAILED, withDetail(Status.BLOCKED, result));
      case FAILED -> new Outcome(CollectRequestStatus.FAILED, withDetail(Status.FAILED, result));
    };
  }

  private Outcome judgeCollected(CatalogCollectRequest request, List<Collected> collected) {
    boolean byName = request.getName() != null && request.getTypeCode() != null;
    List<Product> candidates =
        byName
            ? completion.productsByName(
                request.getTypeCode(), request.getBrand(), request.getName())
            : productsFrom(request, collected);
    if (byName && candidates.isEmpty()) {
      candidates = rememberCollectedName(request, collected);
    }
    CollectCompletion.Judgment judgment =
        completion.judge(candidates, request.getCategoryCode(), request.getShadeName());
    if (judgment == null) {
      return new Outcome(CollectRequestStatus.UNRESOLVED, CollectCompletion.NOT_IN_CATALOG);
    }
    return new Outcome(judgment.status(), judgment.reason());
  }

  /**
   * 회원이 쓴 이름으로는 못 찾았지만 워커가 그 브랜드 공식 홈에서 제품 하나를 확실히 찾아 적재했으면, 회원이 쓴 이름을 그 제품의 별칭으로 남긴다. 워커가 후보를 여럿
   * 수집했거나(이름만으로 하나를 고르지 못함) 그 제품의 소분류가 요청과 다르면 남기지 않는다. 이후 검색·자동 연결이 이 별칭으로 같은 제품을 찾는다.
   */
  private List<Product> rememberCollectedName(
      CatalogCollectRequest request, List<Collected> collected) {
    if (collected.size() != 1) {
      return List.of();
    }
    Collected only = collected.getFirst();
    Product product =
        products.findBySourceAndSourceProductId(only.source(), only.sourceProductId()).orElse(null);
    if (product == null || !request.getTypeCode().equals(product.getType().getCode())) {
      return List.of();
    }
    aliases.remember(
        request.getTypeCode(),
        request.getBrand(),
        request.getName(),
        product.getId(),
        request.getId(),
        clock.instant());
    log.info("수집 요청 이름을 제품 별칭으로 남김: request={} product={}", request.getId(), product.getId());
    return List.of(product);
  }

  /** 상품 주소 요청: 요청한 주소의 상품을 먼저, 없으면 결과 상품 전부를 출처 번호로 찾는다. */
  private List<Product> productsFrom(CatalogCollectRequest request, List<Collected> collected) {
    List<Collected> same =
        collected.stream().filter(c -> c.sourceUrl().equals(request.getProductUrl())).toList();
    List<Product> found = new ArrayList<>();
    for (Collected ref : same.isEmpty() ? collected : same) {
      products
          .findBySourceAndSourceProductId(ref.source(), ref.sourceProductId())
          .filter(p -> found.stream().noneMatch(f -> f.getId().equals(p.getId())))
          .ifPresent(found::add);
    }
    return found;
  }

  /** 사유 앞에 워커 상태를 붙인다. 워커가 이미 붙여 보냈으면(BLOCKED:host) 그대로 쓴다. */
  private static String withDetail(Status status, CollectJobResultRequest result) {
    String reason = result.reason();
    if (reason == null || reason.isBlank()) {
      return status.name();
    }
    return reason.startsWith(status.name() + ":") ? reason : status.name() + ":" + reason;
  }
}
