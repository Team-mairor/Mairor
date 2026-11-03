package com.mairor.backend.guides.repository;

import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface GuideRepository extends JpaRepository<Guide, UUID> {

  Optional<Guide> findByAnalysisJobId(UUID analysisJobId);

  /** 영상의 공개 가이드. {@code uk_guides_video_approved}가 많아야 하나임을 보장한다. */
  Optional<Guide> findByVideoIdAndReviewStatus(UUID videoId, ReviewStatus reviewStatus);
}
