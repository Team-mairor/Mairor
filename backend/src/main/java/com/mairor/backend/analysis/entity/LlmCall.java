package com.mairor.backend.analysis.entity;

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
import org.hibernate.annotations.CreationTimestamp;

/**
 * LLM 호출 기록 한 건. 토큰·소요 시간으로 비용을 보고, 응답 원문을 남겨 같은 영상을 다시 부르지 않고도 결과를 다시 읽을 수 있게 한다.
 *
 * <p>분석 작업과는 ID 로만 잇는다({@value #ANALYSIS_JOB_FK}). 작업 밖에서 부른 호출은 {@code analysisJobId}가 {@code
 * null}이다.
 */
@Entity
@Table(name = "llm_calls")
public class LlmCall {

  public static final String ANALYSIS_JOB_FK = "fk_llm_calls_analysis_job";

  public static final int PROVIDER_MAX_LENGTH = 30;
  public static final int MODEL_MAX_LENGTH = 80;
  public static final int PURPOSE_MAX_LENGTH = 40;
  public static final int ERROR_CODE_MAX_LENGTH = 50;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "analysis_job_id")
  private UUID analysisJobId;

  /** 호출 경로. 예: {@code GMS}, {@code GEMINI}(Google 직접). */
  @Column(nullable = false, length = PROVIDER_MAX_LENGTH)
  private String provider;

  @Column(nullable = false, length = MODEL_MAX_LENGTH)
  private String model;

  /** 무엇을 위해 불렀는지. 예: {@code STEP_EXTRACTION}. */
  @Column(nullable = false, length = PURPOSE_MAX_LENGTH)
  private String purpose;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private LlmCallStatus status;

  @Column(name = "input_tokens")
  private Integer inputTokens;

  @Column(name = "output_tokens")
  private Integer outputTokens;

  @Column(name = "duration_ms", nullable = false)
  private int durationMs;

  @Column(name = "error_code", length = ERROR_CODE_MAX_LENGTH)
  private String errorCode;

  @Column(name = "response_body", columnDefinition = "text")
  private String responseBody;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  protected LlmCall() {}

  /**
   * @param analysisJobId 분석 작업 ID. 작업 밖 호출이면 {@code null}
   * @param errorCode 실패 원인 코드. 성공이면 {@code null}
   * @param responseBody 응답 원문. 없으면 {@code null}
   */
  public LlmCall(
      UUID analysisJobId,
      String provider,
      String model,
      String purpose,
      LlmCallStatus status,
      Integer inputTokens,
      Integer outputTokens,
      int durationMs,
      String errorCode,
      String responseBody) {
    this.analysisJobId = analysisJobId;
    this.provider = Objects.requireNonNull(provider, "provider");
    this.model = Objects.requireNonNull(model, "model");
    this.purpose = Objects.requireNonNull(purpose, "purpose");
    this.status = Objects.requireNonNull(status, "status");
    this.inputTokens = inputTokens;
    this.outputTokens = outputTokens;
    this.durationMs = durationMs;
    this.errorCode = errorCode;
    this.responseBody = responseBody;
  }

  public UUID getId() {
    return id;
  }

  public UUID getAnalysisJobId() {
    return analysisJobId;
  }

  public String getProvider() {
    return provider;
  }

  public String getModel() {
    return model;
  }

  public String getPurpose() {
    return purpose;
  }

  public LlmCallStatus getStatus() {
    return status;
  }

  public Integer getInputTokens() {
    return inputTokens;
  }

  public Integer getOutputTokens() {
    return outputTokens;
  }

  public int getDurationMs() {
    return durationMs;
  }

  public String getErrorCode() {
    return errorCode;
  }

  public String getResponseBody() {
    return responseBody;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
