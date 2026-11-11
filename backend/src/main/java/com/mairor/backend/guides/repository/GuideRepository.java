package com.mairor.backend.guides.repository;

import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import jakarta.persistence.LockModeType;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface GuideRepository extends JpaRepository<Guide, UUID> {

  Optional<Guide> findByAnalysisJobId(UUID analysisJobId);

  /** 연결 결과를 바꾸는 트랜잭션이 같은 가이드의 버전을 직렬화한다. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select g from Guide g where g.id = :guideId")
  Optional<Guide> findByIdForUpdate(@Param("guideId") UUID guideId);

  /** 실행 스냅샷을 저장하는 동안 검수·연결 버전 변경을 막는다. 카탈로그 writer와 같이 가이드 → 회원 순으로 잠근다. */
  @Lock(LockModeType.PESSIMISTIC_READ)
  @Query("select g from Guide g where g.id = :guideId")
  Optional<Guide> findByIdForShare(@Param("guideId") UUID guideId);

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
