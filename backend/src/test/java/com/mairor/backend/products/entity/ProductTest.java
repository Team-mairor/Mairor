package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** DB 없이 엔티티 규칙만 확인한다. 생성자·변경 메서드에서 실패하면 저장까지 가지 않는다. */
class ProductTest {

  private static final ProductCategory LIP = new ProductCategory("LIP", "립", true, true, 5);
  private static final ProductCategory SKINCARE =
      new ProductCategory("SKINCARE", "스킨케어", false, false, 6);
  private static final ProductType LIP_TINT = new ProductType("LIP_TINT", LIP, "립틴트", 3);
  private static final ProductType TONER = new ProductType("TONER", SKINCARE, "토너", 1);

  @Test
  void constructorKeepsTheOriginalTextAndFillsTheNormalizedKeys() {
    Product product = new Product(LIP_TINT, " ETUDE ", "Dear  Darling Tint");

    assertThat(product.getBrand()).isEqualTo(" ETUDE ");
    assertThat(product.getName()).isEqualTo("Dear  Darling Tint");
    assertThat(product.getBrandNormalized()).isEqualTo("etude");
    assertThat(product.getNameNormalized()).isEqualTo("dear darling tint");
  }

  @Test
  void categoryComesFromTheType() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");

    assertThat(product.getType()).isSameAs(LIP_TINT);
    assertThat(product.getCategory()).isSameAs(LIP);
  }

  @Test
  void blankBrandOrNameFailsAtConstructionBeforeAnySave() {
    assertThatThrownBy(() -> new Product(LIP_TINT, " \t ", "틴트"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("브랜드");
    assertThatThrownBy(() -> new Product(LIP_TINT, "에뛰드", ""))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("제품명");
  }

  @Test
  void tooLongBrandOrNameIsRejected() {
    assertThatThrownBy(() -> new Product(LIP_TINT, "a".repeat(Product.BRAND_MAX_LENGTH + 1), "틴트"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new Product(LIP_TINT, "에뛰드", "a".repeat(Product.NAME_MAX_LENGTH + 1)))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void renameAndChangeBrandUpdateTheNormalizedKeysTogether() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");

    product.rename("Dear DARLING Water Gel Tint");
    product.changeBrand("ETUDE");

    assertThat(product.getName()).isEqualTo("Dear DARLING Water Gel Tint");
    assertThat(product.getNameNormalized()).isEqualTo("dear darling water gel tint");
    assertThat(product.getBrand()).isEqualTo("ETUDE");
    assertThat(product.getBrandNormalized()).isEqualTo("etude");
  }

  @Test
  void failedRenameKeepsThePreviousValues() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");

    assertThatThrownBy(() -> product.rename("   ")).isInstanceOf(IllegalArgumentException.class);

    assertThat(product.getName()).isEqualTo("디어달링 틴트");
    assertThat(product.getNameNormalized()).isEqualTo("디어달링 틴트");
  }

  @Test
  void shadesCanBeAddedToAShadeSelectableCategory() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");

    ProductShade shade =
        product.addShade(" 1호  오렌지레드 ", 1, ShadeColor.of("#e8452c", "OFFICIAL", false));

    assertThat(product.getShades()).containsExactly(shade);
    assertThat(shade.getProduct()).isSameAs(product);
    assertThat(shade.getName()).isEqualTo(" 1호  오렌지레드 ");
    assertThat(shade.getNameNormalized()).isEqualTo("1호 오렌지레드");
    assertThat(shade.getColor().getHex()).isEqualTo("#E8452C");
  }

  @Test
  void shadeWithoutColorKeepsColorNull() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");

    assertThat(product.addShade("3호", 3, null).getColor()).isNull();
  }

  @Test
  void addingAShadeToANonShadeSelectableCategoryIsRejected() {
    // 앱에서만 지키는 규칙이다. DB 는 막지 않는다
    Product toner = new Product(TONER, "라운드랩", "독도 토너");

    assertThatThrownBy(() -> toner.addShade("1호", 1, null))
        .isInstanceOf(IllegalStateException.class);
    assertThat(toner.getShades()).isEmpty();
  }

  @Test
  void shadeWhoseNormalizedNameAlreadyExistsIsRejected() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");
    product.addShade("1호 Orange", 1, null);

    assertThatThrownBy(() -> product.addShade(" 1호  ORANGE", 2, null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThat(product.getShades()).hasSize(1);
  }

  @Test
  void blankShadeNameFailsBeforeAnySave() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");

    assertThatThrownBy(() -> product.addShade(" ", 1, null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("호수명");
    assertThatThrownBy(
            () -> product.addShade("a".repeat(ProductShade.NAME_MAX_LENGTH + 1), 1, null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void renamingAShadeUpdatesTheNormalizedKey() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");
    ProductShade shade = product.addShade("1호", 1, null);

    shade.rename("1호 CORAL");

    assertThat(shade.getName()).isEqualTo("1호 CORAL");
    assertThat(shade.getNameNormalized()).isEqualTo("1호 coral");
  }

  @Test
  void productShadesCannotBeModifiedFromOutside() {
    Product product = new Product(LIP_TINT, "에뛰드", "디어달링 틴트");

    assertThatThrownBy(() -> product.getShades().clear())
        .isInstanceOf(UnsupportedOperationException.class);
  }
}
