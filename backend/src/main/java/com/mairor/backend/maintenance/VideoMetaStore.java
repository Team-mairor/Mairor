package com.mairor.backend.maintenance;

import com.mairor.backend.common.external.youtube.YouTubeVideo;
import com.mairor.backend.videos.entity.Video;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** 영상 메타 갱신이 쓰는 {@code videos} 읽기 · 쓰기. 영상 선택(API-VIDEO-001)의 upsert 와 같은 칸을 같은 규칙(길이 자르기)으로 쓴다. */
@Component
public class VideoMetaStore {

  /** 다시 받을 영상. */
  public record StaleVideo(UUID id, String youtubeVideoId) {}

  private final JdbcTemplate jdbc;

  VideoMetaStore(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  /** 메타를 {@code before} 전에 받은 영상을 오래된 것부터 {@code limit}개. */
  public List<StaleVideo> staleBefore(Instant before, int limit) {
    return jdbc.query(
        "select id, youtube_video_id from videos where meta_refreshed_at < ?"
            + " order by meta_refreshed_at, id limit ?",
        (rs, i) -> new StaleVideo(rs.getObject("id", UUID.class), rs.getString("youtube_video_id")),
        Timestamp.from(before),
        limit);
  }

  /** YouTube 에서 받은 값으로 메타를 바꾼다. 길이가 0(라이브 등)이면 길이만 그대로 둔다. */
  public void update(UUID id, YouTubeVideo found, String chaptersJson, Instant now) {
    Timestamp at = Timestamp.from(now);
    jdbc.update(
        "update videos set title = ?, channel_title = ?,"
            + " duration_seconds = case when ? > 0 then ? else duration_seconds end,"
            + " thumbnail_url = ?, published_at = ?, chapters = cast(? as jsonb),"
            + " meta_refreshed_at = ?, updated_at = ? where id = ?",
        truncate(found.title(), Video.TITLE_MAX_LENGTH),
        truncate(found.channelTitle(), Video.CHANNEL_TITLE_MAX_LENGTH),
        found.durationSeconds(),
        found.durationSeconds(),
        thumbnailOrNull(found.thumbnailUrl()),
        found.publishedAt() == null ? null : Timestamp.from(found.publishedAt()),
        chaptersJson,
        at,
        at,
        id);
  }

  /** YouTube 에 없는 영상(삭제 · 비공개). 메타는 마지막 값으로 두고 확인한 시각만 남겨 매일 다시 묻지 않게 한다. */
  public void markChecked(UUID id, Instant now) {
    Timestamp at = Timestamp.from(now);
    jdbc.update("update videos set meta_refreshed_at = ?, updated_at = ? where id = ?", at, at, id);
  }

  private static String truncate(String value, int max) {
    return value.length() <= max ? value : value.substring(0, max);
  }

  private static String thumbnailOrNull(String url) {
    return url == null || url.length() > Video.THUMBNAIL_URL_MAX_LENGTH ? null : url;
  }
}
