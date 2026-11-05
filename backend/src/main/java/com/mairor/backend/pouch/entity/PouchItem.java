package com.mairor.backend.pouch.entity;

import com.mairor.backend.products.support.CatalogTextNormalizer;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/** 개인 표시값·비교키·색상 복사본. 카탈로그 ID는 연결 정보이며 표시 응답을 실시간 조인하지 않는다. */
@Entity
@Table(
    name = "pouch_items",
    uniqueConstraints =
        @UniqueConstraint(
            name = PouchItem.DUPLICATE_UNIQUE,
            columnNames = {
              "user_id",
              "brand_normalized",
              "name_normalized",
              "shade_name_normalized"
            }),
    indexes =
        @Index(
            name = "idx_pouch_items_user_created",
            columnList = "user_id, created_at DESC, id DESC"))
public class PouchItem {

  public static final String DUPLICATE_UNIQUE = "uk_pouch_items_user_brand_name_shade";
  public static final int BRAND_MAX_LENGTH = 100;
  public static final int NAME_MAX_LENGTH = 200;
  public static final int SHADE_NAME_MAX_LENGTH = 100;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "user_id", nullable = false)
  private UUID userId;

  @Enumerated(EnumType.STRING)
  @Column(name = "registration_mode", nullable = false, length = 10)
  private RegistrationMode registrationMode;

  @Column(name = "product_id")
  private UUID productId;

  @Column(name = "shade_id")
  private UUID shadeId;

  @Column(name = "category_code", nullable = false, length = 20)
  private String category;

  @Column(name = "type_code", nullable = false, length = 40)
  private String type;

  @Column(nullable = false, length = BRAND_MAX_LENGTH)
  private String brand;

  @Column(nullable = false, length = NAME_MAX_LENGTH)
  private String name;

  @Column(name = "shade_name", length = SHADE_NAME_MAX_LENGTH)
  private String shadeName;

  @Column(name = "brand_normalized", nullable = false, length = BRAND_MAX_LENGTH * 2)
  private String brandNormalized;

  @Column(name = "name_normalized", nullable = false, length = NAME_MAX_LENGTH * 2)
  private String nameNormalized;

  @Column(name = "shade_name_normalized", nullable = false, length = SHADE_NAME_MAX_LENGTH * 2)
  private String shadeNameNormalized;

  @Embedded private PouchColor color;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected PouchItem() {}

  /** 분류 소속·제품/호수 관계·호수 필수 여부는 저장 전 서비스에서 검증한다. */
  public PouchItem(
      UUID userId,
      RegistrationMode registrationMode,
      UUID productId,
      UUID shadeId,
      String category,
      String type,
      String brand,
      String name,
      String shadeName,
      PouchColor color) {
    this.userId = Objects.requireNonNull(userId, "userId");
    this.registrationMode = Objects.requireNonNull(registrationMode, "registrationMode");
    if (registrationMode == RegistrationMode.MANUAL && (productId != null || shadeId != null)) {
      throw new IllegalArgumentException("직접 입력 항목에 카탈로그 ID를 넣을 수 없다");
    }
    if (registrationMode == RegistrationMode.CATALOG && productId == null) {
      throw new IllegalArgumentException("카탈로그 항목은 제품 ID가 필요하다");
    }
    if (color != null
        && ((registrationMode == RegistrationMode.CATALOG)
            != (color.getSource() == PouchColor.Source.CATALOG))) {
      throw new IllegalArgumentException("등록 방식과 색상 출처가 다르다");
    }
    this.productId = productId;
    this.shadeId = shadeId;
    this.category = required(category, 20);
    this.type = required(type, 40);
    this.brand = required(brand, BRAND_MAX_LENGTH);
    this.name = required(name, NAME_MAX_LENGTH);
    String trimmedShade = shadeName == null ? "" : CatalogTextNormalizer.trimmed(shadeName);
    this.shadeName = trimmedShade.isEmpty() ? null : required(trimmedShade, SHADE_NAME_MAX_LENGTH);
    this.brandNormalized = CatalogTextNormalizer.normalize(this.brand);
    this.nameNormalized = CatalogTextNormalizer.normalize(this.name);
    this.shadeNameNormalized =
        this.shadeName == null ? "" : CatalogTextNormalizer.normalize(this.shadeName);
    this.color = color;
  }

  private static String required(String value, int max) {
    String trimmed = CatalogTextNormalizer.trimmed(Objects.requireNonNull(value, "text"));
    if (trimmed.isEmpty() || trimmed.length() > max) {
      throw new IllegalArgumentException("입력은 앞뒤 공백 제거 후 1~" + max + "자여야 한다");
    }
    return trimmed;
  }

  public UUID getId() {
    return id;
  }

  public UUID getUserId() {
    return userId;
  }

  public RegistrationMode getRegistrationMode() {
    return registrationMode;
  }

  public UUID getProductId() {
    return productId;
  }

  public UUID getShadeId() {
    return shadeId;
  }

  public String getCategory() {
    return category;
  }

  public String getType() {
    return type;
  }

  public String getBrand() {
    return brand;
  }

  public String getName() {
    return name;
  }

  public String getShadeName() {
    return shadeName;
  }

  public String getBrandNormalized() {
    return brandNormalized;
  }

  public String getNameNormalized() {
    return nameNormalized;
  }

  public String getShadeNameNormalized() {
    return shadeNameNormalized;
  }

  public PouchColor getColor() {
    return color;
  }

  public String getColorSource() {
    return color == null ? "NONE" : color.getSource().name();
  }

  /** 수정 후보의 변경 가능한 필드를 반영한다. 식별자·소유자·생성 시각은 유지한다. */
  public void replaceDetailsFrom(PouchItem candidate) {
    if (!Objects.equals(userId, candidate.userId)) {
      throw new IllegalArgumentException("파우치 항목 소유자는 변경할 수 없다");
    }
    registrationMode = candidate.registrationMode;
    productId = candidate.productId;
    shadeId = candidate.shadeId;
    category = candidate.category;
    type = candidate.type;
    brand = candidate.brand;
    name = candidate.name;
    shadeName = candidate.shadeName;
    brandNormalized = candidate.brandNormalized;
    nameNormalized = candidate.nameNormalized;
    shadeNameNormalized = candidate.shadeNameNormalized;
    color = candidate.color;
  }

  /** 응답·버전 변경 여부 판정에 쓰는 저장 가능한 모든 필드를 비교한다. */
  public boolean hasSameDetails(PouchItem other) {
    return other != null
        && Objects.equals(userId, other.userId)
        && registrationMode == other.registrationMode
        && Objects.equals(productId, other.productId)
        && Objects.equals(shadeId, other.shadeId)
        && Objects.equals(category, other.category)
        && Objects.equals(type, other.type)
        && Objects.equals(brand, other.brand)
        && Objects.equals(name, other.name)
        && Objects.equals(shadeName, other.shadeName)
        && Objects.equals(brandNormalized, other.brandNormalized)
        && Objects.equals(nameNormalized, other.nameNormalized)
        && Objects.equals(shadeNameNormalized, other.shadeNameNormalized)
        && Objects.equals(color, other.color);
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
