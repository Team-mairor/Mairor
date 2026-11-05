package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedShade;
import com.mairor.backend.products.imports.ColorReplacementPolicy.Decision;
import com.mairor.backend.products.imports.ImportPlan.Outcome;
import com.mairor.backend.products.imports.ImportPlan.ShadePlan;
import com.mairor.backend.products.imports.ImportPlan.ShadePlan.Action;
import com.mairor.backend.products.imports.ImportPlan.SlotPlan;
import com.mairor.backend.products.imports.ImportPlan.SlotStep;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 읽기·검증을 통과한 수집 상품 한 건을 DB 에 어떻게 반영할지 계획한다(DB 는 바꾸지 않는다).
 *
 * <p>제품 판정 순서:
 *
 * <ol>
 *   <li>카테고리·종류를 정할 수 없으면 {@code UNCLASSIFIED}
 *   <li>같은 (출처, 상품 번호)의 제품이 있으면 갱신. 그 제품이 더 최근에 수집됐으면 {@code STALE}
 *   <li>없고, 같은 (종류, 브랜드, 제품명)의 제품이 있으면 {@code AMBIGUOUS}. 출처가 있든 없든 자동으로 연결하거나 합치지 않는다
 *   <li>없으면 {@code NEW}
 * </ol>
 *
 * 제품 판정이 {@code NEW}·{@code UPDATE}이면 호수를 묶고({@link ShadeMatcher}), 기존 호수와 맞추고, 칸을 맞추고({@link
 * SlotMatcher}), 칸마다 색을 판정한다({@link ColorApprovalPolicy}·{@link ColorReplacementPolicy}). 공백만 다른 기존
 * 제품을 찾는 판정은 제품 검색 공백 무시 비교(S15P31A306-326)가 정해지면 더한다.
 */
@Service
public class CatalogMatchPlanner {

  private final ProductRepository productRepository;
  private final CatalogTypeMapper typeMapper;
  private final ColorApprovalPolicy approvalPolicy;
  private final CatalogColorProperties colorProperties;
  private final ColorReferenceChecker referenceChecker;

  public CatalogMatchPlanner(
      ProductRepository productRepository,
      CatalogTypeMapper typeMapper,
      ColorApprovalPolicy approvalPolicy,
      CatalogColorProperties colorProperties,
      ColorReferenceChecker referenceChecker) {
    this.productRepository = productRepository;
    this.typeMapper = typeMapper;
    this.approvalPolicy = approvalPolicy;
    this.colorProperties = colorProperties;
    this.referenceChecker = referenceChecker;
  }

  @Transactional(readOnly = true)
  public ImportPlan plan(CollectedProduct item) {
    String cleanedName = CatalogNameCleaner.cleanProductName(item.name());
    Optional<TypeResolution> type =
        typeMapper.resolve(
            item.source(), item.sourceCategoryPath(), item.categoryHint(), item.typeHint());
    if (type.isEmpty()) {
      return product(Outcome.UNCLASSIFIED, item, null, null, cleanedName, Set.of());
    }

    Optional<Product> bySource =
        productRepository.findBySourceAndSourceProductId(item.source(), item.sourceProductId());
    if (bySource.isPresent()) {
      Product existing = bySource.get();
      Instant incomingAt = item.collectedAt().toInstant();
      if (existing.getCollectedAt() != null && incomingAt.isBefore(existing.getCollectedAt())) {
        return product(Outcome.STALE, item, type.get(), existing, cleanedName, Set.of());
      }
      // 갱신할 이름이 같은 종류의 다른 제품과 겹치면 저장할 때 유일 제약에 걸린다. 반영하지 않고 보류한다
      Optional<Product> nameClash =
          productRepository
              .findExact(existing.getType().getCode(), item.brand(), cleanedName)
              .filter(other -> !other.getId().equals(existing.getId()));
      if (nameClash.isPresent()) {
        return product(
            Outcome.AMBIGUOUS,
            item,
            type.get(),
            nameClash.get(),
            cleanedName,
            EnumSet.of(ImportReason.PRODUCT_NAME_CONFLICT));
      }
      Set<ImportReason> reasons = EnumSet.noneOf(ImportReason.class);
      if (!existing.getType().getCode().equals(type.get().typeCode())) {
        reasons.add(ImportReason.TYPE_KEPT);
      }
      return withShades(Outcome.UPDATE, item, type.get(), existing, cleanedName, reasons);
    }

    Optional<Product> sameKey =
        productRepository.findExact(type.get().typeCode(), item.brand(), cleanedName);
    if (sameKey.isPresent()) {
      return product(Outcome.AMBIGUOUS, item, type.get(), sameKey.get(), cleanedName, Set.of());
    }
    return withShades(
        Outcome.NEW, item, type.get(), null, cleanedName, EnumSet.noneOf(ImportReason.class));
  }

  private static ImportPlan product(
      Outcome outcome,
      CollectedProduct item,
      TypeResolution type,
      Product existing,
      String cleanedName,
      Set<ImportReason> reasons) {
    return new ImportPlan(
        outcome, item, type, existing, cleanedName, List.of(), Set.copyOf(reasons), List.of());
  }

  private ImportPlan withShades(
      Outcome outcome,
      CollectedProduct item,
      TypeResolution type,
      Product existing,
      String cleanedName,
      Set<ImportReason> reasons) {
    List<ProductShade> existingShades = existing == null ? List.of() : existing.getShades();
    Set<String> usedNames = new HashSet<>();
    existingShades.forEach(s -> usedNames.add(s.getNameNormalized()));

    List<ShadeMatcher.Group> groups = ShadeMatcher.group(item.shades());
    List<ShadeMatcher.Match> matches = matchAll(groups, existingShades);
    List<ShadePlan> shades = new ArrayList<>();
    for (int i = 0; i < groups.size(); i++) {
      shades.add(planShade(item, groups.get(i), matches.get(i), usedNames));
    }
    // 호수 계획이 다루지 않은 기존 호수의 칸도 출처 금지는 호수 대응과 상관없이 검사한다
    List<ProductShadeColor> leftover = leftoverDowngrades(item, existingShades, shades);
    Set<ImportReason> all = EnumSet.noneOf(ImportReason.class);
    all.addAll(reasons);
    if (!leftover.isEmpty()) {
      all.add(ImportReason.COLOR_DOWNGRADED);
    }
    return new ImportPlan(
        outcome, item, type, existing, cleanedName, List.copyOf(shades), Set.copyOf(all), leftover);
  }

  /**
   * 갱신 중인 제품의 기존 호수·칸 전체에서, **호수 계획과 칸 계획이 다루지 않은** 출처 금지 색을 찾는다. 이번 수집에서 빠진 호수, 모호해서 보류한 호수, 계획에
   * 들어가지 않은 호수가 대상이다. 출처 금지는 저장된 값만으로 알 수 있는 판정이라 호수 대응과 상관없이 적용한다. 호수 계획이 이미 처리한 칸(대응, 교체될 칸, 독립
   * 사용 중단 칸)과 운영 정정, 이미 사용 불가인 색은 제외한다. 이번 수집으로 만나지 못한 제품의 색은 이 검사가 닿지 않는다(일괄 재판정 명령의 몫).
   */
  private List<ProductShadeColor> leftoverDowngrades(
      CollectedProduct item, List<ProductShade> existingShades, List<ShadePlan> shadePlans) {
    Set<ProductShadeColor> handled = java.util.Collections.newSetFromMap(new IdentityHashMap<>());
    for (ShadePlan plan : shadePlans) {
      SlotPlan slots = plan.slots();
      if (slots == null) {
        continue;
      }
      slots.steps().stream()
          .map(SlotStep::existing)
          .filter(java.util.Objects::nonNull)
          .forEach(handled::add);
      handled.addAll(slots.removed());
      handled.addAll(slots.downgrades());
    }
    return existingShades.stream()
        .flatMap(shade -> shade.getColors().stream())
        .filter(slot -> !handled.contains(slot))
        .filter(
            slot ->
                slot.hasUsableColor()
                    && !slot.getReviewStatus().isOperatorDecision()
                    && !approvalPolicy.isSourceAllowed(item.source(), slot.getColorSource()))
        .toList();
  }

  /**
   * 그룹마다 기존 호수를 찾되, **한 기존 호수에 그룹이 둘 이상 대응하면 모두 모호한 것으로 본다.** 이전에 합쳤던 옵션이 다시 갈라진 경우처럼, 서로 다른 옵션의
   * 이름·색이 같은 호수에 반영되거나 대표 옵션을 서로 바꾸려는 충돌을 막는다.
   */
  private static List<ShadeMatcher.Match> matchAll(
      List<ShadeMatcher.Group> groups, List<ProductShade> existingShades) {
    List<ShadeMatcher.Match> matches = new ArrayList<>();
    Map<ProductShade, Integer> uses = new IdentityHashMap<>();
    for (ShadeMatcher.Group group : groups) {
      ShadeMatcher.Match match = ShadeMatcher.find(group, existingShades);
      matches.add(match);
      if (match instanceof ShadeMatcher.Update update) {
        uses.merge(update.existing(), 1, Integer::sum);
      }
    }
    for (int i = 0; i < matches.size(); i++) {
      if (matches.get(i) instanceof ShadeMatcher.Update update && uses.get(update.existing()) > 1) {
        matches.set(i, new ShadeMatcher.Ambiguous());
      }
    }
    return matches;
  }

  private ShadePlan planShade(
      CollectedProduct item,
      ShadeMatcher.Group group,
      ShadeMatcher.Match match,
      Set<String> usedNames) {
    CollectedShade rep = group.representative();
    Set<ImportReason> reasons = EnumSet.noneOf(ImportReason.class);
    if (group.mergeHeld()) {
      reasons.add(ImportReason.SHADE_MERGE_HELD);
    }
    String nameKey = CatalogTextNormalizer.normalize(rep.name());

    if (match instanceof ShadeMatcher.Ambiguous) {
      reasons.add(ImportReason.SHADE_AMBIGUOUS);
      return held(rep, reasons);
    }
    if (match instanceof ShadeMatcher.Create) {
      if (!usedNames.add(nameKey)) {
        reasons.add(ImportReason.SHADE_NAME_CONFLICT);
        return held(rep, reasons);
      }
      SlotPlan slots = planSlots(item, rep, null, reasons);
      return new ShadePlan(
          Action.CREATE,
          null,
          rep,
          null,
          rep.sourceOptionId(),
          aliasesOf(group),
          List.of(),
          slots,
          reasons);
    }

    ShadeMatcher.Update update = (ShadeMatcher.Update) match;
    ProductShade existing = update.existing();
    String renameTo = null;
    if (!existing.getName().equals(rep.name())) {
      boolean sameKey = existing.getNameNormalized().equals(nameKey);
      if (sameKey || usedNames.add(nameKey)) {
        renameTo = rep.name();
        if (!sameKey) {
          usedNames.remove(existing.getNameNormalized());
        }
      }
    }
    SlotPlan slots = planSlots(item, rep, existing, reasons);
    return new ShadePlan(
        Action.UPDATE,
        existing,
        rep,
        renameTo,
        update.newPrimaryOptionId(),
        update.addAliases(),
        update.removeAliases(),
        slots,
        reasons);
  }

  private static List<String> aliasesOf(ShadeMatcher.Group group) {
    return group.optionIds().stream().skip(1).toList();
  }

  private static ShadePlan held(CollectedShade rep, Set<ImportReason> reasons) {
    return new ShadePlan(
        Action.HELD, null, rep, null, null, List.of(), List.of(), null, Set.copyOf(reasons));
  }

  private SlotPlan planSlots(
      CollectedProduct item, CollectedShade rep, ProductShade existing, Set<ImportReason> reasons) {
    List<ProductShadeColor> existingSlots = existing == null ? List.of() : existing.getColors();
    boolean references = existing != null && referenceChecker.hasReferences(existing);
    SlotMatcher.Pairing pairing =
        SlotMatcher.match(
            existingSlots,
            rep.colors(),
            rep.slotOrderBasis(),
            references,
            colorProperties.layoutMatchMaxDeltaE());
    reasons.addAll(pairing.reasons());

    Instant collectedAt = item.collectedAt().toInstant();
    List<SlotStep> steps = new ArrayList<>();
    for (SlotMatcher.Pair pair : pairing.pairs()) {
      ReviewStatus judged = approvalPolicy.judge(item.source(), pair.incoming());
      ProductShadeColor old = pair.existing();
      boolean sourceAllowed =
          old == null
              || old.getColorSource() == null
              || approvalPolicy.isSourceAllowed(item.source(), old.getColorSource());
      ColorReplacementPolicy.Result result =
          ColorReplacementPolicy.decide(
              old, pair.incoming(), judged, rep.colorStatus(), collectedAt, sourceAllowed);
      boolean hadColor = old != null && old.getColor() != null;
      // 쓰던 색이 새 값으로 바뀌면서 사용 불가가 된 경우(금지된 출처의 색을 새로 받은 값이 못 넘음)도 내려간 것이다
      boolean wasUsable = hadColor && old.hasUsableColor();
      boolean downgradedByAdopt =
          result.decision() == Decision.ADOPT
              && wasUsable
              && result.status() != null
              && !result.status().isUsable();
      if (downgradedByAdopt) {
        reasons.add(ImportReason.COLOR_DOWNGRADED);
      }
      reasonOf(result.decision(), hadColor).ifPresent(reasons::add);
      steps.add(new SlotStep(pair.existing(), pair.incoming(), pair.sortOrder(), result));
    }
    List<ProductShadeColor> downgrades = standaloneDowngrades(item, existingSlots, pairing, steps);
    if (!downgrades.isEmpty()) {
      reasons.add(ImportReason.COLOR_DOWNGRADED);
    }
    return new SlotPlan(pairing.kind(), List.copyOf(steps), pairing.removed(), downgrades);
  }

  /**
   * 이번 수집에서 짝을 찾지 못한 기존 칸 중 **출처가 금지된 사용 중 색**을 찾는다. 칸 대응이 {@code NONE}·{@code KEPT}로 끝나도 출처 금지는
   * 저장된 값만으로 알 수 있는 판정이라 칸 배치와 상관없이 적용한다. 운영 정정과 이미 사용 불가인 색은 건드리지 않고, 지워질 칸({@code REPLACE_ALL})도
   * 제외한다.
   */
  private List<ProductShadeColor> standaloneDowngrades(
      CollectedProduct item,
      List<ProductShadeColor> existingSlots,
      SlotMatcher.Pairing pairing,
      List<SlotStep> steps) {
    Set<ProductShadeColor> handled = java.util.Collections.newSetFromMap(new IdentityHashMap<>());
    steps.stream().map(SlotStep::existing).filter(java.util.Objects::nonNull).forEach(handled::add);
    handled.addAll(pairing.removed());
    return existingSlots.stream()
        .filter(slot -> !handled.contains(slot))
        .filter(
            slot ->
                slot.hasUsableColor()
                    && !slot.getReviewStatus().isOperatorDecision()
                    && !approvalPolicy.isSourceAllowed(item.source(), slot.getColorSource()))
        .toList();
  }

  /** 기존 색이 있던 칸에서 유지하거나 교체했을 때만 사유를 남긴다. 새 칸이나 색이 없던 칸의 '못 찾음'은 사유가 아니다. */
  private static Optional<ImportReason> reasonOf(Decision decision, boolean hadColor) {
    if (decision == Decision.REPLACE) {
      return Optional.of(ImportReason.COLOR_REPLACED);
    }
    if (decision == Decision.DOWNGRADE) {
      return Optional.of(ImportReason.COLOR_DOWNGRADED);
    }
    if (!hadColor) {
      return Optional.empty();
    }
    return switch (decision) {
      case KEPT_BETTER -> Optional.of(ImportReason.COLOR_KEPT_BETTER);
      case KEPT_OPERATOR -> Optional.of(ImportReason.COLOR_KEPT_OPERATOR);
      case KEPT_ON_FAILURE -> Optional.of(ImportReason.COLOR_KEPT_ON_FAILURE);
      case KEPT_NOT_FOUND -> Optional.of(ImportReason.COLOR_KEPT_NOT_FOUND);
      case KEPT_STALE -> Optional.of(ImportReason.COLOR_KEPT_STALE);
      default -> Optional.empty();
    };
  }
}
