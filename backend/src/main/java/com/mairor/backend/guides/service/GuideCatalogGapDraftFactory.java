package com.mairor.backend.guides.service;

import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CollectGap;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

/** 가이드 단계의 카탈로그 부족 유형을 판정하고 수집 요청 초안을 만든다. */
@Component
class GuideCatalogGapDraftFactory {

  CatalogCollectRequest create(GuideStepProductLink link, JsonNode step) {
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
    String category = GuideQueryService.MATCH_CATEGORY.get(text(step.path("makeup")));
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

  /** 이미 있는 제품을 다시 수집한다. 출처 URL이 있으면 해당 페이지를 대상으로 한다. */
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

  private static String normalizedCompact(String value) {
    return normalized(value).replace(" ", "");
  }

  private static String normalized(String value) {
    try {
      return CatalogTextNormalizer.normalize(value);
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
