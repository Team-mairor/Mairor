package com.mairor.backend.guides.repository;

import com.mairor.backend.guides.entity.GuideStepProductLink;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface GuideStepProductLinkRepository extends JpaRepository<GuideStepProductLink, UUID> {

  @EntityGraph(attributePaths = {"product", "shade", "color"})
  List<GuideStepProductLink> findByGuideIdOrderByStepIdAsc(UUID guideId);

  Optional<GuideStepProductLink> findByGuideIdAndStepId(UUID guideId, String stepId);

  @Query(
      "select case when count(link) > 0 then true else false end"
          + " from GuideStepProductLink link where link.color.shade.id = :shadeId")
  boolean existsColorReferenceByShadeId(@Param("shadeId") UUID shadeId);
}
