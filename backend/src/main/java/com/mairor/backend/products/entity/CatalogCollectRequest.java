package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;
import org.springframework.data.domain.Persistable;

/**
 * 화장품 수집 요청 하나. {@code id}가 수집 워커에 보내는 작업 ID(jobId)다. 제품 이름으로 찾거나({@code name}) 상품 주소로 다시
 * 수집한다({@code productUrl}). 둘 중 하나만 있다.
 *
 * <p>같은 제품({@code requestKey})의 진행 중 요청은 하나뿐이다(SQL 부분 유니크 {@value #OPEN_KEY_UNIQUE}). 진행 중({@link
 * CollectRequestStatus#isOpen()})이면 {@code finishedAt}이 없고, 끝나면 반드시 있다.
 *
 * <p>id 를 만들 때 정하므로 {@link Persistable}로 새 행인지 알려 저장이 merge 가 아닌 insert 가 되게 한다.
 */
@Entity
@Table(name = "catalog_collect_requests")
public class CatalogCollectRequest implements Persistable<UUID> {

  public static final String OPEN_KEY_UNIQUE = "uk_catalog_collect_requests_open_key";
  public static final String KEY_FINISHED_INDEX = "idx_catalog_collect_requests_key_finished";
  public static final String STATUS_UPDATED_INDEX = "idx_catalog_collect_requests_status_updated";
  public static final String IMPORT_RUN_FK = "fk_catalog_collect_requests_import_run";
  public static final String TRIGGER_CHECK = "ck_catalog_collect_requests_trigger";
  public static final String STATUS_CHECK = "ck_catalog_collect_requests_status";
  public static final String TARGET_CHECK = "ck_catalog_collect_requests_target";
  public static final String FINISHED_CHECK = "ck_catalog_collect_requests_finished";
  public static final String SENT_CHECK = "ck_catalog_collect_requests_sent";
  public static final String ATTEMPTS_CHECK = "ck_catalog_collect_requests_attempts";
  public static final String GAP_CHECK = "ck_catalog_collect_requests_gap";
  public static final String TRIGGER_GAP_CHECK = "ck_catalog_collect_requests_trigger_gap";
  public static final String TARGET_PRODUCT_FK = "fk_catalog_collect_requests_target_product";
  public static final String TARGET_SHADE_FK = "fk_catalog_collect_requests_target_shade";
  public static final String TARGET_COLOR_FK = "fk_catalog_collect_requests_target_color";

  public static final int REQUEST_KEY_MAX_LENGTH = 800;
  public static final int BRAND_MAX_LENGTH = 100;
  public static final int NAME_MAX_LENGTH = 200;
  public static final int URL_MAX_LENGTH = 2000;
  public static final int SHADE_NAME_MAX_LENGTH = 100;
  public static final int REASON_MAX_LENGTH = 200;
  public static final int RESULT_STATUS_MAX_LENGTH = 30;
  public static final int RESULT_FILE_MAX_LENGTH = 200;
  public static final int SLOT_LABEL_MAX_LENGTH = 100;

  @Id private UUID id;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 10)
  private CollectTrigger trigger;

  @Column(name = "request_key", nullable = false, length = REQUEST_KEY_MAX_LENGTH)
  private String requestKey;

  @Column(name = "category_code", length = 20)
  private String categoryCode;

  @Column(name = "type_code", length = 40)
  private String typeCode;

  @Column(nullable = false, length = BRAND_MAX_LENGTH)
  private String brand;

  @Column(length = NAME_MAX_LENGTH)
  private String name;

  @Column(name = "product_url", length = URL_MAX_LENGTH)
  private String productUrl;

  @Column(name = "shade_name", length = SHADE_NAME_MAX_LENGTH)
  private String shadeName;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private CollectRequestStatus status;

  @Column(length = REASON_MAX_LENGTH)
  private String reason;

  @Column(name = "send_attempts", nullable = false)
  private int sendAttempts;

  @Column(name = "sent_at")
  private Instant sentAt;

  /** 수집 워커가 알린 상태(COLLECTED·SEARCH_EMPTY 등). 판정 재료로만 남긴다. */
  @Column(name = "result_status", length = RESULT_STATUS_MAX_LENGTH)
  private String resultStatus;

  @Column(name = "result_file", length = RESULT_FILE_MAX_LENGTH)
  private String resultFile;

  @Column(name = "import_run_id")
  private UUID importRunId;

  /** 영상 분석 요청(GUIDE)이 채우려는 것. 회원 요청(USER)은 없다. */
  @Enumerated(EnumType.STRING)
  @Column(length = 20)
  private CollectGap gap;

  @Column(name = "target_product_id")
  private UUID targetProductId;

  @Column(name = "target_shade_id")
  private UUID targetShadeId;

  @Column(name = "target_color_id")
  private UUID targetColorId;

  /** 칸 행이 없던 팔레트에서 영상이 적은 칸 이름·번호. 생긴 칸 중 이것과 맞는 칸을 본다. */
  @Column(name = "target_slot_label", length = SLOT_LABEL_MAX_LENGTH)
  private String targetSlotLabel;

  @Column(name = "finished_at")
  private Instant finishedAt;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  @Transient private boolean persisted;

  protected CatalogCollectRequest() {
    this.persisted = true;
  }

  /**
   * 큐에 보내기 전 요청을 만든다. id 는 여기서 정해 작업 ID 로 쓴다.
   *
   * @throws IllegalArgumentException 필수 값이 비었거나, 이름·주소가 둘 다 있거나 둘 다 없거나, 값이 컬럼 길이를 넘으면
   */
  public CatalogCollectRequest(
      CollectTrigger trigger,
      String requestKey,
      String categoryCode,
      String typeCode,
      String brand,
      String name,
      String productUrl,
      String shadeName) {
    this(trigger, requestKey, categoryCode, typeCode, brand, name, productUrl, shadeName, null);
    if (trigger == CollectTrigger.GUIDE) {
      throw new IllegalArgumentException("영상 분석 요청은 forGuide 로 만든다");
    }
  }

  private CatalogCollectRequest(
      CollectTrigger trigger,
      String requestKey,
      String categoryCode,
      String typeCode,
      String brand,
      String name,
      String productUrl,
      String shadeName,
      CollectGap gap) {
    if ((name == null) == (productUrl == null)) {
      throw new IllegalArgumentException("name 과 productUrl 중 하나만 준다");
    }
    this.id = UUID.randomUUID();
    this.trigger = Objects.requireNonNull(trigger, "trigger");
    this.requestKey = require(requestKey, "requestKey", REQUEST_KEY_MAX_LENGTH);
    this.categoryCode = categoryCode;
    this.typeCode = typeCode;
    this.brand = require(brand, "brand", BRAND_MAX_LENGTH);
    this.name = name == null ? null : require(name, "name", NAME_MAX_LENGTH);
    this.productUrl = productUrl == null ? null : require(productUrl, "productUrl", URL_MAX_LENGTH);
    this.shadeName = optional(shadeName, "shadeName", SHADE_NAME_MAX_LENGTH);
    this.gap = gap;
    this.status = CollectRequestStatus.QUEUED;
  }

  /**
   * 영상 분석 부족분 요청을 만든다(S15P31A306-518).
   *
   * @param target 대상 제품·호수·칸과 칸 이름. 제품 없음이면 모두 비어 있다
   * @throws IllegalArgumentException 제품 없음이 아닌데 대상 제품이 없으면
   */
  public static CatalogCollectRequest forGuide(
      CollectGap gap,
      String requestKey,
      String categoryCode,
      String typeCode,
      String brand,
      String name,
      String productUrl,
      String shadeName,
      Target target) {
    Objects.requireNonNull(gap, "gap");
    Objects.requireNonNull(target, "target");
    if (gap != CollectGap.PRODUCT_MISSING && target.productId() == null) {
      throw new IllegalArgumentException(gap + " 는 대상 제품이 필요하다");
    }
    CatalogCollectRequest request =
        new CatalogCollectRequest(
            CollectTrigger.GUIDE,
            requestKey,
            categoryCode,
            typeCode,
            brand,
            name,
            productUrl,
            shadeName,
            gap);
    request.targetProductId = target.productId();
    request.targetShadeId = target.shadeId();
    request.targetColorId = target.colorId();
    request.targetSlotLabel = optional(target.slotLabel(), "slotLabel", SLOT_LABEL_MAX_LENGTH);
    return request;
  }

  /** 영상 분석 요청의 대상. */
  public record Target(UUID productId, UUID shadeId, UUID colorId, String slotLabel) {
    public static final Target NONE = new Target(null, null, null, null);
  }

  /** 큐에 보냈다. 다시 보내면 보낸 시각을 새로 적는다(같은 jobId 는 워커가 한 번만 반영한다). */
  public void markSent(Instant now) {
    requireOpen();
    this.sendAttempts++;
    this.status = CollectRequestStatus.SENT;
    this.sentAt = Objects.requireNonNull(now, "now");
  }

  /** 보내지 못했다. QUEUED 로 남아 다시 보낸다. */
  public void markSendFailed() {
    requireOpen();
    this.sendAttempts++;
  }

  /** 수집 워커의 결과를 적어 둔다. 판정({@link #finish})과 따로 부른다. */
  public void recordResult(String resultStatus, String resultFile, UUID importRunId) {
    requireOpen();
    this.resultStatus = optional(resultStatus, "resultStatus", RESULT_STATUS_MAX_LENGTH);
    this.resultFile = optional(resultFile, "resultFile", RESULT_FILE_MAX_LENGTH);
    this.importRunId = importRunId;
  }

  /**
   * 요청을 끝낸다.
   *
   * @throws IllegalArgumentException 끝난 상태가 아니면
   * @throws IllegalStateException 이미 끝났으면
   */
  public void finish(CollectRequestStatus end, String reason, Instant now) {
    requireOpen();
    if (Objects.requireNonNull(end, "end").isOpen()) {
      throw new IllegalArgumentException("끝내는 상태가 아니다: " + end);
    }
    this.status = end;
    this.reason = truncate(reason, REASON_MAX_LENGTH);
    this.finishedAt = Objects.requireNonNull(now, "now");
  }

  public boolean isOpen() {
    return status.isOpen();
  }

  @Override
  public boolean isNew() {
    return !persisted;
  }

  @PostPersist
  void markPersisted() {
    this.persisted = true;
  }

  private void requireOpen() {
    if (!status.isOpen()) {
      throw new IllegalStateException("이미 끝난 요청이다: " + status);
    }
  }

  private static String require(String value, String field, int maxLength) {
    if (value == null || value.isBlank()) {
      throw new IllegalArgumentException(field + " 는 비어 있을 수 없다");
    }
    return optional(value, field, maxLength);
  }

  private static String optional(String value, String field, int maxLength) {
    if (value != null && value.length() > maxLength) {
      throw new IllegalArgumentException(field + " 는 " + maxLength + "자까지다");
    }
    return value;
  }

  private static String truncate(String value, int maxLength) {
    return value == null || value.length() <= maxLength ? value : value.substring(0, maxLength);
  }

  public UUID getId() {
    return id;
  }

  public CollectTrigger getTrigger() {
    return trigger;
  }

  public String getRequestKey() {
    return requestKey;
  }

  public String getCategoryCode() {
    return categoryCode;
  }

  public String getTypeCode() {
    return typeCode;
  }

  public String getBrand() {
    return brand;
  }

  public String getName() {
    return name;
  }

  public String getProductUrl() {
    return productUrl;
  }

  public String getShadeName() {
    return shadeName;
  }

  public CollectRequestStatus getStatus() {
    return status;
  }

  public String getReason() {
    return reason;
  }

  public int getSendAttempts() {
    return sendAttempts;
  }

  public Instant getSentAt() {
    return sentAt;
  }

  public String getResultStatus() {
    return resultStatus;
  }

  public String getResultFile() {
    return resultFile;
  }

  public UUID getImportRunId() {
    return importRunId;
  }

  public CollectGap getGap() {
    return gap;
  }

  public Target getTarget() {
    return new Target(targetProductId, targetShadeId, targetColorId, targetSlotLabel);
  }

  public Instant getFinishedAt() {
    return finishedAt;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
