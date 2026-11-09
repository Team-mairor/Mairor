package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class ProductShadeEditingTest {

  private static ProductShade shade() {
    ProductCategory category = new ProductCategory("EYE", "아이", true, true, 3);
    ProductType type = new ProductType("MASCARA", category, "마스카라", 2);
    Product product = new Product(type, "에뛰드", "마스카라");
    return product.addShade("01 블랙", 1, null);
  }

  @Test
  void anOptionAliasCanBeRemovedAndRemovingAMissingOneIsIgnored() {
    ProductShade shade = shade();
    shade.addOptionAlias("old-1");
    shade.addOptionAlias("old-2");

    shade.removeOptionAlias("old-1");
    shade.removeOptionAlias("never-there");

    assertThat(shade.getOptionAliases()).containsExactly("old-2");
  }

  @Test
  void aSlotCanBeRemovedFromItsShade() {
    ProductShade shade = shade();
    ProductShadeColor first = shade.addColor(1, null, NameSource.NONE);
    ProductShadeColor second = shade.addColor(2, null, NameSource.NONE);

    shade.removeColor(first);

    assertThat(shade.getColors()).containsExactly(second);
  }
}
