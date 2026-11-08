package com.mairor.backend.analysis.entity;

import com.mairor.backend.analysis.service.ReceiptType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/**
 * 회원의 분석 요청 한 건(API-VIDEO-002). 새 작업을 만든 요청({@code NEW_JOB})과 진행 중 작업에 합류한 요청({@code JOINED_JOB})만
 * 남긴다. 합류한 회원의 조회 권한과 회원별 일일 신규 분석 한도에 쓴다.
 *
 * <p>작업 · 회원과는 ID 로만 잇는다. 같은 회원 · 같은 작업은 한 줄이다({@value #JOB_USER_UNIQUE}).
 */
@Entity
@Table(name = "analysis_job_requests")
public class AnalysisJobRequestRecord {

  public static final String JOB_USER_UNIQUE = "uk_analysis_job_requests_job_user";

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "analysis_job_id", nullable = false)
  private UUID analysisJobId;

  @Column(name = "user_id", nullable = false)
  private UUID userId;

  @Enumerated(EnumType.STRING)
  @Column(name = "receipt_type", nullable = false, length = 20)
  private ReceiptType receiptType;

  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  protected AnalysisJobRequestRecord() {}

  /**
   * @param receiptType {@code NEW_JOB} 또는 {@code JOINED_JOB}. 재사용은 작업이 없어 남기지 않는다
   * @param createdAt 요청 시각. 일일 한도를 이 값으로 센다
   */
  public AnalysisJobRequestRecord(
      UUID analysisJobId, UUID userId, ReceiptType receiptType, Instant createdAt) {
    if (receiptType == ReceiptType.REUSED_GUIDE) {
      throw new IllegalArgumentException("가이드 재사용은 요청 기록을 남기지 않습니다.");
    }
    this.analysisJobId = Objects.requireNonNull(analysisJobId, "analysisJobId");
    this.userId = Objects.requireNonNull(userId, "userId");
    this.receiptType = Objects.requireNonNull(receiptType, "receiptType");
    this.createdAt = Objects.requireNonNull(createdAt, "createdAt");
  }

  public UUID getId() {
    return id;
  }

  public UUID getAnalysisJobId() {
    return analysisJobId;
  }

  public UUID getUserId() {
    return userId;
  }

  public ReceiptType getReceiptType() {
    return receiptType;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
