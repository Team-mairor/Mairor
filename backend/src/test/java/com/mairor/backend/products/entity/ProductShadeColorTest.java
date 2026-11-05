package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ProductShadeColorTest {

  private ProductShade shade;

  @BeforeEach
  void setUp() {
    ProductCategory eye = new ProductCategory("EYE", "아이", true, true, 3);
    ProductType palette = new ProductType("EYESHADOW_PALETTE", eye, "아이섀도 팔레트", 1);
    shade = new Product(palette, "Brand", "Palette").addShade("01 Dusk", 1, null);
  }

  @Test
  void slotWithoutNameKeepsNameSourceNone() {
    ProductShadeColor slot = shade.addColor(1, null, NameSource.NONE);

    assertThat(slot.getName()).isNull();
    assertThat(slot.getNameNormalized()).isNull();
    assertThat(slot.getNameSource()).isEqualTo(NameSource.NONE);
    assertThat(slot.getColor()).isNull();
    assertThat(slot.getReviewStatus()).isNull();
    assertThat(slot.hasUsableColor()).isFalse();
  }

  @Test
  void slotNameNeedsARealSourceAndIsNormalized() {
    ProductShadeColor slot = shade.addColor(1, "  Matte  Sand ", NameSource.SITE_TEXT);

    assertThat(slot.getName()).isEqualTo("  Matte  Sand ");
    assertThat(slot.getNameNormalized()).isEqualTo("matte sand");
    assertThat(slot.getNameSource()).isEqualTo(NameSource.SITE_TEXT);
  }

  @Test
  void nameAndNameSourceMustAgree() {
    // 순서대로 센 번호는 이름이 아니다. 이름이 없으면 근거도 NONE 이다
    assertThatThrownBy(() -> shade.addColor(1, null, NameSource.SITE_TEXT))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> shade.addColor(1, "Sand", NameSource.NONE))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> shade.addColor(1, "   ", NameSource.IMAGE_PRINT))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                shade.addColor(
                    1, "a".repeat(ProductShadeColor.NAME_MAX_LENGTH + 1), NameSource.SITE_TEXT))
        .isInstanceOf(IllegalArgumentException.class);
    assertThat(shade.getColors()).isEmpty();
  }

  @Test
  void slotOrderIsUniqueInAShade() {
    shade.addColor(1, null, NameSource.NONE);

    assertThatThrownBy(() -> shade.addColor(1, null, NameSource.NONE))
        .isInstanceOf(IllegalArgumentException.class);
    assertThat(shade.addColor(2, null, NameSource.NONE).getSortOrder()).isEqualTo(2);
  }

  @Test
  void photoAndModelAndSiteValueColorsAreAlwaysEstimated() {
    Instant at = Instant.parse("2026-11-05T01:00:00Z");
    for (ColorSource source :
        List.of(
            ColorSource.SOURCE_VALUE,
            ColorSource.SWATCH_CHIP,
            ColorSource.PRODUCT_PHOTO,
            ColorSource.WEB_PHOTO,
            ColorSource.LLM_ESTIMATE)) {
      ProductShadeColor slot = shade.addColor(source.rank(), null, NameSource.NONE);

      slot.assignColor(source, "#e8452c", false, ReviewStatus.AUTO_APPROVED, at);

      assertThat(slot.getColor().isEstimated()).as(source.name()).isTrue();
      assertThat(slot.getColor().getHex()).isEqualTo("#E8452C");
      assertThat(slot.getColorSource()).isEqualTo(source);
      assertThat(slot.getSourceCollectedAt()).isEqualTo(at);
    }
  }

  @Test
  void sampleColorKeepsTheGivenEstimatedFlag() {
    ProductShadeColor slot = shade.addColor(1, null, NameSource.NONE);

    slot.assignColor(ColorSource.SAMPLE, "#C8102E", false, ReviewStatus.AUTO_APPROVED, null);

    assertThat(slot.getColor().isEstimated()).isFalse();
  }

  @Test
  void onlyApprovedStatesAreUsableAndBelowThresholdKeepsTheHex() {
    ProductShadeColor slot = shade.addColor(1, null, NameSource.NONE);

    slot.assignColor(
        ColorSource.PRODUCT_PHOTO, "#E8452C", true, ReviewStatus.BELOW_THRESHOLD, null);
    assertThat(slot.getColor().getHex()).isEqualTo("#E8452C");
    assertThat(slot.hasUsableColor()).isFalse();

    slot.changeReviewStatus(ReviewStatus.APPROVED);
    assertThat(slot.hasUsableColor()).isTrue();

    slot.changeReviewStatus(ReviewStatus.REJECTED);
    assertThat(slot.hasUsableColor()).isFalse();
    assertThat(slot.getColor().getHex()).isEqualTo("#E8452C");
  }

  @Test
  void clearColorEmptiesColorStatusAndCollectedAt() {
    ProductShadeColor slot = shade.addColor(1, null, NameSource.NONE);
    slot.assignColor(
        ColorSource.WEB_PHOTO,
        "#E8452C",
        true,
        ReviewStatus.AUTO_APPROVED,
        Instant.parse("2026-11-05T01:00:00Z"));

    slot.clearColor();

    assertThat(slot.getColor()).isNull();
    assertThat(slot.getReviewStatus()).isNull();
    assertThat(slot.getSourceCollectedAt()).isNull();
    assertThat(slot.getColorSource()).isNull();
    assertThatThrownBy(() -> slot.changeReviewStatus(ReviewStatus.APPROVED))
        .isInstanceOf(IllegalStateException.class);
  }

  @Test
  void malformedHexIsRejected() {
    ProductShadeColor slot = shade.addColor(1, null, NameSource.NONE);

    assertThatThrownBy(
            () ->
                slot.assignColor(
                    ColorSource.WEB_PHOTO, "E8452C", true, ReviewStatus.AUTO_APPROVED, null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void sourcePriorityFollowsThePolicyOrder() {
    assertThat(ColorSource.SOURCE_VALUE.outranks(ColorSource.SWATCH_CHIP)).isTrue();
    assertThat(ColorSource.SWATCH_CHIP.outranks(ColorSource.PRODUCT_PHOTO)).isTrue();
    assertThat(ColorSource.PRODUCT_PHOTO.outranks(ColorSource.WEB_PHOTO)).isTrue();
    assertThat(ColorSource.WEB_PHOTO.outranks(ColorSource.LLM_ESTIMATE)).isTrue();
    assertThat(ColorSource.LLM_ESTIMATE.outranks(ColorSource.SAMPLE)).isTrue();
    assertThat(ColorSource.WEB_PHOTO.outranks(ColorSource.WEB_PHOTO)).isFalse();
  }

  @Test
  void operatorDecisionsAreRecognizedSoCollectionDoesNotOverwriteThem() {
    assertThat(ReviewStatus.APPROVED.isOperatorDecision()).isTrue();
    assertThat(ReviewStatus.REJECTED.isOperatorDecision()).isTrue();
    assertThat(ReviewStatus.AUTO_APPROVED.isOperatorDecision()).isFalse();
    assertThat(ReviewStatus.BELOW_THRESHOLD.isOperatorDecision()).isFalse();
  }

  @Test
  void optionIdsAndAliasesAreValidatedAndDeduplicated() {
    shade.changeSourceOptionId("opt-1");
    shade.addOptionAlias("opt-1");
    shade.addOptionAlias("old-1");
    shade.addOptionAlias("old-1");

    assertThat(shade.getSourceOptionId()).isEqualTo("opt-1");
    assertThat(shade.getOptionAliases()).containsExactly("old-1");
    assertThatThrownBy(() -> shade.addOptionAlias(" "))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> shade.addOptionAlias(null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> shade.changeSourceOptionId("a".repeat(ProductShade.SOURCE_OPTION_MAX_LENGTH + 1)))
        .isInstanceOf(IllegalArgumentException.class);

    shade.changeSourceOptionId(null);
    assertThat(shade.getSourceOptionId()).isNull();
  }

  @Test
  void listingRecordsImageAndSaleStatusWithinTheLimit() {
    ProductCategory eye = new ProductCategory("EYE", "아이", true, true, 3);
    Product product = new Product(new ProductType("MASCARA", eye, "마스카라", 2), "Brand", "Mascara");

    product.recordListing("https://example.com/a.png", SaleStatus.SOLD_OUT);
    assertThat(product.getImageUrl()).isEqualTo("https://example.com/a.png");
    assertThat(product.getSaleStatus()).isEqualTo(SaleStatus.SOLD_OUT);

    assertThatThrownBy(
            () -> product.recordListing("a".repeat(Product.IMAGE_URL_MAX_LENGTH + 1), null))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
