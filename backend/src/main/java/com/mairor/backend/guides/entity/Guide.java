package com.mairor.backend.guides.entity;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.videos.entity.Video;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

/**
 * 분석 작업 하나가 만든 가이드. 단계 입력·설명·영역을 레포 {@code shared/} 스키마 모양의 JSON 그대로 담는다.
 *
 * <ul>
 *   <li>{@code guideInput}: AI 서버에 보낸 가이드 입력({@code shared/guide-input/guide_input.v1.schema.json})
 *   <li>{@code explanation}: AI 콜백의 {@code guide}({@code shared/guide-job}). 콜백 전에는 {@code null}
 *   <li>{@code area}: 가이드 영역({@code shared/guide-area}). AI 는 설명과 영역을 콜백 한 번에 보내므로, 프레임 없이 맡긴 작업만
 *       {@code null}이다
 * </ul>
 *
 * <p>같은 영상의 공개(APPROVED) 가이드는 하나뿐이다. 부분 유일 인덱스({@value #VIDEO_APPROVED_UNIQUE})라 {@code
 * db/schema/analysis.sql}에만 있다. 검수 상태 전이는 S15P31A306-311 에서 더한다.
 */
@Entity
@Table(
    name = "guides",
    uniqueConstraints = {
      @UniqueConstraint(name = Guide.ANALYSIS_JOB_UNIQUE, columnNames = "analysis_job_id"),
      @UniqueConstraint(
          name = Guide.VIDEO_VERSION_UNIQUE,
          columnNames = {"video_id", "version"})
    })
public class Guide {

  public static final String VIDEO_FK = "fk_guides_video";
  public static final String ANALYSIS_JOB_FK = "fk_guides_analysis_job";
  public static final String REVIEWED_BY_FK = "fk_guides_reviewed_by";
  public static final String ANALYSIS_JOB_UNIQUE = "uk_guides_analysis_job";
  public static final String VIDEO_VERSION_UNIQUE = "uk_guides_video_version";
  public static final String VIDEO_APPROVED_UNIQUE = "uk_guides_video_approved";

  public static final int MESH_VERSION_MAX_LENGTH = 10;
  public static final int FRAMES_MANIFEST_KEY_MAX_LENGTH = 500;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "video_id", nullable = false, foreignKey = @ForeignKey(name = VIDEO_FK))
  private Video video;

  // 작업당 가이드 하나는 이름 있는 유일 제약(ANALYSIS_JOB_UNIQUE)으로 지킨다. @OneToOne 은 Hibernate 가 이름 없는 유일 제약을 더 만든다
  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(
      name = "analysis_job_id",
      nullable = false,
      foreignKey = @ForeignKey(name = ANALYSIS_JOB_FK))
  private AnalysisJob analysisJob;

  /** 같은 영상 안에서 1부터 오른다. 매칭의 stale 판정(guideVersion)에 쓴다. */
  @Column(nullable = false)
  private int version;

  /** 원본 제품 연결 또는 연결된 슬롯 색 변경 버전. 가이드 콘텐츠 {@link #version}과 별개다. */
  @Column(name = "reference_version", nullable = false)
  private int referenceVersion;

  @Enumerated(EnumType.STRING)
  @Column(name = "review_status", nullable = false, length = 20)
  private ReviewStatus reviewStatus;

  /** 가이드 영역의 얼굴 메시 버전({@code "v1"}). 영역이 오기 전에는 {@code null}. */
  @Column(name = "mesh_version", length = MESH_VERSION_MAX_LENGTH)
  private String meshVersion;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "guide_input", nullable = false)
  private String guideInput;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "explanation")
  private String explanation;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "area")
  private String area;

  @Column(name = "frames_manifest_key", length = FRAMES_MANIFEST_KEY_MAX_LENGTH)
  private String framesManifestKey;

  @Column(name = "reviewed_at")
  private Instant reviewedAt;

  @Column(name = "reviewed_by")
  private UUID reviewedBy;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected Guide() {}

  /**
   * 단계 입력만 있는(NOT_READY) 가이드를 만든다.
   *
   * @param guideInput AI 서버에 보낼 가이드 입력 JSON 문자열
   */
  public Guide(AnalysisJob analysisJob, int version, String guideInput) {
    this.analysisJob = Objects.requireNonNull(analysisJob, "analysisJob");
    this.video = analysisJob.getVideo();
    this.version = version;
    this.guideInput = Objects.requireNonNull(guideInput, "guideInput");
    this.reviewStatus = ReviewStatus.NOT_READY;
  }

  public UUID getId() {
    return id;
  }

  public Video getVideo() {
    return video;
  }

  public AnalysisJob getAnalysisJob() {
    return analysisJob;
  }

  public int getVersion() {
    return version;
  }

  public int getReferenceVersion() {
    return referenceVersion;
  }

  /** 연결 결과가 실제로 달라졌을 때 호출한다. 연결 슬롯 색상 변경은 DB 트리거가 올린다. */
  public void incrementReferenceVersion() {
    referenceVersion = Math.incrementExact(referenceVersion);
  }

  public ReviewStatus getReviewStatus() {
    return reviewStatus;
  }

  public String getMeshVersion() {
    return meshVersion;
  }

  public String getGuideInput() {
    return guideInput;
  }

  /** 같은 작업을 다시 돌려(멈춘 뒤 대기열로 되돌림) 단계를 새로 뽑았을 때 입력을 바꾼다. 설명·영역은 아직 없다. */
  /**
   * AI 콜백의 쉬운 설명·가이드 영역을 저장한다(NOT_READY → PENDING). 저장하는 쪽이 같은 트랜잭션에서 바로 공개한다(검수 없음,
   * S15P31A306-409).
   *
   * @param explanation 콜백 {@code guide} JSON
   * @param area 콜백 {@code area} JSON. 프레임 없이 맡긴 작업이면 null
   * @param meshVersion {@code area.meshVersion}. 영역이 없으면 null
   */
  public void recordAiResult(String explanation, String area, String meshVersion) {
    this.explanation = Objects.requireNonNull(explanation, "explanation");
    this.area = area;
    this.meshVersion = meshVersion;
    this.reviewStatus = ReviewStatus.PENDING;
  }

  /** 공개(승인). PENDING 일 때만. 같은 영상의 이전 공개 판은 호출하는 쪽이 먼저 내린다(공개 하나). */
  public void approve(Instant now) {
    requirePending("승인");
    this.reviewStatus = ReviewStatus.APPROVED;
    this.reviewedAt = Objects.requireNonNull(now, "now");
  }

  /** 반려. 공개 전(PENDING)이면 공개하지 않고, 공개된 가이드(APPROVED)면 내린다. */
  public void reject(Instant now) {
    if (reviewStatus != ReviewStatus.PENDING && reviewStatus != ReviewStatus.APPROVED) {
      throw new IllegalStateException("가이드 " + id + " 은 " + reviewStatus + " 상태라 반려할 수 없습니다.");
    }
    this.reviewStatus = ReviewStatus.REJECTED;
    this.reviewedAt = Objects.requireNonNull(now, "now");
  }

  /** 새 판이 승인되어 공개에서 내려간다(APPROVED → REJECTED). */
  public void supersede(Instant now) {
    if (reviewStatus != ReviewStatus.APPROVED) {
      throw new IllegalStateException("공개 가이드만 내릴 수 있습니다: " + id + " " + reviewStatus);
    }
    this.reviewStatus = ReviewStatus.REJECTED;
    this.reviewedAt = Objects.requireNonNull(now, "now");
  }

  private void requirePending(String action) {
    if (reviewStatus != ReviewStatus.PENDING) {
      throw new IllegalStateException(
          "가이드 " + id + " 은 " + reviewStatus + " 상태라 " + action + " 할 수 없습니다.");
    }
  }

  /** 프레임 목록({@code frames.json})의 저장소 키. */
  public void useFramesManifest(String key) {
    this.framesManifestKey = Objects.requireNonNull(key, "key");
  }

  /** 프레임을 싣지 않고 AI 에 맡긴다. 이 키는 "AI 에 보낸 프레임 목록"이고, 콜백 검사는 키가 있으면 영역을 요구하므로 보내지 않았으면 비운다. */
  public void forgetFramesManifest() {
    this.framesManifestKey = null;
  }

  public void replaceGuideInput(String guideInput) {
    this.guideInput = Objects.requireNonNull(guideInput, "guideInput");
  }

  public String getExplanation() {
    return explanation;
  }

  public String getArea() {
    return area;
  }

  public String getFramesManifestKey() {
    return framesManifestKey;
  }

  public Instant getReviewedAt() {
    return reviewedAt;
  }

  public UUID getReviewedBy() {
    return reviewedBy;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
