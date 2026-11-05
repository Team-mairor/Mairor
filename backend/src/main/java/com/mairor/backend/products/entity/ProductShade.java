package com.mairor.backend.products.entity;

import jakarta.persistence.CascadeType;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
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
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 제품의 호수(예: "1호 오렌지레드"). 호수명은 원문과 비교용 키를 함께 저장하고, 비교용 키는 생성과 {@link #rename}에서만 채운다. 생성은 {@link
 * Product#addShade}로만 한다.
 *
 * <p>정렬은 {@code sort_order}, {@code name_normalized} 순이다. 같은 제품 안에서 {@code name_normalized}가
 * 유니크({@value #PRODUCT_NAME_UNIQUE})라 순서가 하나로 정해진다.
 *
 * <p>색은 호수의 {@link #getColors 색 칸}에 둔다(0..N개). {@link #getColor 옛 대표 색상} 컬럼은 칸 구조로 옮기는 동안 남겨 둔 값이고
 * 새 코드는 쓰지 않는다. 수집 출처의 옵션 값은 {@code sourceOptionId}이고, 호수가 합쳐질 때 사라지는 옵션 값은 별칭으로 남긴다.
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
  public static final String SOURCE_OPTION_UNIQUE_INDEX = "uk_product_shades_source_option";
  public static final String OPTION_ALIAS_FK = "fk_product_shade_option_aliases_shade";

  public static final int NAME_MAX_LENGTH = 100;
  public static final int SOURCE_OPTION_MAX_LENGTH = 200;

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

  /** 옛 대표 색상. 칸 구조로 옮기는 동안 남겨 둔 값이고 새 코드는 쓰지 않는다. 모르면 {@code null}이고 색상 컬럼이 모두 NULL 이다. */
  @Embedded private ShadeColor color;

  /** 수집 출처가 준 옵션 값. 같은 제품 안에서 유일하다. 직접 넣은 호수는 {@code null}. */
  @Column(name = "source_option_id", length = SOURCE_OPTION_MAX_LENGTH)
  private String sourceOptionId;

  /** 합쳐진 옵션 값. {@link #sourceOptionId}와 함께 호수를 찾는 데 쓴다. */
  @ElementCollection(fetch = FetchType.LAZY)
  @CollectionTable(
      name = "product_shade_option_aliases",
      joinColumns =
          @JoinColumn(
              name = "shade_id",
              foreignKey = @ForeignKey(name = ProductShade.OPTION_ALIAS_FK)))
  @Column(name = "source_option_id", nullable = false, length = SOURCE_OPTION_MAX_LENGTH)
  private Set<String> optionAliases = new LinkedHashSet<>();

  @OneToMany(mappedBy = "shade", cascade = CascadeType.ALL, orphanRemoval = true)
  @OrderBy("sortOrder ASC")
  private List<ProductShadeColor> colors = new ArrayList<>();

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
   * @param sourceOptionId 수집 출처의 옵션 값(1~200자). 직접 넣은 호수면 {@code null}
   */
  public void changeSourceOptionId(String sourceOptionId) {
    this.sourceOptionId = checkOptionId(sourceOptionId, true);
  }

  /**
   * 합쳐진 옵션 값을 별칭으로 남긴다. 이미 호수의 옵션 값이면 무시한다. 같은 제품의 다른 호수와 겹치는지는 호출하는 쪽이 확인한다.
   *
   * @throws IllegalArgumentException 비었거나 200자를 넘으면
   */
  public void addOptionAlias(String optionId) {
    String checked = checkOptionId(optionId, false);
    if (!checked.equals(sourceOptionId)) {
      optionAliases.add(checked);
    }
  }

  /**
   * 색 칸을 추가한다. 칸 순서는 호수 안에서 유일해야 한다.
   *
   * @param name 칸 이름. 없으면 {@code null}이고 근거는 {@code NONE}
   * @return 색은 아직 비어 있는 칸. {@link ProductShadeColor#assignColor}로 채운다
   * @throws IllegalArgumentException 같은 순서의 칸이 이미 있거나, 이름과 근거가 맞지 않거나, 이름이 비었거나 길면
   */
  public ProductShadeColor addColor(int sortOrder, String name, NameSource nameSource) {
    if (colors.stream().anyMatch(c -> c.getSortOrder() == sortOrder)) {
      throw new IllegalArgumentException("이미 있는 칸 순서다: " + sortOrder);
    }
    ProductShadeColor slot = new ProductShadeColor(this, sortOrder, name, nameSource);
    colors.add(slot);
    return slot;
  }

  private static String checkOptionId(String optionId, boolean nullable) {
    if (optionId == null && nullable) {
      return null;
    }
    if (optionId == null || optionId.isBlank() || optionId.length() > SOURCE_OPTION_MAX_LENGTH) {
      throw new IllegalArgumentException("옵션 값은 1~" + SOURCE_OPTION_MAX_LENGTH + "자여야 한다");
    }
    return optionId;
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

  /** 옛 대표 색상. 새 코드는 {@link #getColors}를 쓴다. */
  public ShadeColor getColor() {
    return color;
  }

  public String getSourceOptionId() {
    return sourceOptionId;
  }

  public Set<String> getOptionAliases() {
    return Collections.unmodifiableSet(optionAliases);
  }

  /** 색 칸. 정렬: {@code sortOrder} 순 (DB 에서 읽을 때). */
  public List<ProductShadeColor> getColors() {
    return Collections.unmodifiableList(colors);
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
