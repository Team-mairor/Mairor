package com.mairor.backend.products.collect;

import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.repository.ProductShadeRepository;
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

  private final ProductRepository products;
  private final ProductShadeRepository shades;
  private final ProductCategoryRepository categories;

  public CollectCompletion(
      ProductRepository products,
      ProductShadeRepository shades,
      ProductCategoryRepository categories) {
    this.products = products;
    this.shades = shades;
    this.categories = categories;
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
    List<Product> compact = products.findCompact(types, brand, name);
    return compact.isEmpty() ? products.findByAlias(types, brand, name) : compact;
  }

  /** 이름으로 찾은 제품들로 판정한다. 없으면 {@code null}(카탈로그에 아직 없음). */
  public Judgment judge(List<Product> candidates, String categoryCode, String shadeName) {
    if (candidates.isEmpty()) {
      return null;
    }
    if (candidates.size() > 1) {
      return Judgment.unresolved(MULTIPLE_CANDIDATES, null);
    }
    Product product = candidates.getFirst();
    if (missingShade(product, categoryCode, shadeName)) {
      return Judgment.unresolved(SHADE_NOT_FOUND, product);
    }
    return Judgment.resolved(product);
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

  /** 제품에서 이름이 정규화 일치하는 호수. 없으면 {@code null}. */
  public ProductShade findShade(UUID productId, String shadeName) {
    String normalized = CatalogTextNormalizer.normalize(shadeName);
    return shades.findByProductIdOrderBySortOrderAscNameNormalizedAsc(productId).stream()
        .filter(shade -> normalized.equals(shade.getNameNormalized()))
        .findFirst()
        .orElse(null);
  }
}
