package com.mairor.backend.guides.entity;

import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import jakarta.persistence.Column;
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

/** 한 가이드 단계의 기존 카탈로그 제품 대조 결과. 제품 카탈로그 데이터는 이 엔티티에서 변경하지 않는다. */
@Entity
@Table(
    name = "guide_step_product_links",
    uniqueConstraints =
        @UniqueConstraint(
            name = GuideStepProductLink.GUIDE_STEP_UNIQUE,
            columnNames = {"guide_id", "step_id"}),
    indexes = {
      @Index(name = GuideStepProductLink.PRODUCT_INDEX, columnList = "product_id", unique = false),
      @Index(name = GuideStepProductLink.SHADE_INDEX, columnList = "shade_id", unique = false),
      @Index(name = GuideStepProductLink.COLOR_INDEX, columnList = "color_id", unique = false)
    })
public class GuideStepProductLink {

  public static final String GUIDE_FK = "fk_guide_step_product_links_guide";
  public static final String PRODUCT_FK = "fk_guide_step_product_links_product";
  public static final String SHADE_FK = "fk_guide_step_product_links_shade";
  public static final String COLOR_FK = "fk_guide_step_product_links_color";
  public static final String GUIDE_STEP_UNIQUE = "uk_guide_step_product_links_guide_step";
  public static final String PRODUCT_INDEX = "idx_guide_step_product_links_product";
  public static final String SHADE_INDEX = "idx_guide_step_product_links_shade";
  public static final String COLOR_INDEX = "idx_guide_step_product_links_color";
  public static final String MATCH_LEVEL_CHECK = "ck_guide_step_product_links_match_level";
  public static final String REASON_CODE_CHECK = "ck_guide_step_product_links_reason_code";

  public static final int STEP_ID_MAX_LENGTH = 200;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "guide_id", nullable = false, foreignKey = @ForeignKey(name = GUIDE_FK))
  private Guide guide;

  @Column(name = "step_id", nullable = false, length = STEP_ID_MAX_LENGTH)
  private String stepId;

  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "product_id", foreignKey = @ForeignKey(name = PRODUCT_FK))
  private Product product;

  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "shade_id", foreignKey = @ForeignKey(name = SHADE_FK))
  private ProductShade shade;

  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "color_id", foreignKey = @ForeignKey(name = COLOR_FK))
  private ProductShadeColor color;

  @Enumerated(EnumType.STRING)
  @Column(name = "match_level", nullable = false, length = 20)
  private ReferenceMatchLevel matchLevel;

  @Enumerated(EnumType.STRING)
  @Column(name = "reason_code", length = 40)
  private ReferenceMatchReason reasonCode;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected GuideStepProductLink() {}

  public GuideStepProductLink(
      Guide guide,
      String stepId,
      Product product,
      ProductShade shade,
      ProductShadeColor color,
      ReferenceMatchLevel matchLevel,
      ReferenceMatchReason reasonCode) {
    this.guide = Objects.requireNonNull(guide, "guide");
    this.stepId = requireStepId(stepId);
    this.matchLevel = Objects.requireNonNull(matchLevel, "matchLevel");
    this.reasonCode = reasonCode;
    setReferences(product, shade, color);
  }

  private void setReferences(Product product, ProductShade shade, ProductShadeColor color) {
    if (shade != null && (product == null || !product.getId().equals(shade.getProduct().getId()))) {
      throw new IllegalArgumentException("호수는 연결 제품에 속해야 한다");
    }
    if (color != null && (shade == null || !shade.getId().equals(color.getShade().getId()))) {
      throw new IllegalArgumentException("색 칸은 연결 호수에 속해야 한다");
    }
    boolean consistent =
        switch (matchLevel) {
          case NONE -> product == null && shade == null && color == null;
          case PRODUCT -> product != null && shade == null && color == null;
          case SHADE -> product != null && shade != null && color == null;
          case SLOT -> product != null && shade != null && color != null;
        };
    if (!consistent) {
      throw new IllegalArgumentException("연결 수준과 제품·호수·색 칸 ID 가 일치하지 않는다");
    }
    this.product = product;
    this.shade = shade;
    this.color = color;
  }

  /** 기존 식별자를 보존하고 충돌 없이 확인된 더 구체적 ID 만 보완한다. */
  public boolean reconcile(
      Product candidateProduct,
      ProductShade candidateShade,
      ProductShadeColor candidateColor,
      ReferenceMatchReason candidateReason) {
    boolean conflict =
        (product != null
                && candidateProduct != null
                && !product.getId().equals(candidateProduct.getId()))
            || (shade != null
                && candidateShade != null
                && !shade.getId().equals(candidateShade.getId()))
            || (color != null
                && candidateColor != null
                && !color.getId().equals(candidateColor.getId()));

    Product nextProduct = product;
    ProductShade nextShade = shade;
    ProductShadeColor nextColor = color;
    if (!conflict) {
      if (nextProduct == null) {
        nextProduct = candidateProduct;
      }
      if (nextShade == null
          && candidateShade != null
          && nextProduct != null
          && nextProduct.getId().equals(candidateShade.getProduct().getId())) {
        nextShade = candidateShade;
      }
      if (nextColor == null
          && candidateColor != null
          && nextShade != null
          && nextShade.getId().equals(candidateColor.getShade().getId())) {
        nextColor = candidateColor;
      }
    }

    ReferenceMatchLevel nextLevel = level(nextProduct, nextShade, nextColor);
    ReferenceMatchReason nextReason =
        conflict ? ReferenceMatchReason.LINK_CONFLICT : candidateReason;
    boolean changed =
        !sameId(product, nextProduct)
            || !sameId(shade, nextShade)
            || !sameId(color, nextColor)
            || matchLevel != nextLevel
            || reasonCode != nextReason;
    if (changed) {
      // 연결 수준을 먼저 바꾼다. setReferences 가 연결 수준과 ID 가 맞는지 확인하므로, 옛 수준으로 확인하면 연결이 좋아질 때마다 실패한다
      // (예: 제품 없음 → 수집 뒤 제품 연결, S15P31A306-518)
      matchLevel = nextLevel;
      setReferences(nextProduct, nextShade, nextColor);
      reasonCode = nextReason;
    }
    return changed;
  }

  private static ReferenceMatchLevel level(
      Product product, ProductShade shade, ProductShadeColor color) {
    if (color != null) {
      return ReferenceMatchLevel.SLOT;
    }
    if (shade != null) {
      return ReferenceMatchLevel.SHADE;
    }
    return product == null ? ReferenceMatchLevel.NONE : ReferenceMatchLevel.PRODUCT;
  }

  private static boolean sameId(Product left, Product right) {
    if (left == null || right == null) {
      return left == right;
    }
    return left.getId().equals(right.getId());
  }

  private static boolean sameId(ProductShade left, ProductShade right) {
    if (left == null || right == null) {
      return left == right;
    }
    return left.getId().equals(right.getId());
  }

  private static boolean sameId(ProductShadeColor left, ProductShadeColor right) {
    if (left == null || right == null) {
      return left == right;
    }
    return left.getId().equals(right.getId());
  }

  private static String requireStepId(String stepId) {
    Objects.requireNonNull(stepId, "stepId");
    if (stepId.isBlank() || stepId.length() > STEP_ID_MAX_LENGTH) {
      throw new IllegalArgumentException("stepId 는 비어 있지 않고 200자 이하여야 한다");
    }
    return stepId;
  }

  public UUID getId() {
    return id;
  }

  public Guide getGuide() {
    return guide;
  }

  public String getStepId() {
    return stepId;
  }

  public Product getProduct() {
    return product;
  }

  public ProductShade getShade() {
    return shade;
  }

  public ProductShadeColor getColor() {
    return color;
  }

  public ReferenceMatchLevel getMatchLevel() {
    return matchLevel;
  }

  public ReferenceMatchReason getReasonCode() {
    return reasonCode;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
