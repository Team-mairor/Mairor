package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.CollectedShade;
import com.mairor.backend.products.imports.CollectedProduct.ColorStatus;
import com.mairor.backend.products.imports.CollectedProduct.ShadeLink;
import com.mairor.backend.products.imports.CollectedProduct.SlotOrderBasis;
import com.mairor.backend.products.imports.CollectedProduct.VariantHints;
import java.time.Instant;
import java.util.List;

/** 가져오기 규칙 테스트가 같이 쓰는 데이터 만들기. 메모리 안에서 만들어서 DB 가 필요 없다. */
final class ImportTestData {

  static final Instant T0 = Instant.parse("2026-11-01T00:00:00Z");
  static final Instant T1 = Instant.parse("2026-11-02T00:00:00Z");
  static final Instant T2 = Instant.parse("2026-11-03T00:00:00Z");

  private ImportTestData() {}

  /** 아직 저장하지 않은 기존 호수. 칸은 {@link #slot}으로 더한다. */
  static ProductShade shade(String name) {
    ProductCategory eye = new ProductCategory("EYE", "아이", true, true, 3);
    ProductType palette = new ProductType("EYESHADOW_PALETTE", eye, "아이섀도 팔레트", 1);
    return new Product(palette, "Brand", "Palette").addShade(name, 1, null);
  }

  /** 기존 칸. {@code hex}가 {@code null}이면 색이 없는 칸이다. */
  static ProductShadeColor slot(
      ProductShade shade,
      int sortOrder,
      String name,
      NameSource nameSource,
      String hex,
      ColorSource source,
      ReviewStatus status,
      Instant collectedAt) {
    ProductShadeColor slot = shade.addColor(sortOrder, name, nameSource);
    if (hex != null) {
      slot.assignColor(source, hex, true, status, collectedAt);
    }
    return slot;
  }

  static ProductShadeColor namedSlot(ProductShade shade, int sortOrder, String name, String hex) {
    return slot(
        shade,
        sortOrder,
        name,
        NameSource.SITE_TEXT,
        hex,
        ColorSource.PRODUCT_PHOTO,
        ReviewStatus.AUTO_APPROVED,
        T1);
  }

  static ProductShadeColor unnamedSlot(ProductShade shade, int sortOrder, String hex) {
    return slot(
        shade,
        sortOrder,
        null,
        NameSource.NONE,
        hex,
        ColorSource.PRODUCT_PHOTO,
        ReviewStatus.AUTO_APPROVED,
        T1);
  }

  /** 새 수집 칸. */
  static CollectedColor color(
      int sortOrder,
      String name,
      NameSource nameSource,
      String hex,
      ColorSource source,
      ShadeLink link,
      Double quality) {
    return new CollectedColor(
        sortOrder, name, nameSource, hex, source, link, quality, "k/" + sortOrder);
  }

  static CollectedColor named(int sortOrder, String name, String hex) {
    return color(
        sortOrder,
        name,
        NameSource.SITE_TEXT,
        hex,
        ColorSource.PRODUCT_PHOTO,
        ShadeLink.OPTION_IMAGE,
        0.9);
  }

  static CollectedColor unnamed(int sortOrder, String hex) {
    return color(
        sortOrder,
        null,
        NameSource.NONE,
        hex,
        ColorSource.PRODUCT_PHOTO,
        ShadeLink.OPTION_IMAGE,
        0.9);
  }

  /** 색이 없는 새 칸. */
  static CollectedColor colorless(int sortOrder) {
    return color(sortOrder, null, NameSource.NONE, null, null, ShadeLink.UNVERIFIED, null);
  }

  static CollectedShade collectedShade(
      String optionId, String name, VariantHints hints, List<CollectedColor> colors) {
    return new CollectedShade(
        optionId,
        name,
        1,
        SlotOrderBasis.GRID,
        colors.stream().anyMatch(CollectedColor::hasColor)
            ? ColorStatus.EXTRACTED
            : ColorStatus.NOT_FOUND,
        hints,
        colors);
  }

  static VariantHints hints(String volume) {
    return new VariantHints(volume, null, null, null, null);
  }
}
