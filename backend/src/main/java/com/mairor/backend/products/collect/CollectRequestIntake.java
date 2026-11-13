package com.mairor.backend.products.collect;

import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.entity.CollectTrigger;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import com.mairor.backend.products.repository.CatalogCollectRequestUserRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 직접 입력으로 등록된 파우치 항목에서 화장품 수집 요청을 만든다(S15P31A306-517). 회원에게 묻거나 알리지 않는다.
 *
 * <p>순서:
 *
 * <ol>
 *   <li>자동 수집 소분류가 아니거나 회원의 최근 24시간 요청이 한도를 넘으면 만들지 않는다.
 *   <li>카탈로그를 먼저 다시 본다. 그 사이 다른 요청으로 제품이 들어왔으면 수집하지 않고 바로 끝난 요청으로 남긴다. 제품은 있는데 회원이 적은 호수가 없으면 그 제품의
 *       이름과 호수로 다시 찾는다(시리즈별 상품이면 호수가 있는 상품을 워커가 고른다).
 *   <li>같은 제품이 최근에 찾은 제품 없음·부족 정보 미해결로 끝났으면 다시 요청하지 않는다.
 *   <li>같은 제품의 진행 중 요청이 있으면 회원만 붙이고, 없으면 새 요청을 QUEUED 로 넣는다. 새 요청은 커밋된 뒤 큐에 보낸다 ({@link
 *       CollectRequestQueued}).
 * </ol>
 */
@Service
public class CollectRequestIntake {

  static final Duration LIMIT_WINDOW = Duration.ofHours(24);

  private final CatalogCollectProperties properties;
  private final PouchItemRepository pouchItems;
  private final CollectCompletion completion;
  private final CatalogCollectRequestRepository requests;
  private final CatalogCollectRequestUserRepository requesters;
  private final ApplicationEventPublisher events;
  private final Clock clock;

  public CollectRequestIntake(
      CatalogCollectProperties properties,
      PouchItemRepository pouchItems,
      CollectCompletion completion,
      CatalogCollectRequestRepository requests,
      CatalogCollectRequestUserRepository requesters,
      ApplicationEventPublisher events,
      Clock clock) {
    this.properties = properties;
    this.pouchItems = pouchItems;
    this.completion = completion;
    this.requests = requests;
    this.requesters = requesters;
    this.events = events;
    this.clock = clock;
  }

  /** 접수 결과. 요청을 만들지 않았으면 {@code requestId}가 없다. */
  public record Intake(IntakeOutcome outcome, UUID requestId) {
    static Intake skipped(IntakeOutcome outcome) {
      return new Intake(outcome, null);
    }
  }

  /** 등록 트랜잭션이 커밋된 뒤 따로 부른다. 등록과 같은 트랜잭션이 아니다. */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public Intake requestFor(UUID userId, UUID pouchItemId) {
    if (!properties.enabled()) {
      return Intake.skipped(IntakeOutcome.DISABLED);
    }
    Optional<PouchItem> found = pouchItems.findByIdAndUserId(pouchItemId, userId);
    if (found.isEmpty() || found.get().getRegistrationMode() != RegistrationMode.MANUAL) {
      return Intake.skipped(IntakeOutcome.NOT_MANUAL);
    }
    PouchItem item = found.get();
    if (!properties.typeSet().contains(item.getType())) {
      return Intake.skipped(IntakeOutcome.TYPE_NOT_COLLECTED);
    }
    Instant now = clock.instant();
    if (requesters.countByUserIdAndCreatedAtGreaterThanEqual(userId, now.minus(LIMIT_WINDOW))
        >= properties.dailyLimitPerUser()) {
      return Intake.skipped(IntakeOutcome.DAILY_LIMIT);
    }

    Target target = targetFor(item);
    if (target.finished() != null) {
      return finishedInCatalog(item, target, now);
    }
    if (requests.existsRecentDeadEnd(target.key(), now.minus(properties.retryAfter()))) {
      return Intake.skipped(IntakeOutcome.RECENTLY_TRIED);
    }
    return queueOrJoin(item, target, now);
  }

  /** 수집할 대상. 카탈로그만으로 결론이 나면 {@code finished}에 끝난 상태가 있다. */
  private record Target(
      String key, String name, String url, CollectRequestStatus finished, String reason) {}

  private Target targetFor(PouchItem item) {
    String key = nameKey(item);
    CollectCompletion.Judgment judgment =
        completion.judge(
            completion.productsByName(item.getType(), item.getBrand(), item.getName()),
            item.getCategory(),
            item.getShadeName());
    if (judgment == null) {
      return new Target(key, item.getName(), null, null, null);
    }
    if (CollectCompletion.SHADE_NOT_FOUND.equals(judgment.reason())) {
      // 제품은 알지만 적은 호수가 없다. 한 제품이 시리즈별 상품으로 나뉘어 있으면 다른 시리즈에 있을 수 있어서 그 상품 주소가 아니라
      // 이름과 호수로 다시 찾는다(워커가 호수가 있는 시리즈를 고른다)
      return new Target(key, item.getName(), null, null, null);
    }
    return new Target(key, item.getName(), null, judgment.status(), judgment.reason());
  }

  private Intake finishedInCatalog(PouchItem item, Target target, Instant now) {
    CatalogCollectRequest request = newRequest(item, target);
    request.finish(target.finished(), target.reason(), now);
    requests.saveAndFlush(request);
    attach(request.getId(), item, now);
    events.publishEvent(new CollectRequestFinished(request.getId(), request.getStatus()));
    IntakeOutcome outcome =
        target.finished() == CollectRequestStatus.RESOLVED
            ? IntakeOutcome.RESOLVED_IN_CATALOG
            : IntakeOutcome.UNRESOLVED_IN_CATALOG;
    return new Intake(outcome, request.getId());
  }

  private Intake queueOrJoin(PouchItem item, Target target, Instant now) {
    CatalogCollectRequest draft = newRequest(item, target);
    int inserted = requests.insertIfNoneOpen(draft, now);
    UUID requestId =
        inserted == 1
            ? draft.getId()
            : requests
                .findOpenByRequestKey(target.key())
                .map(CatalogCollectRequest::getId)
                .orElseThrow(() -> new IllegalStateException("진행 중 요청이 방금 끝났다: " + target.key()));
    attach(requestId, item, now);
    if (inserted == 1) {
      events.publishEvent(new CollectRequestQueued(requestId));
    }
    return new Intake(inserted == 1 ? IntakeOutcome.QUEUED : IntakeOutcome.JOINED, requestId);
  }

  private CatalogCollectRequest newRequest(PouchItem item, Target target) {
    return new CatalogCollectRequest(
        CollectTrigger.USER,
        target.key(),
        item.getCategory(),
        item.getType(),
        item.getBrand(),
        target.name(),
        target.url(),
        item.getShadeName());
  }

  private void attach(UUID requestId, PouchItem item, Instant now) {
    requesters.attach(requestId, item.getUserId(), item.getId(), item.getUpdatedAt(), now);
  }

  /**
   * 이름으로 찾는 요청의 키. 소분류·브랜드·공백을 뺀 제품명·공백을 뺀 호수명이 같으면 같은 요청이다. 호수가 다르면 다른 요청이다(한 제품이 시리즈별 상품으로 나뉘어
   * 있으면 호수마다 수집할 상품이 다르다).
   */
  static String nameKey(PouchItem item) {
    String shade =
        item.getShadeName() == null ? "" : CatalogTextNormalizer.compact(item.getShadeName());
    return "NAME|"
        + item.getType()
        + "|"
        + CatalogTextNormalizer.normalize(item.getBrand())
        + "|"
        + CatalogTextNormalizer.compact(item.getName())
        + "|"
        + shade;
  }
}
