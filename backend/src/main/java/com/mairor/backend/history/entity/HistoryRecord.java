package com.mairor.backend.history.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import lombok.Getter;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** 실행 완료 순간의 리포트 목록 필드와 전체 상세 응답을 고정한다. */
@Getter
@Entity
@Table(
    name = "history_records",
    uniqueConstraints =
        @UniqueConstraint(name = "uk_history_records_execution", columnNames = "execution_id"),
    indexes =
        @Index(
            name = "idx_history_records_owner_completed",
            columnList = "user_id, completed_at, id"))
public class HistoryRecord {
  @Id private UUID id;

  @Column(name = "execution_id", nullable = false, updatable = false)
  private UUID executionId;

  @Column(name = "user_id", nullable = false, updatable = false)
  private UUID userId;

  @Column(name = "guide_id", nullable = false, updatable = false)
  private UUID guideId;

  @Column(name = "guide_version", nullable = false, updatable = false)
  private int guideVersion;

  @Column(name = "video_id", nullable = false, updatable = false)
  private UUID videoId;

  @Column(name = "youtube_video_id", nullable = false, updatable = false, length = 20)
  private String youtubeVideoId;

  @Column(name = "video_title", nullable = false, updatable = false, length = 300)
  private String videoTitle;

  @Column(name = "channel_title", nullable = false, updatable = false, length = 200)
  private String channelTitle;

  @Column(name = "thumbnail_url", length = 1000, updatable = false)
  private String thumbnailUrl;

  @Column(name = "completed_at", nullable = false, updatable = false)
  private Instant completedAt;

  @Column(name = "completed_photo_id", updatable = false)
  private UUID completedPhotoId;

  @Column(name = "step_count", nullable = false, updatable = false)
  private int stepCount;

  @Column(name = "substitute_count", nullable = false, updatable = false)
  private int substituteCount;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "record_snapshot", nullable = false, updatable = false)
  private String recordSnapshot;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  protected HistoryRecord() {}

  public HistoryRecord(
      UUID id,
      UUID executionId,
      UUID userId,
      UUID guideId,
      int guideVersion,
      UUID videoId,
      String youtubeVideoId,
      String videoTitle,
      String channelTitle,
      String thumbnailUrl,
      Instant completedAt,
      UUID completedPhotoId,
      int stepCount,
      int substituteCount,
      String recordSnapshot) {
    this.id = Objects.requireNonNull(id, "id");
    this.executionId = Objects.requireNonNull(executionId, "executionId");
    this.userId = Objects.requireNonNull(userId, "userId");
    this.guideId = Objects.requireNonNull(guideId, "guideId");
    this.videoId = Objects.requireNonNull(videoId, "videoId");
    this.guideVersion = positive(guideVersion, "guideVersion");
    this.youtubeVideoId = text(youtubeVideoId, 20, "youtubeVideoId");
    this.videoTitle = text(videoTitle, 300, "videoTitle");
    this.channelTitle = text(channelTitle, 200, "channelTitle");
    this.thumbnailUrl = thumbnailUrl == null ? null : text(thumbnailUrl, 1000, "thumbnailUrl");
    this.completedAt = Objects.requireNonNull(completedAt, "completedAt");
    this.completedPhotoId = completedPhotoId;
    this.stepCount = nonnegative(stepCount, "stepCount");
    this.substituteCount = nonnegative(substituteCount, "substituteCount");
    this.recordSnapshot = text(recordSnapshot, Integer.MAX_VALUE, "recordSnapshot");
  }

  private static int positive(int value, String name) {
    if (value < 1) throw new IllegalArgumentException(name + " must be positive");
    return value;
  }

  private static int nonnegative(int value, String name) {
    if (value < 0) throw new IllegalArgumentException(name + " must not be negative");
    return value;
  }

  private static String text(String value, int max, String name) {
    Objects.requireNonNull(value, name);
    if (value.isBlank() || value.length() > max) {
      throw new IllegalArgumentException(name + " is invalid");
    }
    return value;
  }
}
