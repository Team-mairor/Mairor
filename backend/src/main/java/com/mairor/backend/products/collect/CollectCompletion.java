package com.mairor.backend.products.collect;

import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.repository.ProductShadeColorRepository;
import com.mairor.backend.products.repository.ProductShadeRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * 수집 요청의 부족 정보가 카탈로그에서 풀렸는지 판정한다. 접수 때(수집 전)와 결과가 온 뒤(적재 후) 같은 규칙을 쓴다.
 *
 * <p>제품을 찾았다는 것만으로 끝내지 않는다. 일치 제품이 정확히 하나이고, 호수를 고르는 카테고리에서 회원이 호수를 적었으면 그 호수도 있어야 해결이다.
 */
@Component
public class CollectCompletion {

  static final String MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES";
  static final String SHADE_NOT_FOUND = "SHADE_NOT_FOUND";
  static final String NOT_IN_CATALOG = "NOT_IN_CATALOG";
  static final String TARGET_GONE = "TARGET_GONE";
  static final String NO_COLOR_SLOTS = "NO_COLOR_SLOTS";
  static final String COLOR_NOT_USABLE = "COLOR_NOT_USABLE";
  static final String SLOT_NOT_FOUND = "SLOT_NOT_FOUND";

  private final ProductRepository products;
  private final ProductShadeRepository shades;
  private final ProductCategoryRepository categories;
  private final ProductTypeRepository types;
  private final ProductShadeColorRepository colors;

  public CollectCompletion(
      ProductRepository products,
      ProductShadeRepository shades,
      ProductCategoryRepository categories,
      ProductTypeRepository types,
      ProductShadeColorRepository colors) {
    this.products = products;
    this.shades = shades;
    this.categories = categories;
    this.types = types;
    this.colors = colors;
  }

  /** 판정. 해결이면 {@code product}가 있다. */
  public record Judgment(CollectRequestStatus status, String reason, Product product) {
    static Judgment resolved(Product product) {
      return new Judgment(CollectRequestStatus.RESOLVED, null, product);
    }

    static Judgment unresolved(String reason, Product product) {
      return new Judgment(CollectRequestStatus.UNRESOLVED, reason, product);
    }
  }

  /** 소분류·브랜드가 같고 제품명이 정규화 일치하는 제품. 없으면 공백 무시 일치, 그래도 없으면 회원이 쓴 이름의 별칭. */
  public List<Product> productsByName(String typeCode, String brand, String name) {
    List<String> types = List.of(typeCode);
    List<Product> exact = products.findExact(types, brand, name);
    if (!exact.isEmpty()) {
      return exact;
    }
    return fallbackByName(types, brand, name);
  }

  /** 정확 일치가 없을 때: 공백 무시 → 사이트가 앞에 브랜드를 붙인 이름 → 회원이 쓴 이름의 별칭. */
  private List<Product> fallbackByName(List<String> types, String brand, String name) {
    List<Product> compact = products.findCompact(types, brand, name);
    if (compact.isEmpty()) {
      compact = products.findWithBrandPrefix(types, brand, name);
    }
    return compact.isEmpty() ? products.findByAlias(types, brand, name) : compact;
  }

  /**
   * 이름으로 찾은 제품들로 판정한다. 없으면 {@code null}(카탈로그에 아직 없음).
   *
   * <p>후보가 여럿이면 호수를 고르는 카테고리에서 회원이 적은 호수가 있는 상품으로 좁힌다(시리즈별 상품으로 나뉜 제품). 호수가 있는 상품이 하나면 그것이고, 아무
   * 상품에도 없으면 호수 없음, 여럿에 있거나 호수를 적지 않았으면 후보 여럿이다.
   */
  public Judgment judge(List<Product> candidates, String categoryCode, String shadeName) {
    if (candidates.isEmpty()) {
      return null;
    }
    if (candidates.size() > 1) {
      List<Product> holders = narrowByShade(candidates, categoryCode, shadeName);
      if (holders.size() == 1) {
        candidates = holders;
      } else if (holders.isEmpty() && shadeNarrows(categoryCode, shadeName)) {
        return Judgment.unresolved(SHADE_NOT_FOUND, null);
      } else {
        return Judgment.unresolved(MULTIPLE_CANDIDATES, null);
      }
    }
    Product product = candidates.getFirst();
    if (missingShade(product, categoryCode, shadeName)) {
      return Judgment.unresolved(SHADE_NOT_FOUND, product);
    }
    return Judgment.resolved(product);
  }

  /** 호수로 상품을 좁힐 수 있는가: 호수를 고르는 카테고리이고 호수를 적었다. */
  private boolean shadeNarrows(String categoryCode, String shadeName) {
    return shadeName != null
        && categoryCode != null
        && categories.findById(categoryCode).map(c -> c.isShadeSelectable()).orElse(false);
  }

  /** 후보 중 요청한 호수가 있는 상품. 호수로 좁힐 수 없는 경우(호수를 안 적었거나 호수를 고르지 않는 카테고리)에는 후보를 그대로 돌려준다. */
  public List<Product> narrowByShade(
      List<Product> candidates, String categoryCode, String shadeName) {
    if (!shadeNarrows(categoryCode, shadeName)) {
      return candidates;
    }
    return candidates.stream().filter(p -> findShade(p.getId(), shadeName) != null).toList();
  }

  /** 후보 중 하나라도 요청한 호수가 있는가. 호수로 좁힐 수 없으면 있다고 본다. */
  public boolean anyHasShade(List<Product> candidates, String categoryCode, String shadeName) {
    return !shadeNarrows(categoryCode, shadeName)
        || !narrowByShade(candidates, categoryCode, shadeName).isEmpty();
  }

  /** 호수를 고르는 카테고리에서 회원이 적은 호수가 그 제품에 없는가. 호수를 적지 않았으면 없다고 보지 않는다. */
  public boolean missingShade(Product product, String categoryCode, String shadeName) {
    if (shadeName == null || categoryCode == null) {
      return false;
    }
    boolean selectable =
        categories.findById(categoryCode).map(c -> c.isShadeSelectable()).orElse(false);
    return selectable && findShade(product.getId(), shadeName) == null;
  }

  /**
   * 제품에서 이름이 정규화 일치하는 호수. 없으면 공백을 뺀 이름이 같은 호수가 하나뿐일 때 그 호수("02누카다미아" → "02 누카다미아"). 없거나 공백을 빼면 여럿이
   * 같아지면 {@code null}.
   */
  public ProductShade findShade(UUID productId, String shadeName) {
    return matchShade(
        shades.findByProductIdOrderBySortOrderAscNameNormalizedAsc(productId), shadeName);
  }

  /** {@link #findShade}의 비교 규칙. 영상 대조도 같은 규칙을 쓴다. */
  public static ProductShade matchShade(List<ProductShade> candidates, String shadeName) {
    String normalized;
    try {
      normalized = CatalogTextNormalizer.normalize(shadeName);
    } catch (IllegalArgumentException e) {
      return null;
    }
    List<ProductShade> exact =
        candidates.stream().filter(s -> normalized.equals(s.getNameNormalized())).toList();
    if (!exact.isEmpty()) {
      return exact.size() == 1 ? exact.getFirst() : null;
    }
    String compact = normalized.replace(" ", "");
    List<ProductShade> spaced =
        candidates.stream()
            .filter(s -> s.getNameNormalized() != null)
            .filter(s -> compact.equals(s.getNameNormalized().replace(" ", "")))
            .toList();
    return spaced.size() == 1 ? spaced.getFirst() : null;
  }

  /** 같은 카테고리의 모든 소분류에서 브랜드·제품명이 일치하는 제품(정확 → 공백 무시 → 별칭). 영상 제품은 소분류를 모른다. */
  public List<Product> productsInCategory(String categoryCode, String brand, String name) {
    List<String> typeCodes =
        types.findByCategoryCodeOrderBySortOrderAscCodeAsc(categoryCode).stream()
            .map(ProductType::getCode)
            .toList();
    List<Product> exact = products.findExact(typeCodes, brand, name);
    if (!exact.isEmpty()) {
      return exact;
    }
    return fallbackByName(typeCodes, brand, name);
  }

  /**
   * 영상 분석 요청(S15P31A306-518)의 부족분이 카탈로그에서 풀렸는지 판정한다. 부족 유형마다 완료 조건이 다르다. 제품을 찾았다는 것만으로 호수·색 요청을 끝내지
   * 않는다.
   *
   * <ul>
   *   <li>제품 없음: 같은 카테고리에서 일치 제품이 정확히 하나
   *   <li>호수 없음: 대상 제품에 영상의 호수명과 일치하는 호수
   *   <li>색 없음(대상 칸): 그 칸에 쓸 수 있는 색. 다른 칸에만 색이 생기면 해결이 아니다
   *   <li>색 없음(대상 호수, 칸 행이 없던 경우): 칸이 하나면 그 칸, 영상 칸 이름·번호가 있으면 맞는 칸에 쓸 수 있는 색. 팔레트인데 영상 칸 이름·번호가
   *       없으면 칸 행이 생긴 것으로 해결(어느 칸을 썼는지는 수집이 아니라 대조가 정한다)
   * </ul>
   *
   * @param candidates 제품 없음 요청의 후보(별칭까지 본 뒤). 다른 유형은 쓰지 않는다
   */
  public Judgment judgeGuide(CatalogCollectRequest request, List<Product> candidates) {
    CatalogCollectRequest.Target target = request.getTarget();
    return switch (request.getGap()) {
      case PRODUCT_MISSING -> {
        // 시리즈별 상품이 여럿이면 영상의 호수가 있는 상품으로 좁힌다. 호수가 있는지는 요구하지 않는다(그건 대조가 다음 부족분으로 본다)
        List<Product> found = candidates;
        if (found.size() > 1) {
          List<Product> holders =
              narrowByShade(found, request.getCategoryCode(), request.getShadeName());
          found = holders.size() == 1 ? holders : found;
        }
        Judgment judgment = judge(found, null, null);
        yield judgment == null ? Judgment.unresolved(NOT_IN_CATALOG, null) : judgment;
      }
      case SHADE_MISSING -> {
        Product product =
            target.productId() == null ? null : products.findById(target.productId()).orElse(null);
        if (product == null) {
          yield Judgment.unresolved(TARGET_GONE, null);
        }
        yield request.getShadeName() != null
                && findShade(product.getId(), request.getShadeName()) != null
            ? Judgment.resolved(product)
            : Judgment.unresolved(SHADE_NOT_FOUND, product);
      }
      case COLOR_MISSING -> judgeColor(target);
    };
  }

  private Judgment judgeColor(CatalogCollectRequest.Target target) {
    if (target.shadeId() == null) {
      return Judgment.unresolved(TARGET_GONE, null);
    }
    List<ProductShadeColor> slots =
        colors.findByShadeIdInOrderByShadeIdAscSortOrderAsc(List.of(target.shadeId()));
    if (target.colorId() != null) {
      return slots.stream()
          .filter(slot -> slot.getId().equals(target.colorId()))
          .findFirst()
          .map(
              slot ->
                  slot.hasUsableColor()
                      ? Judgment.resolved(null)
                      : Judgment.unresolved(COLOR_NOT_USABLE, null))
          .orElse(Judgment.unresolved(TARGET_GONE, null));
    }
    if (slots.isEmpty()) {
      return Judgment.unresolved(NO_COLOR_SLOTS, null);
    }
    if (slots.size() == 1) {
      return slots.getFirst().hasUsableColor()
          ? Judgment.resolved(null)
          : Judgment.unresolved(COLOR_NOT_USABLE, null);
    }
    if (target.slotLabel() == null) {
      return Judgment.resolved(null);
    }
    List<ProductShadeColor> matching =
        slots.stream().filter(slot -> matchesLabel(slot, target.slotLabel())).toList();
    if (matching.size() != 1) {
      return Judgment.unresolved(SLOT_NOT_FOUND, null);
    }
    return matching.getFirst().hasUsableColor()
        ? Judgment.resolved(null)
        : Judgment.unresolved(COLOR_NOT_USABLE, null);
  }

  /** 영상의 칸 이름(정규화 일치) 또는 칸 번호(1부터)와 맞는 칸인가. */
  private static boolean matchesLabel(ProductShadeColor slot, String label) {
    String trimmed = label.trim();
    if (trimmed.chars().allMatch(Character::isDigit) && !trimmed.isEmpty()) {
      return slot.getSortOrder() == Integer.parseInt(trimmed);
    }
    try {
      return CatalogTextNormalizer.normalize(trimmed).equals(slot.getNameNormalized());
    } catch (IllegalArgumentException e) {
      return false;
    }
  }
}
