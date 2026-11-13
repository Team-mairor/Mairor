package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.CatalogCollectRequestGuide;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogCollectRequestGuideRepository
    extends JpaRepository<CatalogCollectRequestGuide, UUID> {

  List<CatalogCollectRequestGuide> findByRequestId(UUID requestId);

  List<CatalogCollectRequestGuide> findByRequestIdInOrderByCreatedAtAsc(
      Collection<UUID> requestIds);

  /** 가이드가 이 시각 뒤에 붙은 요청 수. 가이드당 한도에 쓴다. */
  long countByGuideIdAndCreatedAtGreaterThanEqual(UUID guideId, Instant since);

  /** 요청에 가이드 단계를 붙인다. 이미 붙어 있으면 그대로 둔다(0건). */
  @Modifying
  @Query(
      value =
          "insert into catalog_collect_request_guides (id, request_id, guide_id, step_id,"
              + " created_at) values (gen_random_uuid(), :request, :guide, :step, :now)"
              + " on conflict (request_id, guide_id, step_id) do nothing",
      nativeQuery = true)
  int attach(
      @Param("request") UUID requestId,
      @Param("guide") UUID guideId,
      @Param("step") String stepId,
      @Param("now") Instant now);
}
