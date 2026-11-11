package com.mairor.backend.videos.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/**
 * 회원이 영상을 고른 기록 한 건(API-VIDEO-001). 선택이 성공할 때마다 한 줄 남고, 인기 Top 4(API-VIDEO-005)를 셀 때 쓴다.
 *
 * <p>선택은 분석할 수 있는 영상만 성공하므로 분석 불가 영상은 남지 않는다. 영상 · 회원과는 ID 로만 잇는다.
 */
@Entity
@Table(name = "video_selections")
public class VideoSelectionRecord {

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "video_id", nullable = false, updatable = false)
  private UUID videoId;

  @Column(name = "user_id", nullable = false, updatable = false)
  private UUID userId;

  @Column(name = "selected_at", nullable = false, updatable = false)
  private Instant selectedAt;

  protected VideoSelectionRecord() {}

  public VideoSelectionRecord(UUID videoId, UUID userId, Instant selectedAt) {
    this.videoId = Objects.requireNonNull(videoId, "videoId");
    this.userId = Objects.requireNonNull(userId, "userId");
    this.selectedAt = Objects.requireNonNull(selectedAt, "selectedAt");
  }

  public UUID getId() {
    return id;
  }

  public UUID getVideoId() {
    return videoId;
  }

  public UUID getUserId() {
    return userId;
  }

  public Instant getSelectedAt() {
    return selectedAt;
  }
}
