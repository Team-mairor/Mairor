package com.mairor.backend.products.entity;

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
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.util.stream.Collectors;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 적재 실행의 건. 수집 상품 한 건({@code itemKey})의 처리 결과이고, {@code (run, itemKey)}가 유니크라 같은 건을 다시 보내도 한 번만
 * 처리한다.
 *
 * <p>색 칸의 {@code source_item_id}가 이 행을 가리켜 칸의 현재 값이 어느 건에서 왔는지 찾아간다. 그 건의 근거(이미지·영역·방법)는 실행 결과 파일에서
 * {@code itemKey}로 찾는다. 사유는 코드의 쉼표 문자열이다. 오류 요약({@code message})에는 스택 트레이스를 넣지 않는다.
 */
@Entity
@Table(
    name = "catalog_import_items",
    uniqueConstraints =
        @UniqueConstraint(
            name = CatalogImportItem.RUN_ITEM_UNIQUE,
            columnNames = {"run_id", "item_key"}),
    indexes = {
      @Index(name = CatalogImportItem.RUN_OUTCOME_INDEX, columnList = "run_id, outcome"),
      @Index(name = CatalogImportItem.PRODUCT_INDEX, columnList = "product_id")
    })
public class CatalogImportItem {

  public static final String RUN_ITEM_UNIQUE = "uk_catalog_import_items_run_item";
  public static final String RUN_OUTCOME_INDEX = "idx_catalog_import_items_run_outcome";
  public static final String PRODUCT_INDEX = "idx_catalog_import_items_product";
  public static final String RUN_FK = "fk_catalog_import_items_run";
  public static final String PRODUCT_FK = "fk_catalog_import_items_product";
  public static final String OUTCOME_CHECK = "ck_catalog_import_items_outcome";
  public static final String COLORS_CHECK = "ck_catalog_import_items_colors";

  public static final int ITEM_KEY_MAX_LENGTH = 100;
  public static final int SOURCE_MAX_LENGTH = 100;
  public static final int SOURCE_PRODUCT_ID_MAX_LENGTH = 100;
  public static final int REASONS_MAX_LENGTH = 1000;
  public static final int MESSAGE_MAX_LENGTH = 500;

  private static final String REASON_SEPARATOR = ",";

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "run_id", nullable = false, foreignKey = @ForeignKey(name = RUN_FK))
  private CatalogImportRun run;

  @Column(name = "item_key", nullable = false, length = ITEM_KEY_MAX_LENGTH)
  private String itemKey;

  @Column(length = SOURCE_MAX_LENGTH)
  private String source;

  @Column(name = "source_product_id", length = SOURCE_PRODUCT_ID_MAX_LENGTH)
  private String sourceProductId;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private ImportItemOutcome outcome;

  /** 일부만 반영했거나 기존 값을 지킨 사유가 있는가. */
  @Column(nullable = false)
  private boolean partial;

  @Column(nullable = false, length = REASONS_MAX_LENGTH)
  private String reasons;

  /** 반영한 제품. 반영하지 않았으면 {@code null}. */
  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "product_id", foreignKey = @ForeignKey(name = PRODUCT_FK))
  private Product product;

  @Column(name = "colors_applied", nullable = false)
  private int colorsApplied;

  @Column(length = MESSAGE_MAX_LENGTH)
  private String message;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected CatalogImportItem() {}

  /**
   * 건을 처음 기록한다.
   *
   * @param source 수집 상품의 출처. 읽지 못한 건이면 {@code null}
   * @param sourceProductId 수집 상품의 상품 번호. 읽지 못한 건이면 {@code null}
   * @throws IllegalArgumentException {@code itemKey}가 비었거나 길면, 값이 컬럼 길이를 넘으면
   */
  public CatalogImportItem(
      CatalogImportRun run, String itemKey, String source, String sourceProductId) {
    this.run = Objects.requireNonNull(run, "run");
    if (itemKey == null || itemKey.isBlank()) {
      throw new IllegalArgumentException("itemKey 는 비어 있을 수 없다");
    }
    this.itemKey = limited(itemKey, "itemKey", ITEM_KEY_MAX_LENGTH);
    this.source = limited(source, "source", SOURCE_MAX_LENGTH);
    this.sourceProductId =
        limited(sourceProductId, "sourceProductId", SOURCE_PRODUCT_ID_MAX_LENGTH);
  }

  /**
   * 처리 결과를 기록한다. 같은 건을 다시 처리하면 이 메서드로 결과를 덮어쓴다.
   *
   * @param reasonCodes 사유 코드. 없으면 빈 목록
   * @param product 반영한 제품. 반영하지 않았으면 {@code null}
   * @param colorsApplied 이 건이 저장하거나 바꾼 색 칸 수
   * @param message 오류 요약. 길면 잘라 저장한다
   * @throws IllegalArgumentException 색 칸 수가 음수이거나 사유가 컬럼 길이를 넘으면
   */
  public void recordResult(
      ImportItemOutcome outcome,
      boolean partial,
      Collection<String> reasonCodes,
      Product product,
      int colorsApplied,
      String message) {
    if (colorsApplied < 0) {
      throw new IllegalArgumentException("colorsApplied 는 0 이상이어야 한다");
    }
    this.outcome = Objects.requireNonNull(outcome, "outcome");
    this.partial = partial;
    this.reasons = joinReasons(reasonCodes);
    this.product = product;
    this.colorsApplied = colorsApplied;
    this.message = truncate(message, MESSAGE_MAX_LENGTH);
  }

  /** 결과를 기록하지 않은 채 저장하면 DB 가 NOT NULL 로 거절하기 전에 이유를 알려 준다. */
  @PrePersist
  void requireResult() {
    if (outcome == null) {
      throw new IllegalStateException("recordResult 로 결과를 기록한 뒤 저장해야 한다");
    }
  }

  /** 사유 코드. 없으면 빈 목록이다. */
  public List<String> getReasonCodes() {
    if (reasons == null || reasons.isEmpty()) {
      return List.of();
    }
    return List.of(reasons.split(REASON_SEPARATOR));
  }

  private static String joinReasons(Collection<String> codes) {
    if (codes == null || codes.isEmpty()) {
      return "";
    }
    String joined =
        codes.stream().sorted().distinct().collect(Collectors.joining(REASON_SEPARATOR));
    if (joined.length() > REASONS_MAX_LENGTH) {
      throw new IllegalArgumentException("사유는 " + REASONS_MAX_LENGTH + "자까지다");
    }
    return joined;
  }

  private static String limited(String value, String field, int maxLength) {
    if (value != null && value.length() > maxLength) {
      throw new IllegalArgumentException(field + " 는 " + maxLength + "자까지다");
    }
    return value;
  }

  private static String truncate(String value, int maxLength) {
    if (value == null || value.length() <= maxLength) {
      return value;
    }
    return value.substring(0, maxLength - 1) + "…";
  }

  public UUID getId() {
    return id;
  }

  public CatalogImportRun getRun() {
    return run;
  }

  public String getItemKey() {
    return itemKey;
  }

  public String getSource() {
    return source;
  }

  public String getSourceProductId() {
    return sourceProductId;
  }

  public ImportItemOutcome getOutcome() {
    return outcome;
  }

  public boolean isPartial() {
    return partial;
  }

  public String getReasons() {
    return reasons;
  }

  public Product getProduct() {
    return product;
  }

  public int getColorsApplied() {
    return colorsApplied;
  }

  public String getMessage() {
    return message;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
