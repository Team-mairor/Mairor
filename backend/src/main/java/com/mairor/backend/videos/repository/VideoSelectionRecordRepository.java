package com.mairor.backend.videos.repository;

import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.videos.entity.VideoSelectionRecord;
import com.mairor.backend.videos.service.PopularVideoRow;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface VideoSelectionRecordRepository extends JpaRepository<VideoSelectionRecord, UUID> {

  /**
   * {@code since} 이후 선택 기록으로 센 인기 영상. 고른 서로 다른 회원 수가 많은 순이고(같은 회원이 여러 번 골라도 1), 같으면 마지막 선택이 늦은 순 →
   * 영상 ID 순으로 순서를 고정한다. 영상마다 {@code guideStatus} 가이드(공개 가이드는 영상마다 하나)가 있으면 그 ID 를 붙인다.
   */
  @Query(
      """
      select new com.mairor.backend.videos.service.PopularVideoRow(
          v.id, v.youtubeVideoId, v.title, v.channelTitle, v.durationSeconds,
          v.thumbnailUrl, v.publishedAt, g.id, count(distinct s.userId), max(s.selectedAt))
      from VideoSelectionRecord s
      join Video v on v.id = s.videoId
      left join Guide g on g.video = v and g.reviewStatus = :guideStatus
      where s.selectedAt >= :since
      group by v.id, v.youtubeVideoId, v.title, v.channelTitle, v.durationSeconds,
          v.thumbnailUrl, v.publishedAt, g.id
      order by count(distinct s.userId) desc, max(s.selectedAt) desc, v.id
      """)
  List<PopularVideoRow> findPopular(
      @Param("since") Instant since, @Param("guideStatus") ReviewStatus guideStatus, Limit limit);
}
