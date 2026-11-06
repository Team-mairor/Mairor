package com.mairor.backend.guides.repository;

import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface GuideRepository extends JpaRepository<Guide, UUID> {

  Optional<Guide> findByAnalysisJobId(UUID analysisJobId);

  /** 영상의 가이드 중 가장 큰 판 번호. 없으면 0. */
  @Query("select coalesce(max(g.version), 0) from Guide g where g.video.id = :videoId")
  int findMaxVersionByVideoId(@Param("videoId") UUID videoId);

  /** 영상의 공개 가이드. {@code uk_guides_video_approved}가 많아야 하나임을 보장한다. */
  Optional<Guide> findByVideoIdAndReviewStatus(UUID videoId, ReviewStatus reviewStatus);

  /** 여러 영상의 공개 가이드(검색 결과에 가이드 상태를 붙일 때). */
  List<Guide> findByVideoIdInAndReviewStatus(Collection<UUID> videoIds, ReviewStatus reviewStatus);

  /** 영상의 가장 최근 판 가이드(검수 상태를 보일 때). */
  Optional<Guide> findFirstByVideoIdOrderByVersionDesc(UUID videoId);
}
