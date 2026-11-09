package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 호수의 색 칸. 듀오·팔레트도 칸마다 저장한다. {@code id}가 colorId(영구 식별자)라 칸은 지우고 다시 만들지 않는다. 생성은 {@link
 * ProductShade#addColor}로만 한다.
 *
 * <p>이름은 사이트 글자나 사진에 인쇄된 이름만이다({@link NameSource}). 이름이 없으면 {@code name}은 {@code null}이고 근거는 {@link
 * NameSource#NONE}이다. 색은 모르면 {@code color}가 {@code null}이고 컬럼 네 개가 모두 NULL 이다.
 *
 * <p>사진·LLM·사이트 색값 출처의 색은 항상 {@code estimated=true}다({@link ColorSource#isAlwaysEstimated}). 이 규칙은
 * 엔티티가 지키고 DB 는 막지 않는다. 서비스에 쓰는 색은 {@link ReviewStatus#isUsable}인 것뿐이다.
 */
@Entity
@Table(
    name = "product_shade_colors",
    uniqueConstraints =
        @UniqueConstraint(
            name = ProductShadeColor.SHADE_ORDER_UNIQUE,
            columnNames = {"shade_id", "sort_order"}),
    indexes = {
      @Index(name = ProductShadeColor.SHADE_ORDER_INDEX, columnList = "shade_id, sort_order"),
      @Index(name = ProductShadeColor.SOURCE_ITEM_INDEX, columnList = "source_item_id")
    })
public class ProductShadeColor {

  public static final String SHADE_ORDER_UNIQUE = "uk_product_shade_colors_shade_order";
  public static final String SHADE_ORDER_INDEX = "idx_product_shade_colors_shade_order";
  public static final String SHADE_FK = "fk_product_shade_colors_shade";
  public static final String NAME_PAIR_CHECK = "ck_product_shade_colors_name_pair";
  public static final String NAME_SOURCE_CHECK = "ck_product_shade_colors_name_source";
  public static final String COLOR_ALL_OR_NONE_CHECK = "ck_product_shade_colors_all_or_none";
  public static final String COLOR_HEX_CHECK = "ck_product_shade_colors_hex";
  public static final String COLOR_SOURCE_CHECK = "ck_product_shade_colors_source";
  public static final String REVIEW_CHECK = "ck_product_shade_colors_review";
  public static final String SOURCE_ITEM_FK = "fk_product_shade_colors_source_item";
  public static final String SOURCE_PAIR_CHECK = "ck_product_shade_colors_source_pair";
  public static final String SOURCE_ITEM_INDEX = "idx_product_shade_colors_source_item";

  public static final int NAME_MAX_LENGTH = 100;
  public static final int EVIDENCE_KEY_MAX_LENGTH = 400;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "shade_id", nullable = false, foreignKey = @ForeignKey(name = SHADE_FK))
  private ProductShade shade;

  @Column(name = "sort_order", nullable = false)
  private int sortOrder;

  @Column(length = NAME_MAX_LENGTH)
  private String name;

  @Column(name = "name_normalized", length = NAME_MAX_LENGTH * 2)
  private String nameNormalized;

  @Enumerated(EnumType.STRING)
  @Column(name = "name_source", nullable = false, length = 20)
  private NameSource nameSource;

  /** 색. 모르면 {@code null}이고 색 컬럼과 {@code review_status}가 모두 NULL 이다. */
  @Embedded private ShadeColor color;

  @Enumerated(EnumType.STRING)
  @Column(name = "review_status", length = 20)
  private ReviewStatus reviewStatus;

  /** 이 색을 만든 수집 시각. 같은 우선순위끼리 더 최신인 값을 고르는 데 쓴다. */
  @Column(name = "source_collected_at")
  private Instant sourceCollectedAt;

  /** 이 칸의 현재 값을 만든 적재 건. 직접 넣은 칸이면 {@code null}이고 {@code sourceEvidenceKey}도 {@code null}이다. */
  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "source_item_id", foreignKey = @ForeignKey(name = SOURCE_ITEM_FK))
  private CatalogImportItem sourceItem;

  /** 그 건의 근거를 실행 결과 파일에서 찾는 키({@code <상품 번호>/<옵션 값>/<칸 순서>}). */
  @Column(name = "source_evidence_key", length = EVIDENCE_KEY_MAX_LENGTH)
  private String sourceEvidenceKey;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected ProductShadeColor() {}

  ProductShadeColor(ProductShade shade, int sortOrder, String name, NameSource nameSource) {
    this.shade = shade;
    this.sortOrder = sortOrder;
    this.nameSource = Objects.requireNonNull(nameSource, "nameSource");
    changeName(name, nameSource);
  }

  /**
   * 이름과 이름의 근거를 바꾼다.
   *
   * @param name 칸 이름. 없으면 {@code null}
   * @param nameSource 이름이 있으면 {@code SITE_TEXT}·{@code IMAGE_PRINT}, 없으면 {@code NONE}
   * @throws IllegalArgumentException 이름과 근거가 맞지 않거나 이름이 비었거나 길면
   */
  public void changeName(String name, NameSource nameSource) {
    Objects.requireNonNull(nameSource, "nameSource");
    if (name == null) {
      if (nameSource != NameSource.NONE) {
        throw new IllegalArgumentException("이름이 없으면 근거는 NONE 이어야 한다");
      }
      this.name = null;
      this.nameNormalized = null;
      this.nameSource = NameSource.NONE;
      return;
    }
    if (nameSource == NameSource.NONE) {
      throw new IllegalArgumentException("이름이 있으면 근거는 NONE 일 수 없다");
    }
    this.nameNormalized = Product.normalize(name, NAME_MAX_LENGTH, "칸 이름");
    this.name = name;
    this.nameSource = nameSource;
  }

  public void changeSortOrder(int sortOrder) {
    this.sortOrder = sortOrder;
  }

  /**
   * 색을 채운다. 사진·LLM·사이트 색값 출처는 {@code estimated}를 항상 {@code true}로 저장한다.
   *
   * @param hex {@code #RRGGBB}. 대소문자 무관, 대문자로 바꿔 저장한다
   * @param estimated {@link ColorSource#SAMPLE}처럼 추정이 아닌 출처일 때만 의미가 있다
   * @param collectedAt 이 색을 만든 수집 시각. 모르면 {@code null}
   */
  public void assignColor(
      ColorSource source,
      String hex,
      boolean estimated,
      ReviewStatus reviewStatus,
      Instant collectedAt) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(reviewStatus, "reviewStatus");
    this.color = ShadeColor.of(hex, source.name(), source.isAlwaysEstimated() || estimated);
    this.reviewStatus = reviewStatus;
    this.sourceCollectedAt = collectedAt;
  }

  /** 색을 모르게 됐다. 색 컬럼과 승인 상태를 모두 비운다. */
  public void clearColor() {
    this.color = null;
    this.reviewStatus = null;
    this.sourceCollectedAt = null;
  }

  /** 색은 그대로 두고 승인 상태만 바꾼다(운영 정정). 색이 없으면 바꿀 수 없다. */
  public void changeReviewStatus(ReviewStatus reviewStatus) {
    Objects.requireNonNull(reviewStatus, "reviewStatus");
    if (color == null) {
      throw new IllegalStateException("색이 없는 칸의 승인 상태는 바꿀 수 없다");
    }
    this.reviewStatus = reviewStatus;
  }

  /**
   * 이 칸의 현재 값이 어느 적재 건과 근거 키에서 왔는지 남긴다. 둘은 함께 있어야 한다.
   *
   * @throws IllegalArgumentException 근거 키가 비었거나 길면
   */
  public void linkSource(CatalogImportItem item, String evidenceKey) {
    Objects.requireNonNull(item, "item");
    if (evidenceKey == null || evidenceKey.isBlank()) {
      throw new IllegalArgumentException("근거 키는 비어 있을 수 없다");
    }
    if (evidenceKey.length() > EVIDENCE_KEY_MAX_LENGTH) {
      throw new IllegalArgumentException("근거 키는 " + EVIDENCE_KEY_MAX_LENGTH + "자까지다");
    }
    this.sourceItem = item;
    this.sourceEvidenceKey = evidenceKey;
  }

  /** 출처 연결을 지운다(직접 넣은 칸으로 돌린다). */
  public void clearSource() {
    this.sourceItem = null;
    this.sourceEvidenceKey = null;
  }

  /** 서비스에 쓸 수 있는 색이 있는가(API 가 {@code color}를 채우는 칸). */
  public boolean hasUsableColor() {
    return color != null && reviewStatus != null && reviewStatus.isUsable();
  }

  /** 색이 있으면 그 출처, 없으면 {@code null}. */
  public ColorSource getColorSource() {
    return color == null ? null : ColorSource.valueOf(color.getSource());
  }

  public UUID getId() {
    return id;
  }

  public ProductShade getShade() {
    return shade;
  }

  public int getSortOrder() {
    return sortOrder;
  }

  public String getName() {
    return name;
  }

  public String getNameNormalized() {
    return nameNormalized;
  }

  public NameSource getNameSource() {
    return nameSource;
  }

  public ShadeColor getColor() {
    return color;
  }

  public ReviewStatus getReviewStatus() {
    return reviewStatus;
  }

  public Instant getSourceCollectedAt() {
    return sourceCollectedAt;
  }

  public CatalogImportItem getSourceItem() {
    return sourceItem;
  }

  public String getSourceEvidenceKey() {
    return sourceEvidenceKey;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
