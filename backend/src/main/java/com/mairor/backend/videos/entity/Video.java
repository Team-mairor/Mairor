package com.mairor.backend.videos.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
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
 * 유튜브 영상 한 편. 같은 {@code youtubeVideoId}는 행 하나다({@value #YOUTUBE_VIDEO_ID_UNIQUE}).
 *
 * <p>메타(제목·채널·길이·썸네일·챕터)는 YouTube Data API 값이며 {@code metaRefreshedAt}부터 30일 안에 다시 받는다(ADR-002). 영상
 * 선택 화면은 임베드 재생을 하지 않아서(11.03) 재생 가능 여부는 저장하지 않는다.
 *
 * <p>{@code source*}는 분석에 쓴 영상 파일의 값(ffprobe)이다. 파일을 확보하기 전에는 {@code null}이다.
 */
@Entity
@Table(
    name = "videos",
    uniqueConstraints =
        @UniqueConstraint(name = Video.YOUTUBE_VIDEO_ID_UNIQUE, columnNames = "youtube_video_id"))
public class Video {

  public static final String YOUTUBE_VIDEO_ID_UNIQUE = "uk_videos_youtube_video_id";

  public static final int YOUTUBE_VIDEO_ID_MAX_LENGTH = 20;
  public static final int TITLE_MAX_LENGTH = 300;
  public static final int CHANNEL_TITLE_MAX_LENGTH = 200;
  public static final int THUMBNAIL_URL_MAX_LENGTH = 1000;
  public static final int SOURCE_OBJECT_KEY_MAX_LENGTH = 500;

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(name = "youtube_video_id", nullable = false, length = YOUTUBE_VIDEO_ID_MAX_LENGTH)
  private String youtubeVideoId;

  @Column(nullable = false, length = TITLE_MAX_LENGTH)
  private String title;

  @Column(name = "channel_title", nullable = false, length = CHANNEL_TITLE_MAX_LENGTH)
  private String channelTitle;

  @Column(name = "duration_seconds", nullable = false)
  private int durationSeconds;

  @Column(name = "thumbnail_url", length = THUMBNAIL_URL_MAX_LENGTH)
  private String thumbnailUrl;

  @Column(name = "published_at")
  private Instant publishedAt;

  /** 설명란 챕터 JSON 배열 {@code [{"startSeconds": 0, "label": "시작"}]}. 없으면 {@code []}. */
  @JdbcTypeCode(SqlTypes.JSON)
  @Column(nullable = false)
  private String chapters;

  @Column(name = "source_object_key", length = SOURCE_OBJECT_KEY_MAX_LENGTH)
  private String sourceObjectKey;

  @Column(name = "source_width")
  private Integer sourceWidth;

  @Column(name = "source_height")
  private Integer sourceHeight;

  @Column(name = "source_fps")
  private Double sourceFps;

  @Column(name = "source_duration_seconds")
  private Double sourceDurationSeconds;

  @Column(name = "meta_refreshed_at", nullable = false)
  private Instant metaRefreshedAt;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected Video() {}

  /**
   * @param chapters 설명란 챕터 JSON 배열 문자열. 없으면 {@code "[]"}
   * @param metaRefreshedAt 메타를 YouTube 에서 받은 시각
   */
  public Video(
      String youtubeVideoId,
      String title,
      String channelTitle,
      int durationSeconds,
      String thumbnailUrl,
      Instant publishedAt,
      String chapters,
      Instant metaRefreshedAt) {
    this.youtubeVideoId = Objects.requireNonNull(youtubeVideoId, "youtubeVideoId");
    this.title = Objects.requireNonNull(title, "title");
    this.channelTitle = Objects.requireNonNull(channelTitle, "channelTitle");
    this.durationSeconds = durationSeconds;
    this.thumbnailUrl = thumbnailUrl;
    this.publishedAt = publishedAt;
    this.chapters = Objects.requireNonNull(chapters, "chapters");
    this.metaRefreshedAt = Objects.requireNonNull(metaRefreshedAt, "metaRefreshedAt");
  }

  /** 분석에 쓸 영상 파일의 위치와 ffprobe 값을 기록한다. */
  public void attachSource(
      String objectKey, int width, int height, double fps, double durationSeconds) {
    this.sourceObjectKey = Objects.requireNonNull(objectKey, "objectKey");
    this.sourceWidth = width;
    this.sourceHeight = height;
    this.sourceFps = fps;
    this.sourceDurationSeconds = durationSeconds;
  }

  public UUID getId() {
    return id;
  }

  public String getYoutubeVideoId() {
    return youtubeVideoId;
  }

  public String getTitle() {
    return title;
  }

  public String getChannelTitle() {
    return channelTitle;
  }

  public int getDurationSeconds() {
    return durationSeconds;
  }

  public String getThumbnailUrl() {
    return thumbnailUrl;
  }

  public Instant getPublishedAt() {
    return publishedAt;
  }

  public String getChapters() {
    return chapters;
  }

  public String getSourceObjectKey() {
    return sourceObjectKey;
  }

  public Integer getSourceWidth() {
    return sourceWidth;
  }

  public Integer getSourceHeight() {
    return sourceHeight;
  }

  public Double getSourceFps() {
    return sourceFps;
  }

  public Double getSourceDurationSeconds() {
    return sourceDurationSeconds;
  }

  public Instant getMetaRefreshedAt() {
    return metaRefreshedAt;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
