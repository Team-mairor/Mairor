package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CollectRequestStatus;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogCollectRequestRepository
    extends JpaRepository<CatalogCollectRequest, UUID> {

  /** 운영 확인용: 최근 요청부터. */
  List<CatalogCollectRequest> findAllByOrderByCreatedAtDescIdDesc(Pageable page);

  /** 운영 확인용: 한 상태의 최근 요청부터. */
  List<CatalogCollectRequest> findByStatusOrderByCreatedAtDescIdDesc(
      CollectRequestStatus status, Pageable page);

  /** 행 잠금과 함께 읽는다. 보내기·결과 반영이 같은 요청을 겹쳐 바꾸지 않게 한다. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select r from CatalogCollectRequest r where r.id = :id")
  Optional<CatalogCollectRequest> findByIdForUpdate(@Param("id") UUID id);

  /** 이 시각 전부터 보내지 못하고 남은 QUEUED 요청. 오래된 것부터 {@code limit}개. */
  @Query(
      value =
          "select id from catalog_collect_requests where status = 'QUEUED' and updated_at < :before"
              + " order by updated_at, id limit :limit",
      nativeQuery = true)
  List<UUID> findQueuedIdsBefore(@Param("before") Instant before, @Param("limit") int limit);

  /** 이 시각 전에 보내고 아직 결과가 없는 SENT 요청. 오래된 것부터 {@code limit}개. */
  @Query(
      value =
          "select id from catalog_collect_requests where status = 'SENT' and sent_at < :before"
              + " order by sent_at, id limit :limit",
      nativeQuery = true)
  List<UUID> findSentIdsBefore(@Param("before") Instant before, @Param("limit") int limit);

  /** 같은 제품의 진행 중(QUEUED·SENT) 요청. 부분 유니크라 많아야 하나다. */
  @Query(
      "select r from CatalogCollectRequest r where r.requestKey = :key and r.status in"
          + " (com.mairor.backend.products.entity.CollectRequestStatus.QUEUED,"
          + " com.mairor.backend.products.entity.CollectRequestStatus.SENT)")
  Optional<CatalogCollectRequest> findOpenByRequestKey(@Param("key") String requestKey);

  /**
   * 진행 중 요청이 없을 때만 새 요청을 QUEUED 로 넣는다. 동시에 같은 제품을 넣으면 하나만 들어가고 나머지는 0건이다(부분 유니크 {@code
   * uk_catalog_collect_requests_open_key}). 0건이면 {@link #findOpenByRequestKey}로 먼저 들어간 요청을 읽는다.
   */
  @Modifying
  @Query(
      value =
          "insert into catalog_collect_requests (id, trigger, request_key, category_code,"
              + " type_code, brand, name, product_url, shade_name, gap, target_product_id,"
              + " target_shade_id, target_color_id, target_slot_label, status, send_attempts,"
              + " created_at, updated_at) values (:id, :trigger, :key, :category, :type, :brand,"
              + " :name, :url, :shade, :gap, :targetProduct, :targetShade, :targetColor,"
              + " :slotLabel, 'QUEUED', 0, :now, :now)"
              + " on conflict (request_key) where status in ('QUEUED', 'SENT') do nothing",
      nativeQuery = true)
  int insertIfNoneOpen(
      @Param("id") UUID id,
      @Param("trigger") String trigger,
      @Param("key") String requestKey,
      @Param("category") String categoryCode,
      @Param("type") String typeCode,
      @Param("brand") String brand,
      @Param("name") String name,
      @Param("url") String productUrl,
      @Param("shade") String shadeName,
      @Param("gap") String gap,
      @Param("targetProduct") UUID targetProductId,
      @Param("targetShade") UUID targetShadeId,
      @Param("targetColor") UUID targetColorId,
      @Param("slotLabel") String targetSlotLabel,
      @Param("now") Instant now);

  /** 엔티티 그대로 넣는다. 진행 중 요청이 이미 있으면 0건이다. */
  default int insertIfNoneOpen(CatalogCollectRequest draft, Instant now) {
    CatalogCollectRequest.Target target = draft.getTarget();
    return insertIfNoneOpen(
        draft.getId(),
        draft.getTrigger().name(),
        draft.getRequestKey(),
        draft.getCategoryCode(),
        draft.getTypeCode(),
        draft.getBrand(),
        draft.getName(),
        draft.getProductUrl(),
        draft.getShadeName(),
        draft.getGap() == null ? null : draft.getGap().name(),
        target.productId(),
        target.shadeId(),
        target.colorId(),
        target.slotLabel(),
        now);
  }

  /**
   * 이 시각 뒤에 같은 제품으로 끝난 요청 중 다시 요청하지 않을 것이 있는가. 찾은 제품이 없음({@code NOT_FOUND}, 사유 {@code
   * SEARCH_EMPTY})과 부족 정보가 풀리지 않음({@code UNRESOLVED})이 해당한다. 수집할 공식 홈이 없음({@code
   * UNSUPPORTED_SOURCE})과 실패는 다음 등록 때 다시 요청한다.
   */
  @Query(
      "select count(r) > 0 from CatalogCollectRequest r where r.requestKey = :key"
          + " and r.finishedAt >= :since and (r.status ="
          + " com.mairor.backend.products.entity.CollectRequestStatus.UNRESOLVED"
          + " or (r.status = com.mairor.backend.products.entity.CollectRequestStatus.NOT_FOUND"
          + " and r.reason = 'SEARCH_EMPTY'))")
  boolean existsRecentDeadEnd(@Param("key") String requestKey, @Param("since") Instant since);

  /**
   * 이 시각 뒤에 같은 키로 끝난 요청이 있는가(상태 상관없음). 영상 분석 요청은 끝나면 가이드를 다시 대조하고, 그때 같은 부족분이 또 보이므로 이것으로 같은 요청을
   * 되풀이하지 않는다.
   */
  @Query(
      "select count(r) > 0 from CatalogCollectRequest r where r.requestKey = :key"
          + " and r.finishedAt >= :since")
  boolean existsFinishedSince(@Param("key") String requestKey, @Param("since") Instant since);
}
