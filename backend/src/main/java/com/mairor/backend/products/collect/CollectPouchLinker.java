package com.mairor.backend.products.collect;

import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchCatalogRepository;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.products.entity.CatalogCollectRequestUser;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.repository.CatalogCollectRequestUserRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 해결된 수집 요청의 직접 입력 파우치 항목을 카탈로그 제품·호수에 연결한다(S15P31A306-517). 회원에게 묻지 않으므로 아래를 모두 만족할 때만 바꾸고, 하나라도
 * 아니면 항목을 그대로 둔다.
 *
 * <ul>
 *   <li>항목이 아직 직접 입력이고, 요청 뒤로 회원이 고치지 않았다(요청 때 저장한 수정 시각과 같다)
 *   <li>소분류·브랜드·제품명(정규화 또는 공백 무시)이 일치하는 카탈로그 제품이 정확히 하나다
 *   <li>호수를 고르는 카테고리면 회원이 적은 호수가 그 제품에 있다. 호수를 적지 않았으면 연결하지 않는다
 *   <li>바뀐 브랜드·제품명·호수가 회원의 다른 항목과 겹치지 않는다(같은 제품·호수가 이미 파우치에 있음)
 * </ul>
 *
 * <p>회원 행을 먼저 잠그고(등록·수정과 같은 순서) 항목을 잠근 뒤 조건을 다시 확인한다. 연결하면 그 회원의 {@code pouchVersion}을 올린다. 회원마다 따로
 * 트랜잭션이라 한 회원의 실패가 다른 회원에게 번지지 않는다.
 */
@Service
public class CollectPouchLinker {

  static final String LINKED = "LINKED";

  private final CatalogCollectRequestUserRepository requesters;
  private final PouchItemRepository items;
  private final PouchVersionRepository versions;
  private final PouchCatalogRepository catalog;
  private final CollectCompletion completion;

  public CollectPouchLinker(
      CatalogCollectRequestUserRepository requesters,
      PouchItemRepository items,
      PouchVersionRepository versions,
      PouchCatalogRepository catalog,
      CollectCompletion completion) {
    this.requesters = requesters;
    this.items = items;
    this.versions = versions;
    this.catalog = catalog;
    this.completion = completion;
  }

  /**
   * 요청자 한 명의 항목을 판정해 연결하고 결과를 그 행에 남긴다.
   *
   * @return 남긴 결과(LINKED 또는 연결하지 않은 사유). 이미 판정한 행이면 그 결과
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public String link(UUID requesterId) {
    CatalogCollectRequestUser requester = requesters.findById(requesterId).orElseThrow();
    if (requester.getLinkResult() != null) {
      return requester.getLinkResult();
    }
    String result = decideAndLink(requester);
    requester.recordLink(result);
    return result;
  }

  private String decideAndLink(CatalogCollectRequestUser requester) {
    if (requester.getPouchItemId() == null) {
      return "ITEM_DELETED";
    }
    UUID userId = requester.getUserId();
    if (versions.lockByUserId(userId).isEmpty()) {
      return "USER_DELETED";
    }
    Optional<PouchItem> locked =
        items.findByIdAndUserIdForUpdate(requester.getPouchItemId(), userId);
    if (locked.isEmpty()) {
      return "ITEM_DELETED";
    }
    PouchItem item = locked.get();
    if (item.getRegistrationMode() != RegistrationMode.MANUAL) {
      return "NOT_MANUAL";
    }
    if (!sameMoment(item.getUpdatedAt(), requester.getPouchItemUpdatedAt())) {
      return "ITEM_CHANGED";
    }

    List<Product> candidates =
        completion.productsByName(item.getType(), item.getBrand(), item.getName());
    if (candidates.size() != 1) {
      return candidates.isEmpty() ? "PRODUCT_NOT_FOUND" : CollectCompletion.MULTIPLE_CANDIDATES;
    }
    Product product = candidates.getFirst();
    boolean shadeSelectable = product.getCategory().isShadeSelectable();
    UUID shadeId = null;
    if (shadeSelectable) {
      if (item.getShadeName() == null) {
        return "SHADE_REQUIRED";
      }
      ProductShade shade = completion.findShade(product.getId(), item.getShadeName());
      if (shade == null) {
        return CollectCompletion.SHADE_NOT_FOUND;
      }
      shadeId = shade.getId();
    }

    List<Object[]> rows = catalog.findSelection(product.getId(), shadeId);
    if (rows.isEmpty()) {
      return "PRODUCT_NOT_FOUND";
    }
    Object[] row = rows.getFirst();
    String brand = (String) row[1];
    String name = (String) row[2];
    String shadeName = shadeSelectable ? (String) row[7] : null;
    if (items.existsByUserIdAndBrandNormalizedAndNameNormalizedAndShadeNameNormalizedAndIdNot(
        userId,
        CatalogTextNormalizer.normalize(brand),
        CatalogTextNormalizer.normalize(name),
        shadeName == null ? "" : CatalogTextNormalizer.normalize(shadeName),
        item.getId())) {
      return "ALREADY_IN_POUCH";
    }

    String colorHex = (String) row[8];
    PouchColor catalogColor =
        colorHex == null ? null : PouchColor.catalog(colorHex, Boolean.TRUE.equals(row[9]));
    item.linkToCatalog(
        product.getId(),
        shadeId,
        (String) row[3],
        (String) row[4],
        brand,
        name,
        shadeName,
        catalogColor);
    items.saveAndFlush(item);
    versions.increment(userId);
    return LINKED;
  }

  /** DB 는 마이크로초까지 저장한다. 엔티티 시각과 비교할 때 그 아래는 버린다. */
  private static boolean sameMoment(Instant a, Instant b) {
    return a != null
        && b != null
        && Objects.equals(a.truncatedTo(ChronoUnit.MICROS), b.truncatedTo(ChronoUnit.MICROS));
  }
}
