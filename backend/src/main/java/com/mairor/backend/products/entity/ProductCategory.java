package com.mairor.backend.products.entity;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * 화장품 카테고리 9개(BASE·EYE·BROW·CHEEK·LIP·SKINCARE·NAIL·FRAGRANCE·TOOL). 값은 시드({@code
 * db/seed/product-categories.sql})로만 넣는다.
 *
 * <p>{@code product_category_parts}는 카테고리 조회 응답의 호환 부위 값으로 유지하지만 현재 시드는 비어 있다. 가이드 단계별 대체 가능 종류는
 * {@code PouchCompatibilityPolicy}에서 별도로 관리한다.
 */
@Entity
@Table(name = "product_categories")
public class ProductCategory {

  public static final String PARTS_CATEGORY_FK = "fk_product_category_parts_category";

  @Id
  @Column(length = 20)
  private String code;

  @Column(nullable = false, length = 50)
  private String label;

  /** 추천 매칭 대상 여부. BASE·EYE·BROW·CHEEK·LIP만 true. */
  @Column(nullable = false)
  private boolean matchable;

  /** 호수 선택 여부. false 인 카테고리의 제품에는 호수를 연결하지 않는다 ({@link Product#addShade}). */
  @Column(name = "shade_selectable", nullable = false)
  private boolean shadeSelectable;

  @Column(name = "sort_order", nullable = false)
  private int sortOrder;

  @ElementCollection
  @CollectionTable(
      name = "product_category_parts",
      joinColumns = @JoinColumn(name = "category_code"),
      foreignKey = @ForeignKey(name = PARTS_CATEGORY_FK))
  @Column(name = "part_code", nullable = false, length = 30)
  private Set<String> compatibleParts = new LinkedHashSet<>();

  protected ProductCategory() {}

  public ProductCategory(
      String code, String label, boolean matchable, boolean shadeSelectable, int sortOrder) {
    this.code = code;
    this.label = label;
    this.matchable = matchable;
    this.shadeSelectable = shadeSelectable;
    this.sortOrder = sortOrder;
  }

  public String getCode() {
    return code;
  }

  public String getLabel() {
    return label;
  }

  public boolean isMatchable() {
    return matchable;
  }

  public boolean isShadeSelectable() {
    return shadeSelectable;
  }

  public int getSortOrder() {
    return sortOrder;
  }

  public Set<String> getCompatibleParts() {
    return Collections.unmodifiableSet(compatibleParts);
  }
}
