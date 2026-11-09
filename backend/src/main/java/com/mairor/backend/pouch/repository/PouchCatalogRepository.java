package com.mairor.backend.pouch.repository;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

/** 파우치 등록에 필요한 카탈로그 읽기 전용 조회. 카탈로그를 저장하거나 갱신하지 않는다. */
public interface PouchCatalogRepository
    extends Repository<com.mairor.backend.products.entity.Product, UUID> {

  /**
   * 제품·분류·선택 호수·색상을 한 SQL 스냅샷으로 읽는다. shadeId 가 null 이어도 제품 행은 반환한다.
   *
   * <p>색은 호수의 색 칸에서 정한다. 칸이 하나이고 서비스에 쓸 수 있는 상태({@code ReviewStatus#isUsable}:
   * AUTO_APPROVED·APPROVED)면 그 칸의 색을 돌려준다. 칸이 둘 이상인 팔레트이거나 쓸 수 있는 칸이 없으면 색은 {@code null}이다. 칸이 하나도
   * 없는 호수는 옛 단일 색 컬럼을 그대로 돌려준다(이관 전 데이터와의 호환이며 옛 컬럼은 지우지 않았다). 쓸 수 있는 상태 목록은 {@code ReviewStatus}와
   * 같아야 하며 테스트가 모든 상태로 확인한다.
   */
  @Query(
      value =
          """
          select p.id, p.brand, p.name, c.code as category_code, t.code as type_code,
                 c.shade_selectable, s.id as shade_id, s.name as shade_name,
                 case when coalesce(sc.slot_count, 0) = 0 then s.color_hex
                      when sc.slot_count = 1 and sc.usable then sc.color_hex end as color_hex,
                 case when coalesce(sc.slot_count, 0) = 0 then s.color_estimated
                      when sc.slot_count = 1 and sc.usable then sc.color_estimated end as color_estimated
            from products p
            join product_types t on t.code = p.type_code and t.category_code = p.category_code
            join product_categories c on c.code = p.category_code
            left join product_shades s on s.product_id = p.id and s.id = :shadeId
            left join lateral (
                 select count(*) as slot_count,
                        min(k.color_hex) as color_hex,
                        bool_or(k.color_estimated) as color_estimated,
                        coalesce(bool_and(k.review_status in ('AUTO_APPROVED', 'APPROVED')), false) as usable
                   from product_shade_colors k
                  where k.shade_id = s.id
            ) sc on true
           where p.id = :productId
          """,
      nativeQuery = true)
  List<Object[]> findSelection(@Param("productId") UUID productId, @Param("shadeId") UUID shadeId);
}
