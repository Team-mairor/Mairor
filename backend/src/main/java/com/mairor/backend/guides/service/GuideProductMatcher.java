package com.mairor.backend.guides.service;

import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.products.collect.CollectCompletion;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.repository.ProductShadeColorRepository;
import com.mairor.backend.products.repository.ProductShadeRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.List;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

/** 가이드 단계의 제품, 호수, 색상 슬롯을 카탈로그와 대조한다. */
@Component
class GuideProductMatcher {

  private final ProductTypeRepository types;
  private final ProductRepository products;
  private final ProductShadeRepository shades;
  private final ProductShadeColorRepository colors;

  GuideProductMatcher(
      ProductTypeRepository types,
      ProductRepository products,
      ProductShadeRepository shades,
      ProductShadeColorRepository colors) {
    this.types = types;
    this.products = products;
    this.shades = shades;
    this.colors = colors;
  }

  Candidate match(JsonNode step) {
    String categoryCode = GuideQueryService.MATCH_CATEGORY.get(text(step.path("makeup")));
    if (categoryCode == null) {
      return Candidate.none(ReferenceMatchReason.CATEGORY_UNSUPPORTED);
    }
    JsonNode sourceProduct = step.path("product");
    if (!sourceProduct.isObject()) {
      return Candidate.none(ReferenceMatchReason.PRODUCT_NOT_PROVIDED);
    }
    String brand = text(sourceProduct.path("brand"));
    String name = text(sourceProduct.path("name"));
    if (brand == null || name == null) {
      return Candidate.none(ReferenceMatchReason.PRODUCT_DATA_INCOMPLETE);
    }

    ProductMatch productMatch;
    try {
      productMatch = findProduct(categoryCode, brand, name, text(sourceProduct.path("shade")));
    } catch (IllegalArgumentException e) {
      return Candidate.none(ReferenceMatchReason.PRODUCT_DATA_INCOMPLETE);
    }
    if (productMatch.product() == null) {
      return Candidate.none(productMatch.reason());
    }
    Product product = productMatch.product();

    String shadeName = text(sourceProduct.path("shade"));
    if (shadeName == null) {
      return Candidate.of(product, null, null, ReferenceMatchReason.SHADE_NOT_PROVIDED);
    }
    List<ProductShade> productShades =
        shades.findByProductIdOrderBySortOrderAscNameNormalizedAsc(product.getId());
    String normalizedShade;
    try {
      normalizedShade = CatalogTextNormalizer.normalize(shadeName);
    } catch (IllegalArgumentException e) {
      return Candidate.of(product, null, null, ReferenceMatchReason.SHADE_NOT_FOUND);
    }
    List<ProductShade> shadeMatches =
        productShades.stream()
            .filter(shade -> normalizedShade.equals(shade.getNameNormalized()))
            .toList();
    if (shadeMatches.isEmpty()) {
      // 영상 표기와 띄어쓰기만 다른 호수("02누카다미아" → "02 누카다미아")
      String compactShade = normalizedShade.replace(" ", "");
      shadeMatches =
          productShades.stream()
              .filter(shade -> shade.getNameNormalized() != null)
              .filter(shade -> compactShade.equals(shade.getNameNormalized().replace(" ", "")))
              .toList();
    }
    if (shadeMatches.size() != 1) {
      return Candidate.of(
          product,
          null,
          null,
          shadeMatches.isEmpty()
              ? ReferenceMatchReason.SHADE_NOT_FOUND
              : ReferenceMatchReason.SHADE_AMBIGUOUS);
    }

    ProductShade candidateShade = shadeMatches.getFirst();
    ProductShade shade = shades.findByIdForUpdate(candidateShade.getId()).orElse(null);
    if (shade == null) {
      return Candidate.of(product, null, null, ReferenceMatchReason.SHADE_NOT_FOUND);
    }
    List<ProductShadeColor> shadeColors =
        colors.findByShadeIdInOrderByShadeIdAscSortOrderAsc(List.of(shade.getId()));
    if (shadeColors.isEmpty()) {
      return Candidate.of(product, shade, null, ReferenceMatchReason.NO_COLOR_SLOTS);
    }
    if (shadeColors.size() == 1) {
      return Candidate.of(product, shade, shadeColors.getFirst(), null);
    }

    ProductShadeColor selected = explicitSlot(step, shadeColors);
    if (selected == null) {
      return Candidate.of(product, shade, null, ReferenceMatchReason.SLOT_UNIDENTIFIED);
    }
    return Candidate.of(product, shade, selected, null);
  }

  /** 후보가 여럿이면 영상의 호수가 있는 상품이 하나일 때만 선택한다. */
  private ProductMatch findProduct(
      String categoryCode, String brand, String name, String shadeName) {
    List<ProductType> allowedTypes =
        types.findByCategoryCodeOrderBySortOrderAscCodeAsc(categoryCode);
    List<String> typeCodes = allowedTypes.stream().map(ProductType::getCode).toList();
    List<Product> exact = products.findExact(typeCodes, brand, name);
    if (exact.size() == 1) {
      return ProductMatch.found(exact.getFirst());
    }
    if (exact.size() > 1) {
      return byShade(exact, shadeName);
    }

    List<Product> compact = products.findCompact(typeCodes, brand, name);
    if (compact.isEmpty()) {
      compact = products.findWithBrandPrefix(typeCodes, brand, name);
    }
    if (compact.isEmpty()) {
      compact = products.findByAlias(typeCodes, brand, name);
    }
    if (compact.size() == 1) {
      return ProductMatch.found(compact.getFirst());
    }
    return compact.isEmpty()
        ? ProductMatch.none(ReferenceMatchReason.PRODUCT_NOT_FOUND)
        : byShade(compact, shadeName);
  }

  private ProductMatch byShade(List<Product> candidates, String shadeName) {
    if (shadeName != null) {
      List<Product> holders =
          candidates.stream()
              .filter(
                  product ->
                      CollectCompletion.matchShade(
                              shades.findByProductIdOrderBySortOrderAscNameNormalizedAsc(
                                  product.getId()),
                              shadeName)
                          != null)
              .toList();
      if (holders.size() == 1) {
        return ProductMatch.found(holders.getFirst());
      }
    }
    return ProductMatch.none(ReferenceMatchReason.PRODUCT_AMBIGUOUS);
  }

  /** palette.color 는 설명 텍스트이므로 명시적 slotName/slotNumber 만 인정한다. */
  private static ProductShadeColor explicitSlot(JsonNode step, List<ProductShadeColor> candidates) {
    JsonNode palette = step.path("product").path("palette");
    String slotName = text(palette.path("slotName"));
    String slotNumber = text(palette.path("slotNumber"));
    if (slotName == null && slotNumber == null) {
      return null;
    }

    String normalizedName = null;
    if (slotName != null) {
      try {
        normalizedName = CatalogTextNormalizer.normalize(slotName);
      } catch (IllegalArgumentException e) {
        return null;
      }
    }
    Integer oneBasedNumber = parseSlotNumber(slotNumber);
    if (slotNumber != null && oneBasedNumber == null) {
      return null;
    }
    String nameKey = normalizedName;
    List<ProductShadeColor> matches =
        candidates.stream()
            .filter(color -> nameKey == null || nameKey.equals(color.getNameNormalized()))
            .filter(color -> oneBasedNumber == null || color.getSortOrder() == oneBasedNumber)
            .toList();
    return matches.size() == 1 ? matches.getFirst() : null;
  }

  private static Integer parseSlotNumber(String value) {
    if (value == null) {
      return null;
    }
    try {
      int parsed = Integer.parseInt(value);
      return parsed > 0 ? parsed : null;
    } catch (NumberFormatException e) {
      return null;
    }
  }

  private static String text(JsonNode value) {
    if (value == null || !value.isString()) {
      return null;
    }
    String result = value.asString().trim();
    return result.isEmpty() ? null : result;
  }

  private record ProductMatch(Product product, ReferenceMatchReason reason) {
    static ProductMatch found(Product product) {
      return new ProductMatch(product, null);
    }

    static ProductMatch none(ReferenceMatchReason reason) {
      return new ProductMatch(null, reason);
    }
  }

  record Candidate(
      Product product,
      ProductShade shade,
      ProductShadeColor color,
      ReferenceMatchLevel level,
      ReferenceMatchReason reason) {
    static Candidate none(ReferenceMatchReason reason) {
      return new Candidate(null, null, null, ReferenceMatchLevel.NONE, reason);
    }

    static Candidate of(
        Product product, ProductShade shade, ProductShadeColor color, ReferenceMatchReason reason) {
      ReferenceMatchLevel level =
          color != null
              ? ReferenceMatchLevel.SLOT
              : shade != null ? ReferenceMatchLevel.SHADE : ReferenceMatchLevel.PRODUCT;
      return new Candidate(product, shade, color, level, reason);
    }
  }
}
