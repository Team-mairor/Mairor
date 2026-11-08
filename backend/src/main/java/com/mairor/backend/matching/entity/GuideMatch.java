package com.mairor.backend.matching.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** 생성 시점의 파우치·가이드 매칭과 응답 스냅샷. stale 조회에서도 이 행은 다시 계산하지 않는다. */
@Entity
@Table(
    name = "guide_matches",
    indexes =
        @Index(
            name = GuideMatch.USER_CREATED_INDEX,
            columnList = "user_id, created_at DESC, id DESC"))
public class GuideMatch {

  public static final String USER_FK = "fk_guide_matches_user";
  public static final String GUIDE_FK = "fk_guide_matches_guide";
  public static final String USER_CREATED_INDEX = "idx_guide_matches_user_created";

  @Id private UUID id;

  @Column(name = "user_id", nullable = false)
  private UUID userId;

  @Column(name = "guide_id", nullable = false)
  private UUID guideId;

  @Column(name = "guide_version", nullable = false)
  private int guideVersion;

  @Column(name = "pouch_version", nullable = false)
  private long pouchVersion;

  @Column(name = "reference_version", nullable = false)
  private int referenceVersion;

  @Column(name = "compatibility_version", nullable = false)
  private int compatibilityVersion;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "match_snapshot", nullable = false)
  private String matchSnapshot;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  protected GuideMatch() {}

  public GuideMatch(
      UUID id,
      UUID userId,
      UUID guideId,
      int guideVersion,
      long pouchVersion,
      int referenceVersion,
      int compatibilityVersion,
      String matchSnapshot) {
    this.id = Objects.requireNonNull(id, "id");
    this.userId = Objects.requireNonNull(userId, "userId");
    this.guideId = Objects.requireNonNull(guideId, "guideId");
    if (guideVersion < 1 || pouchVersion < 0 || referenceVersion < 0 || compatibilityVersion < 1) {
      throw new IllegalArgumentException("매칭 버전 값이 유효하지 않다");
    }
    this.guideVersion = guideVersion;
    this.pouchVersion = pouchVersion;
    this.referenceVersion = referenceVersion;
    this.compatibilityVersion = compatibilityVersion;
    this.matchSnapshot = requireJson(matchSnapshot);
  }

  private static String requireJson(String value) {
    String json = Objects.requireNonNull(value, "matchSnapshot").trim();
    if (json.isEmpty()) {
      throw new IllegalArgumentException("매칭 스냅샷은 비어 있을 수 없다");
    }
    return json;
  }

  public UUID getId() {
    return id;
  }

  public UUID getUserId() {
    return userId;
  }

  public UUID getGuideId() {
    return guideId;
  }

  public int getGuideVersion() {
    return guideVersion;
  }

  public long getPouchVersion() {
    return pouchVersion;
  }

  public int getReferenceVersion() {
    return referenceVersion;
  }

  public int getCompatibilityVersion() {
    return compatibilityVersion;
  }

  public String getMatchSnapshot() {
    return matchSnapshot;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
