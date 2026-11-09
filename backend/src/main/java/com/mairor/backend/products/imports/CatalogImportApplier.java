package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.CatalogImportItem;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.entity.SaleStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.CollectedShade;
import com.mairor.backend.products.imports.ColorReplacementPolicy.Decision;
import com.mairor.backend.products.imports.ImportPlan.ShadePlan;
import com.mairor.backend.products.imports.ImportPlan.ShadePlan.Action;
import com.mairor.backend.products.imports.ImportPlan.SlotPlan;
import com.mairor.backend.products.imports.ImportPlan.SlotStep;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import java.time.Instant;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.springframework.stereotype.Component;

/**
 * 판정이 끝난 계획({@link ImportPlan})을 DB 에 반영한다. **호출하는 쪽의 트랜잭션 안에서 엔티티만 바꾸고**, 트랜잭션을 열거나 커밋하지 않는다. 같은
 * 출처 제품의 잠금, 건 기록, 실패 격리는 {@link CatalogImportService}가 맡는다.
 *
 * <p>계획이 정한 대로만 바꾼다. 판정을 다시 하지 않는다.
 *
 * <ul>
 *   <li>{@code NEW}: 제품을 만들고 호수·칸·색을 만든다.
 *   <li>{@code UPDATE}: 제품의 이름·브랜드·출처·대표 이미지·판매 상태를 갱신하고, 호수는 계획대로 만들거나 고친다. 종류는 바꾸지 않는다. 새 수집에 대표
 *       이미지나 판매 상태가 없으면 기존 값을 지키지 않고 지우지도 않는다(기존 값을 그대로 둔다).
 *   <li>{@code STALE}·{@code AMBIGUOUS}·{@code UNCLASSIFIED}: 아무것도 바꾸지 않는다.
 * </ul>
 *
 * 호수 보류({@code HELD})는 건너뛴다. 색은 칸마다 판정 결과({@link Decision})대로 채우거나 유지하거나 사용 불가로 내린다. 색을 채우거나 바꾼 칸과
 * 새로 만든 칸은 이 건({@code item})과 근거 키로 출처를 연결한다. 값이 그대로인 칸은 원래 출처를 유지한다.
 *
 * <p>호수를 연결할 수 없는 카테고리(호수 선택이 없는 카테고리)의 제품은 호수를 반영하지 않는다. 계획 단계는 이 규칙을 보지 않으므로 여기서 걸러내고 {@link
 * Applied#extraReasons}로 남긴다.
 */
@Component
public class CatalogImportApplier {

  /** 호수를 연결할 수 없는 카테고리라 호수를 반영하지 않았다. 계획이 아니라 반영 단계에서 정해지는 사유다. */
  public static final String SHADES_NOT_SELECTABLE = "SHADES_NOT_SELECTABLE";

  private final ProductRepository productRepository;
  private final ProductTypeRepository typeRepository;

  public CatalogImportApplier(
      ProductRepository productRepository, ProductTypeRepository typeRepository) {
    this.productRepository = productRepository;
    this.typeRepository = typeRepository;
  }

  /**
   * 반영 결과.
   *
   * @param product 반영한 제품. 반영하지 않았으면 {@code null}
   * @param colorsApplied 저장하거나 바꾼 색 칸 수(새 색 채택, 교체, 사용 불가로 내림)
   * @param changedShades 서비스에 보이는 색(사용할 수 있는 색의 HEX)이 달라진 호수. 색을 저장해도 사용 불가라 보이는 색이 그대로면 들어가지 않는다
   * @param extraReasons 계획에 없던 사유
   */
  public record Applied(
      Product product,
      int colorsApplied,
      List<ProductShade> changedShades,
      Set<String> extraReasons) {

    static Applied nothing() {
      return new Applied(null, 0, List.of(), Set.of());
    }
  }

  /** 계획을 반영한다. */
  public Applied apply(ImportPlan plan, CatalogImportItem item) {
    return switch (plan.outcome()) {
      case STALE, AMBIGUOUS, UNCLASSIFIED -> Applied.nothing();
      case NEW -> applyNew(plan, item);
      case UPDATE -> applyUpdate(plan, item);
    };
  }

  private Applied applyNew(ImportPlan plan, CatalogImportItem item) {
    CollectedProduct collected = plan.item();
    ProductType type = typeRepository.getReferenceById(plan.type().typeCode());
    Product product = new Product(type, collected.brand(), plan.cleanedName());
    recordProduct(product, collected, null);
    productRepository.save(product);
    return applyShades(product, plan, item);
  }

  private Applied applyUpdate(ImportPlan plan, CatalogImportItem item) {
    CollectedProduct collected = plan.item();
    Product product = plan.existing();
    if (!product.getBrand().equals(collected.brand())) {
      product.changeBrand(collected.brand());
    }
    if (!product.getName().equals(plan.cleanedName())) {
      product.rename(plan.cleanedName());
    }
    recordProduct(product, collected, product);
    return applyShades(product, plan, item);
  }

  private static void recordProduct(Product product, CollectedProduct collected, Product previous) {
    product.recordSource(
        collected.source(),
        collected.sourceProductId(),
        collected.sourceUrl(),
        collected.collectedAt().toInstant());
    String image =
        collected.imageUrl() != null || previous == null
            ? collected.imageUrl()
            : previous.getImageUrl();
    SaleStatus saleStatus =
        collected.saleStatus() != null || previous == null
            ? collected.saleStatus()
            : previous.getSaleStatus();
    product.recordListing(image, saleStatus);
  }

  private Applied applyShades(Product product, ImportPlan plan, CatalogImportItem item) {
    if (!plan.shades().isEmpty() && !product.getCategory().isShadeSelectable()) {
      return new Applied(product, 0, List.of(), Set.of(SHADES_NOT_SELECTABLE));
    }
    Instant collectedAt = plan.item().collectedAt().toInstant();
    Counter counter = new Counter();
    for (ShadePlan shadePlan : plan.shades()) {
      if (shadePlan.action() == Action.HELD) {
        continue;
      }
      ProductShade shade =
          shadePlan.action() == Action.CREATE
              ? createShade(product, shadePlan)
              : updateShade(shadePlan);
      applySlots(shade, shadePlan.slots(), item, collectedAt, counter);
    }
    for (ProductShadeColor leftover : plan.downgrades()) {
      downgrade(leftover, counter);
    }
    return new Applied(product, counter.colors, List.copyOf(counter.changed), Set.of());
  }

  private static ProductShade createShade(Product product, ShadePlan plan) {
    CollectedShade collected = plan.shade();
    ProductShade shade = product.addShade(collected.name(), collected.sortOrder(), null);
    shade.changeSourceOptionId(plan.newPrimaryOptionId());
    plan.addAliases().forEach(shade::addOptionAlias);
    return shade;
  }

  private static ProductShade updateShade(ShadePlan plan) {
    ProductShade shade = plan.existing();
    if (plan.renameTo() != null) {
      shade.rename(plan.renameTo());
    }
    shade.changeSortOrder(plan.shade().sortOrder());
    plan.removeAliases().forEach(shade::removeOptionAlias);
    if (plan.newPrimaryOptionId() != null) {
      shade.changeSourceOptionId(plan.newPrimaryOptionId());
    }
    plan.addAliases().forEach(shade::addOptionAlias);
    return shade;
  }

  private static void applySlots(
      ProductShade shade,
      SlotPlan slots,
      CatalogImportItem item,
      Instant collectedAt,
      Counter counter) {
    if (slots == null) {
      return;
    }
    for (ProductShadeColor removed : slots.removed()) {
      if (visibleHex(removed) != null) {
        counter.markChanged(shade);
      }
      shade.removeColor(removed);
    }
    for (SlotStep step : slots.steps()) {
      applyStep(shade, step, item, collectedAt, counter);
    }
    for (ProductShadeColor slot : slots.downgrades()) {
      downgrade(slot, counter);
    }
  }

  /** 칸 하나를 반영한다. 색을 저장하거나 바꿨으면 반영 수에 세고, 서비스에 보이는 색(사용 가능한 색의 HEX)이 달라졌으면 그 호수를 바뀐 호수로 표시한다. */
  private static void applyStep(
      ProductShade shade,
      SlotStep step,
      CatalogImportItem item,
      Instant collectedAt,
      Counter counter) {
    CollectedColor incoming = step.incoming();
    ProductShadeColor slot = step.existing();
    boolean created = slot == null;
    String before = created ? null : visibleHex(slot);
    if (created) {
      slot = shade.addColor(step.sortOrder(), incoming.name(), incoming.nameSource());
    } else {
      slot.changeSortOrder(step.sortOrder());
      if (incoming.name() != null) {
        slot.changeName(incoming.name(), incoming.nameSource());
      }
    }
    Decision decision = step.color().decision();
    ReviewStatus status = step.color().status();
    switch (decision) {
      case ADOPT, REPLACE -> {
        slot.assignColor(incoming.colorSource(), incoming.hex(), true, status, collectedAt);
        slot.linkSource(item, incoming.evidenceKey());
      }
      case DOWNGRADE -> slot.changeReviewStatus(ReviewStatus.BELOW_THRESHOLD);
      default -> {
        // 값이 그대로이거나 유지한 칸은 원래 출처를 지킨다. 새로 만든 칸만 이 건에서 왔다고 남긴다
      }
    }
    if (created && slot.getSourceItem() == null) {
      slot.linkSource(item, incoming.evidenceKey());
    }
    if (decision.changesColor()) {
      counter.colors++;
    }
    if (!Objects.equals(before, visibleHex(slot))) {
      counter.markChanged(shade);
    }
  }

  /** 서비스에 보이는 색. 사용할 수 있는 색의 HEX 이고, 없거나 사용 불가면 {@code null}. */
  private static String visibleHex(ProductShadeColor slot) {
    return slot.hasUsableColor() ? slot.getColor().getHex() : null;
  }

  /** 사용 중이던 색을 사용 불가로 내린다(값은 남긴다). 이미 사용 불가이거나 색이 없으면 아무것도 하지 않는다. */
  private static boolean downgrade(ProductShadeColor slot, Counter counter) {
    if (!slot.hasUsableColor()) {
      return false;
    }
    slot.changeReviewStatus(ReviewStatus.BELOW_THRESHOLD);
    counter.colors++;
    counter.markChanged(slot.getShade());
    return true;
  }

  private static final class Counter {
    int colors;
    final Set<ProductShade> changed = Collections.newSetFromMap(new IdentityHashMap<>());

    void markChanged(ProductShade shade) {
      changed.add(shade);
    }
  }
}
