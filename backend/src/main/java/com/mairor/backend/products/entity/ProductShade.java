package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 제품의 호수(예: "1호 오렌지레드"). 호수명은 원문과 비교용 키를 함께 저장하고, 비교용 키는 생성과 {@link #rename}에서만 채운다. 생성은 {@link
 * Product#addShade}로만 한다.
 *
 * <p>정렬은 {@code sort_order}, {@code name_normalized} 순이다. 같은 제품 안에서 {@code name_normalized}가
 * 유니크({@value #PRODUCT_NAME_UNIQUE})라 순서가 하나로 정해진다.
 */
@Entity
@Table(
    name = "product_shades",
    uniqueConstraints =
        @UniqueConstraint(
            name = ProductShade.PRODUCT_NAME_UNIQUE,
            columnNames = {"product_id", "name_normalized"}),
    indexes =
        @Index(
            name = ProductShade.PRODUCT_ORDER_INDEX,
            columnList = "product_id, sort_order, name_normalized"))
public class ProductShade {

  public static final String PRODUCT_NAME_UNIQUE = "uk_product_shades_product_name";
  public static final String PRODUCT_ORDER_INDEX = "idx_product_shades_product_order";
  public static final String PRODUCT_FK = "fk_product_shades_product";
  public static final String COLOR_ALL_OR_NONE_CHECK = "ck_product_shades_color_all_or_none";
  public static final String COLOR_HEX_CHECK = "ck_product_shades_color_hex";

  public static final int NAME_MAX_LENGTH = 100;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "product_id", nullable = false, foreignKey = @ForeignKey(name = PRODUCT_FK))
  private Product product;

  @Column(nullable = false, length = NAME_MAX_LENGTH)
  private String name;

  @Column(name = "name_normalized", nullable = false, length = NAME_MAX_LENGTH * 2)
  private String nameNormalized;

  @Column(name = "sort_order", nullable = false)
  private int sortOrder;

  /** 대표 색상. 모르면 {@code null}이고 색상 컬럼이 모두 NULL 이다. */
  @Embedded private ShadeColor color;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected ProductShade() {}

  ProductShade(Product product, String name, int sortOrder, ShadeColor color) {
    this.product = product;
    rename(name);
    this.sortOrder = sortOrder;
    this.color = color;
  }

  /**
   * 호수명을 바꾼다. 같은 제품의 다른 호수와 비교용 키가 겹치면 저장할 때 {@value #PRODUCT_NAME_UNIQUE}가 막는다.
   *
   * @throws IllegalArgumentException 호수명이 비었거나(정규화 결과 기준) 길면
   */
  public void rename(String name) {
    this.nameNormalized = Product.normalize(name, NAME_MAX_LENGTH, "호수명");
    this.name = name;
  }

  public void changeSortOrder(int sortOrder) {
    this.sortOrder = sortOrder;
  }

  /**
   * @param color 대표 색상. 모르게 됐으면 {@code null}
   */
  public void changeColor(ShadeColor color) {
    this.color = color;
  }

  public UUID getId() {
    return id;
  }

  public Product getProduct() {
    return product;
  }

  public String getName() {
    return name;
  }

  public String getNameNormalized() {
    return nameNormalized;
  }

  public int getSortOrder() {
    return sortOrder;
  }

  public ShadeColor getColor() {
    return color;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
