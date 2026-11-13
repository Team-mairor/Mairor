package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * 회원이 쓴 제품 이름의 별칭(S15P31A306-517). (소분류, 정규화 브랜드, 공백 뺀 제품명) → 제품. 행은 네이티브 쿼리로만 넣는다({@code
 * ProductNameAliasRepository#insertIfAbsent}). 검색은 정확 일치·공백 무시 일치가 없을 때 이 표를 본다.
 */
@Entity
@Table(name = "product_name_aliases")
public class ProductNameAlias {

  public static final String KEY_UNIQUE = "uk_product_name_aliases_key";
  public static final String PRODUCT_FK = "fk_product_name_aliases_product";

  @Id private UUID id;

  @Column(name = "type_code", nullable = false, length = 40)
  private String typeCode;

  @Column(name = "brand_normalized", nullable = false, length = 200)
  private String brandNormalized;

  @Column(name = "name_compact", nullable = false, length = 400)
  private String nameCompact;

  @Column(name = "product_id", nullable = false)
  private UUID productId;

  @Column(name = "request_id")
  private UUID requestId;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  protected ProductNameAlias() {}

  public UUID getId() {
    return id;
  }

  public String getTypeCode() {
    return typeCode;
  }

  public String getBrandNormalized() {
    return brandNormalized;
  }

  public String getNameCompact() {
    return nameCompact;
  }

  public UUID getProductId() {
    return productId;
  }

  public UUID getRequestId() {
    return requestId;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
