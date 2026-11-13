package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.CatalogCollectRequestUser;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogCollectRequestUserRepository
    extends JpaRepository<CatalogCollectRequestUser, UUID> {

  List<CatalogCollectRequestUser> findByRequestId(UUID requestId);

  List<CatalogCollectRequestUser> findByRequestIdInOrderByCreatedAtAsc(Collection<UUID> requestIds);

  /** 회원이 이 시각 뒤에 붙은 요청 수. 하루 한도에 쓴다. */
  long countByUserIdAndCreatedAtGreaterThanEqual(UUID userId, Instant since);

  /** 요청에 회원·파우치 항목을 붙인다. 같은 항목이 이미 붙어 있으면 그대로 둔다(0건). */
  @Modifying
  @Query(
      value =
          "insert into catalog_collect_request_users (id, request_id, user_id, pouch_item_id,"
              + " pouch_item_updated_at, created_at) values (gen_random_uuid(), :request, :user,"
              + " :item, :itemUpdatedAt, :now)"
              + " on conflict (request_id, pouch_item_id) do nothing",
      nativeQuery = true)
  int attach(
      @Param("request") UUID requestId,
      @Param("user") UUID userId,
      @Param("item") UUID pouchItemId,
      @Param("itemUpdatedAt") Instant pouchItemUpdatedAt,
      @Param("now") Instant now);
}
