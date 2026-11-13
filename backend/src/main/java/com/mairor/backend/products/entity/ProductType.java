package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

/**
 * 카테고리별 세부 종류. 값은 시드({@code db/seed/product-categories.sql})로만 넣으며, 코드는 FE 파우치 계약과 추천 매칭의 기준값이므로
 * 변경하지 않는다.
 *
 * <p>{@value #CATEGORY_CODE_UNIQUE}는 제품의 (카테고리, 종류) 복합 FK가 참조하는 키다.
 */
@Entity
@Table(
    name = "product_types",
    uniqueConstraints =
        @UniqueConstraint(
            name = ProductType.CATEGORY_CODE_UNIQUE,
            columnNames = {"category_code", "code"}),
    indexes =
        @Index(name = ProductType.CATEGORY_ORDER_INDEX, columnList = "category_code, sort_order"))
public class ProductType {

  public static final String CATEGORY_CODE_UNIQUE = "uk_product_types_category_code";
  public static final String CATEGORY_ORDER_INDEX = "idx_product_types_category_order";
  public static final String CATEGORY_FK = "fk_product_types_category";

  @Id
  @Column(length = 40)
  private String code;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(
      name = "category_code",
      nullable = false,
      foreignKey = @ForeignKey(name = CATEGORY_FK))
  private ProductCategory category;

  @Column(nullable = false, length = 50)
  private String label;

  @Column(name = "sort_order", nullable = false)
  private int sortOrder;

  protected ProductType() {}

  public ProductType(String code, ProductCategory category, String label, int sortOrder) {
    this.code = code;
    this.category = category;
    this.label = label;
    this.sortOrder = sortOrder;
  }

  public String getCode() {
    return code;
  }

  public ProductCategory getCategory() {
    return category;
  }

  public String getLabel() {
    return label;
  }

  public int getSortOrder() {
    return sortOrder;
  }
}
