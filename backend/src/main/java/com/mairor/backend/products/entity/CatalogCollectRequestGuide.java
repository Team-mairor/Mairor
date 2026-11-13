package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * 영상 분석 부족분 수집 요청을 기다리는 가이드 단계(S15P31A306-518). 행은 네이티브 쿼리로만 넣고({@code
 * CatalogCollectRequestGuideRepository#attach}) 엔티티는 읽기에 쓴다.
 */
@Entity
@Table(name = "catalog_collect_request_guides")
public class CatalogCollectRequestGuide {

  public static final String REQUEST_FK = "fk_catalog_collect_request_guides_request";
  public static final String GUIDE_FK = "fk_catalog_collect_request_guides_guide";
  public static final String REQUEST_STEP_UNIQUE = "uk_catalog_collect_request_guides_request_step";
  public static final String GUIDE_CREATED_INDEX =
      "idx_catalog_collect_request_guides_guide_created";

  @Id private UUID id;

  @Column(name = "request_id", nullable = false)
  private UUID requestId;

  @Column(name = "guide_id", nullable = false)
  private UUID guideId;

  @Column(name = "step_id", nullable = false, length = 200)
  private String stepId;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  protected CatalogCollectRequestGuide() {}

  public UUID getId() {
    return id;
  }

  public UUID getRequestId() {
    return requestId;
  }

  public UUID getGuideId() {
    return guideId;
  }

  public String getStepId() {
    return stepId;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
