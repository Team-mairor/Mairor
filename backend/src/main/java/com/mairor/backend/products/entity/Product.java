package com.mairor.backend.products.entity;

import com.mairor.backend.products.support.CatalogTextNormalizer;
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.ConstraintMode;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 카탈로그 제품. 브랜드·제품명은 원문과 비교용 키({@link CatalogTextNormalizer})를 함께 저장하고, 비교용 키는 생성자와 변경 메서드에서만 채운다.
 *
 * <p>카테고리는 종류에서 정해진다. DB 에서는 (카테고리, 종류) 복합 FK({@value #CATEGORY_TYPE_FK})가 둘의 일치를 강제한다. JPA 는 복합 FK
 * 를 단일 컬럼 연관으로 표현할 수 없어 엔티티에는 FK 를 선언하지 않는다(제약은 {@code db/schema/products.sql}에만 있다).
 *
 * <p>호수 선택이 없는 카테고리(SKINCARE·FRAGRANCE·TOOL)에 호수를 연결하지 않는 규칙은 {@link #addShade}에서만 지킨다. DB 는 막지
 * 않으므로 SQL 로 직접 넣는 경우에는 지켜지지 않는다.
 */
@Entity
@Table(
    name = "products",
    uniqueConstraints =
        @UniqueConstraint(
            name = Product.TYPE_BRAND_NAME_UNIQUE,
            columnNames = {"type_code", "brand_normalized", "name_normalized"}))
public class Product {

  public static final String TYPE_BRAND_NAME_UNIQUE = "uk_products_type_brand_name";
  public static final String CATEGORY_TYPE_FK = "fk_products_category_type";
  public static final String SALE_STATUS_CHECK = "ck_products_sale_status";
  public static final String SOURCE_PRODUCT_UNIQUE_INDEX = "uk_products_source_product";

  public static final int IMAGE_URL_MAX_LENGTH = 1000;

  /** 크롤링 출처 이름 상한. {@code OFFICIAL:<도메인>} 꼴이라 도메인이 길면 30자를 넘는다. */
  public static final int SOURCE_MAX_LENGTH = 100;

  public static final int SOURCE_PRODUCT_ID_MAX_LENGTH = 100;
  public static final int SOURCE_URL_MAX_LENGTH = 1000;

  public static final int BRAND_MAX_LENGTH = 100;
  public static final int NAME_MAX_LENGTH = 200;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(nullable = false, length = BRAND_MAX_LENGTH)
  private String brand;

  @Column(nullable = false, length = NAME_MAX_LENGTH)
  private String name;

  @Column(name = "brand_normalized", nullable = false, length = BRAND_MAX_LENGTH * 2)
  private String brandNormalized;

  @Column(name = "name_normalized", nullable = false, length = NAME_MAX_LENGTH * 2)
  private String nameNormalized;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(
      name = "category_code",
      nullable = false,
      foreignKey = @ForeignKey(ConstraintMode.NO_CONSTRAINT))
  private ProductCategory category;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(
      name = "type_code",
      nullable = false,
      foreignKey = @ForeignKey(ConstraintMode.NO_CONSTRAINT))
  private ProductType type;

  /** 크롤링 출처 이름. 직접 넣은 데이터는 {@code null}. */
  @Column(length = SOURCE_MAX_LENGTH)
  private String source;

  @Column(name = "source_product_id", length = SOURCE_PRODUCT_ID_MAX_LENGTH)
  private String sourceProductId;

  @Column(name = "source_url", length = SOURCE_URL_MAX_LENGTH)
  private String sourceUrl;

  @Column(name = "collected_at")
  private Instant collectedAt;

  /** 대표 이미지 URL. 화면 표시는 선택이다. */
  @Column(name = "image_url", length = IMAGE_URL_MAX_LENGTH)
  private String imageUrl;

  /** 수집 시점의 판매 상태. 직접 넣은 데이터는 {@code null}. */
  @Enumerated(EnumType.STRING)
  @Column(name = "sale_status", length = 20)
  private SaleStatus saleStatus;

  @OneToMany(mappedBy = "product", cascade = CascadeType.ALL, orphanRemoval = true)
  @OrderBy("sortOrder ASC, nameNormalized ASC")
  private List<ProductShade> shades = new ArrayList<>();

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected Product() {}

  /**
   * @throws IllegalArgumentException 브랜드·제품명이 비었거나(정규화 결과 기준) 길이를 넘으면
   */
  public Product(ProductType type, String brand, String name) {
    this.type = Objects.requireNonNull(type, "type");
    this.category = type.getCategory();
    changeBrand(brand);
    rename(name);
  }

  public void changeBrand(String brand) {
    this.brandNormalized = normalize(brand, BRAND_MAX_LENGTH, "브랜드");
    this.brand = brand;
  }

  public void rename(String name) {
    this.nameNormalized = normalize(name, NAME_MAX_LENGTH, "제품명");
    this.name = name;
  }

  public void recordSource(
      String source, String sourceProductId, String sourceUrl, Instant collectedAt) {
    this.source = source;
    this.sourceProductId = sourceProductId;
    this.sourceUrl = sourceUrl;
    this.collectedAt = collectedAt;
  }

  /**
   * 대표 이미지와 판매 상태를 기록한다.
   *
   * @param imageUrl 대표 이미지 URL(최대 1000자). 없으면 {@code null}
   * @param saleStatus 판매 상태. 모르면 {@code null}
   * @throws IllegalArgumentException 이미지 URL 이 1000자를 넘으면
   */
  public void recordListing(String imageUrl, SaleStatus saleStatus) {
    if (imageUrl != null && imageUrl.length() > IMAGE_URL_MAX_LENGTH) {
      throw new IllegalArgumentException("이미지 URL은 " + IMAGE_URL_MAX_LENGTH + "자를 넘을 수 없다");
    }
    this.imageUrl = imageUrl;
    this.saleStatus = saleStatus;
  }

  /**
   * 호수를 추가한다.
   *
   * @param color 대표 색상. 모르면 {@code null}
   * @throws IllegalStateException 호수 선택이 없는 카테고리의 제품이면
   * @throws IllegalArgumentException 같은 제품에 비교용 키가 같은 호수가 이미 있거나, 호수명이 비었거나 길면
   */
  public ProductShade addShade(String name, int sortOrder, ShadeColor color) {
    if (!category.isShadeSelectable()) {
      throw new IllegalStateException(category.getCode() + " 카테고리 제품에는 호수를 연결할 수 없다");
    }
    ProductShade shade = new ProductShade(this, name, sortOrder, color);
    boolean duplicate =
        shades.stream().anyMatch(s -> s.getNameNormalized().equals(shade.getNameNormalized()));
    if (duplicate) {
      throw new IllegalArgumentException("이미 있는 호수다: " + name);
    }
    shades.add(shade);
    return shade;
  }

  static String normalize(String text, int maxLength, String field) {
    Objects.requireNonNull(text, field);
    if (text.length() > maxLength) {
      throw new IllegalArgumentException(field + "은(는) " + maxLength + "자를 넘을 수 없다");
    }
    try {
      return CatalogTextNormalizer.normalize(text);
    } catch (IllegalArgumentException e) {
      throw new IllegalArgumentException(field + "이(가) 비어 있다", e);
    }
  }

  public UUID getId() {
    return id;
  }

  public String getBrand() {
    return brand;
  }

  public String getName() {
    return name;
  }

  public String getBrandNormalized() {
    return brandNormalized;
  }

  public String getNameNormalized() {
    return nameNormalized;
  }

  public ProductCategory getCategory() {
    return category;
  }

  public ProductType getType() {
    return type;
  }

  public String getSource() {
    return source;
  }

  public String getSourceProductId() {
    return sourceProductId;
  }

  public String getSourceUrl() {
    return sourceUrl;
  }

  public Instant getCollectedAt() {
    return collectedAt;
  }

  public String getImageUrl() {
    return imageUrl;
  }

  public SaleStatus getSaleStatus() {
    return saleStatus;
  }

  /** 정렬: {@code sortOrder}, {@code nameNormalized} 순 (DB 에서 읽을 때). */
  public List<ProductShade> getShades() {
    return Collections.unmodifiableList(shades);
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
