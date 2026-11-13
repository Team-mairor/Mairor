package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;

/**
 * 수집 요청을 낸 회원과 자동 연결 대상 파우치 항목. 같은 제품 요청이 합쳐지면 한 요청에 여러 행이 붙는다.
 *
 * <p>{@code pouchItemUpdatedAt}은 요청 때 항목의 수정 시각이다. 결과가 왔을 때 항목이 그 뒤로 바뀌었으면 자동 연결하지 않는다. 항목이 지워지면
 * {@code pouchItemId}는 비워진다(SQL {@code ON DELETE SET NULL}).
 */
@Entity
@Table(name = "catalog_collect_request_users")
public class CatalogCollectRequestUser {

  public static final String REQUEST_FK = "fk_catalog_collect_request_users_request";
  public static final String USER_FK = "fk_catalog_collect_request_users_user";
  public static final String POUCH_ITEM_FK = "fk_catalog_collect_request_users_pouch_item";
  public static final String REQUEST_ITEM_UNIQUE = "uk_catalog_collect_request_users_request_item";
  public static final String USER_CREATED_INDEX = "idx_catalog_collect_request_users_user_created";
  public static final String POUCH_ITEM_INDEX = "idx_catalog_collect_request_users_pouch_item";

  public static final int LINK_RESULT_MAX_LENGTH = 30;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "request_id", nullable = false)
  private UUID requestId;

  @Column(name = "user_id", nullable = false)
  private UUID userId;

  @Column(name = "pouch_item_id")
  private UUID pouchItemId;

  @Column(name = "pouch_item_updated_at")
  private Instant pouchItemUpdatedAt;

  /** 자동 연결 판정 결과(LINKED 또는 연결하지 않은 사유). 판정 전에는 없다. */
  @Column(name = "link_result", length = LINK_RESULT_MAX_LENGTH)
  private String linkResult;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  protected CatalogCollectRequestUser() {}

  public CatalogCollectRequestUser(
      UUID requestId, UUID userId, UUID pouchItemId, Instant pouchItemUpdatedAt) {
    if ((pouchItemId == null) != (pouchItemUpdatedAt == null)) {
      throw new IllegalArgumentException("파우치 항목과 그 수정 시각은 함께 준다");
    }
    this.requestId = Objects.requireNonNull(requestId, "requestId");
    this.userId = Objects.requireNonNull(userId, "userId");
    this.pouchItemId = pouchItemId;
    this.pouchItemUpdatedAt = pouchItemUpdatedAt;
  }

  public void recordLink(String result) {
    if (result == null || result.isBlank() || result.length() > LINK_RESULT_MAX_LENGTH) {
      throw new IllegalArgumentException("linkResult 는 1~" + LINK_RESULT_MAX_LENGTH + "자다");
    }
    this.linkResult = result;
  }

  public UUID getId() {
    return id;
  }

  public UUID getRequestId() {
    return requestId;
  }

  public UUID getUserId() {
    return userId;
  }

  public UUID getPouchItemId() {
    return pouchItemId;
  }

  public Instant getPouchItemUpdatedAt() {
    return pouchItemUpdatedAt;
  }

  public String getLinkResult() {
    return linkResult;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
