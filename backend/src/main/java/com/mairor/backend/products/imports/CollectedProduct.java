package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.SaleStatus;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * 수집기가 보낸 상품 한 건 ({@code shared/catalog-import/README.md}의 {@code CollectedProduct}). {@link
 * CollectedProductReader}가 검증을 통과시킨 값만 이 모양이 된다.
 *
 * <p>문자열은 앞뒤 공백을 지운 값이고, 상품명·호수명은 사이트 원문 그대로다(판매 배지 정리는 {@link CatalogNameCleaner}). {@code
 * sourceProductId}와 {@code sourceOptionId}는 근거 키에 쓰이므로 가공하지 않는다.
 */
public record CollectedProduct(
    int contractVersion,
    String itemKey,
    String source,
    String sourceProductId,
    String sourceUrl,
    String sourceLanguage,
    OffsetDateTime collectedAt,
    String brand,
    String name,
    List<String> sourceCategoryPath,
    String categoryHint,
    String typeHint,
    String imageUrl,
    SaleStatus saleStatus,
    List<CollectedShade> shades,
    List<String> warnings) {

  /** 호수 하나. 호수가 없는 상품은 {@code shades}가 빈 목록이다. */
  public record CollectedShade(
      String sourceOptionId,
      String name,
      int sortOrder,
      SlotOrderBasis slotOrderBasis,
      ColorStatus colorStatus,
      VariantHints variantHints,
      List<CollectedColor> colors) {

    /** 구분 정보를 보내지 않았으면 '모름'이라 자동 병합하지 않는다. */
    public boolean hasVariantHints() {
      return variantHints != null;
    }
  }

  /**
   * 같은 호수를 합칠지 판단하는 구분 정보. 값은 사이트에 적힌 원문이고, 사이트에 그 구분 정보가 없으면 {@code null}이다. 이 객체 자체가 없으면 수집하지
   * 않았다는 뜻이다.
   */
  public record VariantHints(
      String volume,
      String composition,
      String formulation,
      Map<String, String> optionAttributes,
      String listPrice) {}

  /** 색 칸 하나. 색을 못 구했으면 {@code hex}·{@code colorSource}·{@code colorQuality}가 {@code null}이다. */
  public record CollectedColor(
      int sortOrder,
      String name,
      NameSource nameSource,
      String hex,
      ColorSource colorSource,
      ShadeLink shadeLink,
      Double colorQuality,
      String evidenceKey) {

    public boolean hasColor() {
      return hex != null;
    }
  }

  /** 칸 순서를 어떻게 정했나. */
  public enum SlotOrderBasis {
    /** 수집기가 정한 방향의 행→열 순서. */
    GRID,
    UNKNOWN
  }

  /** 호수의 색 추출 결과. {@code FAILED}는 기존 색을 지우지 않는다. */
  public enum ColorStatus {
    /** 색이 있는 칸이 하나 이상이다. */
    EXTRACTED,
    /** 근거가 될 이미지나 값이 없다. */
    NOT_FOUND,
    /** 다운로드나 추출 중 오류가 났다. */
    FAILED
  }

  /** 사진과 호수를 이은 근거. */
  public enum ShadeLink {
    OPTION_IMAGE,
    SINGLE_SHADE_PRODUCT,
    LABEL_IN_IMAGE,
    UNVERIFIED
  }
}
