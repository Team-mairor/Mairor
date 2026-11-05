package com.mairor.backend.pouch.repository;

import com.mairor.backend.pouch.entity.PouchItem;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PouchItemRepository extends JpaRepository<PouchItem, UUID> {

  Optional<PouchItem> findByIdAndUserId(UUID id, UUID userId);

  /** 회원·선택 필터에 맞는 페이지를 새 항목 순서로 읽는다. */
  @Query(
      value =
          "select item from PouchItem item"
              + " where item.userId = :userId"
              + " and (:category is null or item.category = :category)"
              + " and (:type is null or item.type = :type)"
              + " order by item.createdAt desc, item.id desc",
      countQuery =
          "select count(item) from PouchItem item"
              + " where item.userId = :userId"
              + " and (:category is null or item.category = :category)"
              + " and (:type is null or item.type = :type)")
  Page<PouchItem> findPageForUser(
      @Param("userId") UUID userId,
      @Param("category") String category,
      @Param("type") String type,
      Pageable pageable);

  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select item from PouchItem item where item.id = :id and item.userId = :userId")
  Optional<PouchItem> findByIdAndUserIdForUpdate(
      @Param("id") UUID id, @Param("userId") UUID userId);

  boolean existsByUserIdAndBrandNormalizedAndNameNormalizedAndShadeNameNormalizedAndIdNot(
      UUID userId,
      String brandNormalized,
      String nameNormalized,
      String shadeNameNormalized,
      UUID id);

  boolean existsByUserIdAndBrandNormalizedAndNameNormalizedAndShadeNameNormalized(
      UUID userId, String brandNormalized, String nameNormalized, String shadeNameNormalized);
}
