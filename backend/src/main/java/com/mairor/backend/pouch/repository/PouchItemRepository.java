package com.mairor.backend.pouch.repository;

import com.mairor.backend.pouch.entity.PouchItem;
import jakarta.persistence.LockModeType;
import java.util.Collection;
import java.util.List;
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

  /** 추천 입력과 같은 시점의 회원 파우치를 전부 안정된 순서로 읽는다. */
  List<PouchItem> findByUserIdOrderByCreatedAtDescIdDesc(UUID userId);

  /** 카탈로그 색 칸을 참조하는 파우치 회원을 중복 없이 찾는다. */
  @Query("select distinct item.userId from PouchItem item where item.shadeId in :shadeIds")
  List<UUID> findDistinctUserIdByShadeIdIn(@Param("shadeIds") Collection<UUID> shadeIds);

  /**
   * 지정한 회원들의 항목 중 카탈로그 호수에 연결된 것들. 호수의 색이 바뀌면 색 복사본을 맞춘다(S15P31A306-531). 회원 행을 잠근 뒤 그 회원들로 한정해서
   * 읽어, 버전을 올리는 회원과 색이 바뀌는 회원이 같게 한다.
   */
  List<PouchItem> findAllByShadeIdInAndUserIdIn(
      Collection<UUID> shadeIds, Collection<UUID> userIds);

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
